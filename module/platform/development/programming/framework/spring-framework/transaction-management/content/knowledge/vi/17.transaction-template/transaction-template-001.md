# Khi nào cần ranh giới giao dịch hiển thị trong mã

## 1. Tại sao có lúc phải nhìn thấy transaction boundary ngay trong Java?

Ở đa số Spring service thông thường, `@Transactional` là lựa chọn dễ đọc nhất:

```java
@Transactional
public void createOrder(CreateOrderCommand command) {
    validate(command);
    orderRepository.save(toOrder(command));
    inventoryRepository.reserve(command.items());
}
```

Đây là một snippet minh họa, chưa phải class độc lập: `validate`, `toOrder` và hai repository do ứng dụng định nghĩa. Annotation đặt **ranh giới giao dịch quanh toàn bộ method được gọi qua Spring AOP proxy**. Nếu toàn bộ method thật sự là **một unit of work** cần cùng commit/rollback, đó là thiết kế tốt.

Nhưng nếu method bao gồm **nhiều giai đoạn có yêu cầu transaction khác nhau**, ví dụ:

1. Gọi API ngoài để lấy thông tin (có thể chậm).
2. Ghi hai bản ghi liên quan trong **một transaction ngắn**.
3. Chỉ sau khi transaction đã hoàn tất mới gọi một bước tiếp theo, gửi thông báo hoặc đọc báo cáo.
4. Nếu bước sau thất bại, **không** muốn giả vờ database write ở bước 2 chưa từng commit.

Thì việc đặt một `@Transactional` lên **toàn bộ method** có thể làm transaction tồn tại quá lâu hoặc đặt sai semantic boundary. Lúc đó `TransactionTemplate` cho phép biểu diễn rất rõ:

```java
ExternalData source = fetchExternalData(); // ngoài transaction DB

String id = transactionTemplate.execute(status -> {
    persistSource(source);
    updateRelatedRows(source);
    return source.id();
}); // execute đã đi hết completion path của scope này

notifyAbout(id); // nằm ngoài callback, không nằm trong scope template vừa tạo
```

Snippet này **minh họa cấu trúc**, cần các method/biến được khai báo. Điểm học chính là **khối callback chính là phần mã yêu cầu chạy trong scope transaction của template**. Nếu template tạo transaction mới và không có outer transaction, khi `execute(...)` trả về bình thường, transaction manager đã thực hiện completion path, thường là commit thành công. Nếu callback ném runtime exception, template xử lý rollback rồi propagate exception.

**Phân biệt quan trọng:** một callback `return` chưa đồng nghĩa database commit; lời gọi **`transactionTemplate.execute(...)` return tới caller** mới xảy ra sau bước manager completion. Hơn nữa, nếu template dùng `PROPAGATION_REQUIRED` và đang **tham gia outer transaction**, `execute` return chỉ có nghĩa logical inner scope đã hoàn tất; **physical commit vẫn chờ outer owner**.

Chủ đề bài này là **TransactionTemplate → Khi nào cần ranh giới giao dịch hiển thị trong mã**. Không phải mọi vấn đề đều cần transaction programmatic. Mục tiêu là biết **khi nào nên**, **khi nào không nên**, **API sử dụng như thế nào**, **những lời hứa không được suy ra**, và **cách chứng minh bằng integration test**.

## 2. Định nghĩa: TransactionTemplate là gì?

`org.springframework.transaction.support.TransactionTemplate` là abstraction của Spring dành cho **imperative programmatic transaction management**. Nó kế thừa `DefaultTransactionDefinition` và triển khai `TransactionOperations`, dùng `PlatformTransactionManager` thực sự để thực hiện:

- `getTransaction(definition)` trước callback;
- chạy callback với một `TransactionStatus`;
- nếu callback ném `RuntimeException` hoặc `Error`, xử lý rollback thích hợp và ném lại lỗi;
- nếu callback return bình thường, hoàn tất scope bằng đường `commit(status)`, trong đó manager vẫn phải tôn trọng rollback-only;
- cleanup các transaction resources phù hợp với manager.

Nhà phát triển **không cần** tự viết `try/catch/commit/rollback/finally` theo `PlatformTransactionManager` cho trường hợp thông thường.

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

String result = tx.execute(status -> {
    repository.insert("alpha");
    return "alpha";
});
```

Đây là snippet cần `PlatformTransactionManager transactionManager` và `repository` tồn tại. Kiểu return của `execute(...)` là generic; `null` là kết quả hợp lệ nếu callback trả `null`. `TransactionStatus` có phương thức `setRollbackOnly()` và `isNewTransaction()`, hữu ích khi bạn cần quyết định rõ trong code.

Nếu callback không cần trả giá trị, dùng:

```java
tx.executeWithoutResult(status -> {
    repository.insert("alpha");
    repository.insert("beta");
});
```

`executeWithoutResult` là API trên `TransactionOperations`, được `TransactionTemplate` cung cấp. Trong ví dụ độc lập sau, tất cả import và dependencies đều được khai báo rõ.

### 2.1. So sánh với `@Transactional`

| Tiêu chí | `@Transactional` declarative | `TransactionTemplate` programmatic |
| --- | --- | --- |
| Vị trí boundary | Quanh lời gọi method được AOP intercept | Chính **phạm vi callback** truyền vào `execute` |
| Cần đi qua proxy cho boundary đó? | **Có** trong proxy mode mặc định | **Không**: lời gọi template là Java code trực tiếp |
| Tách một đoạn DB ngắn giữa nhiều bước dài | Cần chia bean/method và call qua proxy | Dễ biểu đạt ngay trong method điều phối |
| Nhiều transaction độc lập trong một workflow | Có thể tạo bằng nhiều bean/method propagation khác nhau | Có thể gọi nhiều `execute` riêng |
| Rollback với runtime exception | Theo rollback rule `@Transactional` | Template xử lý runtime exception/Error thoát callback |
| Checked exception | Điều khiển qua `rollbackFor/noRollbackFor` | Callback không khai báo checked exception; wrap hoặc chủ động `setRollbackOnly` |
| Quyết định rollback dù không ném exception | `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` | `status.setRollbackOnly()` trực tiếp |
| Code business biết Spring transaction API? | Ít hoặc không | Có: phụ thuộc `TransactionTemplate` |
| Cấu hình propagation, isolation, timeout | Thuộc annotation, manager và cấu hình | Thuộc instance `TransactionTemplate` |
| Giao dịch reactive | Dùng reactive transaction support phù hợp | **Không** dùng template imperative; cân nhắc `TransactionalOperator` |

**Quy tắc lựa chọn:** nếu có nhiều method service thông thường, transaction declarative giúp tách infrastructure khỏi business code. Nếu chỉ có một số ít điểm cần boundary chủ động hoặc workflow điều phối giai đoạn rất rõ, `TransactionTemplate` đáng cân nhắc. Đây cũng là khuyến nghị trong tài liệu Spring về **Choosing Between Programmatic and Declarative Transaction Management**.

### 2.2. TransactionTemplate không phải một loại transaction manager

`TransactionTemplate` không trực tiếp mở database connection bằng cơ chế riêng. Nó **ủy quyền** tới một `PlatformTransactionManager`:

```text
Service method
  |
  +-- tx.execute(callback)
         |
         +-- manager.getTransaction(definition)
         |      -> physical transaction mới / tham gia transaction hiện có
         |
         +-- callback.doInTransaction(status)
         |      -> JDBC/JPA repository operations
         |
         +-- manager.commit(status) hoặc rollback(status)
         |      -> rollback-only, synchronization, cleanup
         |
         +-- return kết quả hoặc propagate exception
```

Nó không thay thế việc chọn đúng `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager`, JTA hay resource manager phù hợp. Mỗi manager có semantics và tài nguyên riêng.

## 3. Các tình huống NÊN dùng boundary hiển thị

### 3.1. Chỉ đoạn cập nhật DB cần transaction, workflow còn lại không

Ví dụ một batch item:

```text
parse input file
  -> validate syntax
  -> fetch remote metadata
  -> BEGIN DB TRANSACTION
       INSERT detail rows
       UPDATE aggregate
     COMMIT DB TRANSACTION
  -> format result
  -> notify downstream
```

Đặt `@Transactional` lên toàn bộ method có thể khiến transaction giữ connection/lock trong lúc đọc file, gọi HTTP hoặc chờ user input. Dùng `TransactionTemplate` giúp chỉ bao transaction quanh đoạn DB cần nguyên tử.

Không hiểu “short transaction” là bỏ qua atomicity: các SQL statements thuộc cùng invariant vẫn phải nằm **trong cùng một callback** và cùng manager.

### 3.2. Cần nhiều unit of work độc lập trong một vòng lặp

Ví dụ import 100,000 dòng theo chunk:

```java
for (Chunk chunk : chunks) {
    tx.executeWithoutResult(status -> {
        validateChunk(chunk);
        persistChunk(chunk);
    });
}
```

Đây là snippet minh họa; `Chunk`, `chunks`, `validateChunk` và `persistChunk` do ứng dụng cung cấp. Mỗi lượt gọi `executeWithoutResult` có **logical transaction scope** riêng. Nếu không có outer transaction và propagation là `REQUIRED`, mỗi chunk thường có physical transaction riêng, cho phép checkpoint/progress và retry chunk bị lỗi. Nếu vòng lặp đang nằm trong outer `@Transactional`, mọi callback `REQUIRED` có thể tham gia cùng physical transaction — **không còn tách commit theo chunk**.

Chia chunk làm thay đổi tính nguyên tử: đã commit chunk 1 thì lỗi ở chunk 2 **không tự** rollback chunk 1. Chỉ dùng khi nghiệp vụ cho phép partial success, có idempotency key và khả năng tiếp tục an toàn.

### 3.3. Cần xử lý thất bại của bước trước rồi bắt đầu transaction mới

```java
try {
    tx.executeWithoutResult(status -> persistOneOperation());
} catch (IllegalStateException ex) {
    recordFailure(ex);
}

tx.executeWithoutResult(status -> persistIndependentOperation());
```

Snippets chưa độc lập. Quan trọng là `catch` nằm **bên ngoài `execute` đầu tiên**: transaction manager đã đi qua rollback path cho scope lỗi trước khi code tới bước hai. Nếu bạn bắt exception **bên trong callback** và cứ tiếp tục SQL, DB/JPA resource có thể đã vào trạng thái aborted/rollback-only. Đừng “nuốt lỗi” trong một physical transaction hỏng rồi mong commit.

Đồng thời, việc gọi hai callback chỉ thật sự phân tách **physical commit/rollback** khi chúng không bị đặt trong một outer transaction `REQUIRED`. Để bảo đảm độc lập khi có outer, cần kiểm soát propagation và chấp nhận hệ quả như `REQUIRES_NEW`.

### 3.4. Cần rollback có chủ đích khi một nghiệp vụ trả kết quả chứ không ném lỗi

Một bước có thể nhận response biểu thị “không đủ điều kiện, bỏ toàn bộ thay đổi”:

```java
Outcome result = tx.execute(status -> {
    repository.insertDraft();
    if (!eligibilityPolicy.accepted()) {
        status.setRollbackOnly();
        return Outcome.rejected("Not eligible");
    }
    return Outcome.accepted();
});
```

`Outcome`, `repository` và `eligibilityPolicy` là class/biến minh họa. Khi callback tự đánh dấu rollback-only trên status **sở hữu transaction mới**, `execute` có thể **return bình thường** dù manager thực hiện rollback. Đó là semantics có chủ đích, không phải một lỗi Spring. Vì thế **return value phải thể hiện rõ “đã chấp nhận” hay “đã từ chối”**, không được gọi kết quả `CREATED` trước khi completion thực sự thành công.

Nếu template chỉ tham gia outer transaction, `setRollbackOnly` có thể làm shared physical transaction rollback-only và outer owner sau đó gặp `UnexpectedRollbackException`. Đừng coi `setRollbackOnly` là một boolean cục bộ không ảnh hưởng caller.

### 3.5. Muốn tránh vấn đề self-invocation của annotation ở một điểm nhỏ

Trong proxy mode, `this.someTransactionalMethod()` thường không qua Spring proxy, nên annotation trên inner method không tạo một boundary riêng. Ngược lại, một lời gọi trực tiếp:

```java
public void outer() {
    helper();
}

private void helper() {
    tx.executeWithoutResult(status -> repository.insert("ok"));
}
```

vẫn sử dụng template, dù helper là private và được gọi bằng `this`. Bởi vì **boundary là lời gọi API**, không phải advice intercept method. Đó là một lý do kỹ thuật hợp lý để dùng template trong một orchestration method nhỏ.

Tuy nhiên, không nên chuyển hết code sang template chỉ để né một thiết kế bean không hợp lý. Nếu có nhiều domain services, phương pháp declarative trên các service beans riêng có thể dễ bảo trì hơn.

### 3.6. Muốn gắn tên transaction hoặc policy riêng cho một đoạn

`TransactionTemplate` kế thừa `DefaultTransactionDefinition`, cho phép cấu hình:

```java
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setName("settle-invoice");
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(false);
```

Snippet cần imports/manager. Các cài đặt là **yêu cầu** tới manager, không phải cam kết mọi database/driver đều thực hiện tương tự. `REQUIRES_NEW` có transaction độc lập và có thể cần thêm connection. Isolation, timeout và readOnly có ý nghĩa đặc biệt khi **tạo transaction mới**; nếu `REQUIRED` tham gia transaction hiện có, outer scope thường quyết định các đặc tính physical transaction.

Đặt **một instance template theo cấu hình tĩnh**, ví dụ `readOnlyTemplate` và `writeTemplate`. `TransactionTemplate` thread-safe khi instance không bị sửa cấu hình liên tục trong lúc nhiều thread sử dụng; đừng gọi `setPropagationBehavior`/`setTimeout` trước mỗi request trên một singleton shared object rồi gây race.

## 4. Các tình huống KHÔNG nên chọn TransactionTemplate

1. **Service method thuần DB có một boundary hiển nhiên.** `@Transactional` dễ đọc hơn; không cần callback lồng nhau chỉ vì “trông explicit”.
2. **Muốn khóa một database row hay ngăn duplicate.** TransactionTemplate không tự thêm `SELECT FOR UPDATE`, `UNIQUE`, optimistic version hay isolation đúng; cần DB constraints/locking.
3. **Muốn biến email/HTTP/Kafka call thành một phần của JDBC rollback.** Template quản lý tài nguyên tham gia manager, không rollback một email đã gửi. Xem transactional outbox/idempotency.
4. **Muốn tránh kiểm tra transaction isolation hoặc concurrent race.** Explicit boundary không sửa lỗi TOCTOU hoặc lost updates.
5. **Đang dùng reactive `Mono`/`Flux`.** `TransactionTemplate` là imperative và thường dựa trên thread-bound resources; dùng `TransactionalOperator` với `ReactiveTransactionManager` để bọc lifecycle reactive publisher.
6. **Đang cố làm một transaction chạy qua nhiều thread tùy ý.** ThreadLocal của imperative transaction không được chuyển tự động qua `CompletableFuture`, `@Async` hay executor.
7. **Đang cần distributed transaction trên hai database/ngoại hệ thống.** Một `PlatformTransactionManager` địa phương không tự giải quyết điều phối nhiều tài nguyên.
8. **Chỉ vì muốn bắt exception bên trong callback rồi tiếp tục.** Database/ORM có thể đã hỏng transaction; chia boundary đúng hoặc để rollback hoàn tất trước khi xử lý.
9. **Muốn retry SQL mà không có idempotency.** Callback có transaction mới không bảo đảm retry an toàn nếu kết quả commit của lần trước chưa xác định.
10. **Dùng trong shared domain model để tạo dependency sâu vào Spring.** Có thể tách một infrastructure/application service bao bọc template và giữ domain model framework-agnostic.

**Nguyên tắc kiến trúc:** hãy đặt boundary **ở tầng ứng dụng/orchestration**, nơi biết unit of work nào cần nguyên tử. Đừng rải template vào mọi repository rồi làm mất ranh giới nghiệp vụ.

## 5. `execute`, `executeWithoutResult`, `TransactionStatus`

### 5.1. `execute(TransactionCallback<T>)`

```java
Long id = tx.execute(status -> {
    long createdId = insertOrder();
    insertLineItems(createdId);
    return createdId;
});
```

Đây là mẫu minh họa có method `insertOrder`/`insertLineItems` giả định. Nếu có một physical transaction mới, cả hai thao tác được bao trong cùng DB transaction. `id` được trả cho caller **sau khi transaction manager hoàn tất scope**. Nhưng khi callback chỉ tham gia outer `REQUIRED`, physical commit còn chờ outer.

Không lấy return value của callback làm bằng chứng database đã durable commit khi vẫn có outer transaction hay lỗi commit về sau.

### 5.2. `executeWithoutResult(Consumer<TransactionStatus>)`

```java
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET active = ? WHERE id = ?", true, 10L);
});
```

Mẫu này gọn khi không cần trả giá trị từ callback. Nó không yêu cầu implement class `TransactionCallbackWithoutResult` thủ công. `status` vẫn dùng được nếu cần `setRollbackOnly()`.

### 5.3. `status.setRollbackOnly()` khác ném exception

```java
Decision decision = tx.execute(status -> {
    insertDraft();
    if (businessCheckFails()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    return Decision.ACCEPTED;
});
```

Callback return `REJECTED` mà transaction có thể rollback bình thường; không có `RuntimeException` bắt buộc được ném. Một transaction owner tự đánh dấu local rollback-only có thể rollback **im lặng về mặt exception**. Vì thế kiểu kết quả phải mô tả đúng business semantics.

Với checked exception không được phép throw trực tiếp từ callback signature, có hai đường đi:

**A. Catch và trả business result sau khi đánh dấu rollback-only:**

```java
return tx.execute(status -> {
    try {
        callCodeThatThrowsIOException();
        saveData();
        return Result.ok();
    } catch (IOException ex) {
        status.setRollbackOnly();
        return Result.failed(ex.getMessage());
    }
});
```

**B. Wrap thành unchecked exception để template rollback và propagate:**

```java
tx.executeWithoutResult(status -> {
    try {
        callCodeThatThrowsIOException();
        saveData();
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
});
```

Đây là snippets minh họa, chưa có `Result`, `saveData`, `callCodeThatThrowsIOException` cụ thể; cần `java.io.IOException` và `java.io.UncheckedIOException`. Trong ví dụ đầy đủ mục 8 sẽ có class/method tương ứng. **Không** ép mọi checked exception phải rollback nếu contract nghiệp vụ thực sự muốn giữ dữ liệu; cần quyết định từ invariant trước.

### 5.4. Những gì callback có thể và không thể bắt

```text
Caller -> tx.execute(...)
              |
              +-- manager.getTransaction(...)
              +-- callback START
              |     JDBC INSERT
              |     callback return
              +-- manager.commit(status)  <-- có thể lỗi ở đây
              +-- callback scope đã xong
        <- execute return hoặc ném exception
```

`try/catch` **bên trong callback** không thể bắt một exception do transaction manager ném **sau callback return**, ví dụ commit failure. `try/catch` **bên ngoài `execute(...)`** mới bao trùm cả begin/callback/commit/rollback path tương ứng.

Trong một workflow cần báo trạng thái “đã lưu”, hãy đặt quyết định **sau khi `execute` trả về** và ngoài mọi outer transaction có thể đang sở hữu physical transaction. Nếu thất bại ngay lúc commit và kết nối bị mất, outcome có thể không xác định; không tự khẳng định rollback thành công và retry mù.

## 6. Đừng nhầm boundary hiển thị với physical transaction độc lập

### 6.1. Default `PROPAGATION_REQUIRED` có thể JOIN

`TransactionTemplate` mặc định dùng propagation `REQUIRED`. Ví dụ:

```java
@Transactional
public void outer() {
    tx.executeWithoutResult(status -> {
        jdbc.update("INSERT INTO events(code) VALUES (?)", "inner");
    });
    throw new IllegalStateException("outer failure");
}
```

Snippet có các field `tx`/`jdbc` giả định, và method `outer` phải được gọi qua proxy. Khi template đang tham gia outer transaction hiện có, `executeWithoutResult` return **không có nghĩa inner INSERT đã commit độc lập**. Outer ném exception và transaction owner rollback -> inner INSERT cũng bị hủy.

```text
outer @Transactional(REQUIRED): physical transaction T
   +-- tx.execute(REQUIRED) -> JOIN T
       +-- INSERT 'inner'
       +-- execute returns (không physical commit)
   +-- outer throws
   +-- ROLLBACK T (hủy 'inner')
```

Đây là lý do câu “mọi `execute` tạo transaction riêng” là **sai**.

### 6.2. Cần độc lập thật thì `REQUIRES_NEW`

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);

outerTemplate.executeWithoutResult(outer -> {
    writeMainData();
    isolated.executeWithoutResult(inner -> writeIndependentAudit());
    outer.setRollbackOnly();
});
```

Đây là mẫu minh họa. Nếu manager/resource hỗ trợ `REQUIRES_NEW`, inner dùng physical transaction T2 và có thể commit độc lập, trong khi outer T1 bị rollback. Nhưng T1 và T2 **không còn atomic cùng nhau**. Hơn nữa outer vẫn có thể giữ một connection trong lúc T2 cần connection khác; pool phải đủ, tránh deadlock/starvation khi nhiều threads làm cùng lúc.

**`REQUIRES_NEW` không phải “làm retry an toàn” hay “lưu audit vĩnh viễn” một cách tự động**. Audit vẫn có thể gặp lỗi, DB outage hoặc commit outcome chưa rõ. Nếu audit/event phải gắn chặt với transaction chính, transactional outbox là một phương án quan trọng cần cân nhắc.

### 6.3. `NESTED` không giống `REQUIRES_NEW`

Nếu dùng `PROPAGATION_NESTED` với JDBC manager/driver hỗ trợ savepoints, inner rollback thường là rollback **về savepoint trong cùng physical transaction**, không có T2 độc lập. Khi outer sau đó rollback, mọi thay đổi trong T, kể cả phần inner từng thành công, có thể bị hủy. Với JPA, `JpaTransactionManager` không mặc định hỗ trợ nested JPA semantics; JDBC savepoint không snapshot JPA persistence context.

### 6.4. Có thể gọi template từ method private

Khác với `@Transactional` proxy, `TransactionTemplate` không cần method chứa callback public hay được gọi qua Spring AOP proxy. Nhưng điều này **không** làm các tài nguyên bất kỳ trở thành transaction-aware. `JdbcTemplate` vẫn phải dùng cùng `DataSource`/transaction manager; `EntityManager`/JPA vẫn cần manager phù hợp; gọi async sang thread khác vẫn cần cơ chế riêng.

## 7. Thiết kế ranh giới để giảm lock time và giữ outcome đúng

### 7.1. Một workflow có external I/O

**Cách không nên làm khi HTTP chậm và không thuộc DB transaction:**

```java
@Transactional
public void importFromPartner() {
    PartnerResponse response = remoteClient.fetch(); // network I/O lâu
    repository.insert(response);
    remoteClient.acknowledge(response);              // không thể DB rollback
}
```

Đây là snippet giả định, không phải chương trình độc lập. Transaction có thể giữ connection/lock trong lúc chờ network, trong khi response `acknowledge` không được rollback bởi DB manager.

**Cách hiển thị boundary ngắn hơn:**

```java
public void importFromPartner() {
    PartnerResponse response = remoteClient.fetch(); // ngoài DB transaction

    tx.executeWithoutResult(status -> {
        repository.insert(response);
        repository.updateRelatedRows(response);
    });

    remoteClient.acknowledge(response);  // ngoài callback
}
```

Ở đây callback chỉ chứa DB work. Nếu transaction do template tạo mới và `execute` trả bình thường, DB transaction hoàn tất trước khi gửi acknowledge. **Nhưng nếu acknowledge thất bại**, bản ghi DB đã commit **không tự rollback**. Nếu phải đảm bảo sự kiện/thông báo được giao tin cậy sau commit, hãy cân nhắc outbox + dispatcher retry/idempotent; không gửi message trực tiếp rồi gọi đó là “atomic”.

### 7.2. Vì sao outbox thường tốt hơn gọi gửi email ngay sau commit?

```text
DB transaction:
    INSERT order
    INSERT outbox_event
    COMMIT
          |
          v
outbox dispatcher:
    đọc event committed
    gửi message (retry theo idempotency)
    đánh dấu delivered
```

Lưu order và outbox record trong **cùng transaction** bảo đảm hai row cùng commit/rollback. Dispatcher là thành phần khác với retry an toàn cho tác dụng ngoài DB. Khi `TransactionTemplate` giúp làm lộ boundary DB, nó **không thay thế outbox** nếu cần at-least-once delivery hoặc exactly-once business effect qua nhiều hệ thống.

### 7.3. TransactionTemplate không phải stopwatch

`setTimeout(10)` không đảm bảo hủy mọi đoạn Java code CPU-bound hoặc `Thread.sleep(...)` sau 10 giây. Timeout có thể được manager, resource hoặc JDBC statement hưởng ứng theo cách riêng. Với external I/O, dùng network client timeout độc lập và không giữ DB transaction xuyên qua network call khi không cần.

### 7.4. Một callback nên nhỏ, nhưng không chia nhỏ invariant

Không nên phân mỗi SQL statement thành một `execute`:

```java
tx.executeWithoutResult(s -> insertOrder());
tx.executeWithoutResult(s -> reserveInventory());
```

Nếu nghiệp vụ yêu cầu order và inventory **cùng thành công hoặc cùng thất bại**, cách chia trên có thể commit order trước khi reserve lỗi. Đúng hơn:

```java
tx.executeWithoutResult(s -> {
    insertOrder();
    reserveInventory();
});
```

Đây là snippets minh họa; điều kiện là cùng resource manager và propagation phù hợp. “Transaction ngắn” không đồng nghĩa “transaction nhỏ bất chấp invariant”.

## 8. Dự án hoàn chỉnh Java 17 + Spring Boot/JDBC/H2

Ví dụ sau dùng **Spring Boot 3.3.5**, Spring JDBC, H2 và JUnit 5. Nó mô phỏng rõ từng điểm mà `TransactionTemplate` thêm giá trị:

- trả kết quả của callback sau completion;
- callback `void`;
- runtime exception làm rollback;
- `setRollbackOnly()` cho business rejection không ném exception;
- checked exception được chuyển sang business result hoặc wrapped unchecked;
- hai transaction tách nhau, retry/continue **sau** rollback;
- `REQUIRES_NEW` commit audit độc lập với outer rollback;
- lỗi ngoài callback **không** rollback một DB transaction đã commit;
- self-call vẫn thực thi template vì đó là lời gọi trực tiếp, không dựa vào proxy;
- đọc trạng thái transaction trong và ngoài callback;
- read-only template với settings riêng.

### 8.1. Cấu trúc file

```text
visible-transaction-boundaries/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/boundary/
    │   │   ├── VisibleBoundaryApplication.java
    │   │   ├── EventStore.java
    │   │   └── BoundaryService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/boundary/
        └── BoundaryServiceIntegrationTest.java
```

Nếu tạo dự án từ Spring Initializr thì có thể có sẵn Gradle Wrapper; nếu bạn tạo chính xác các file bên trên thủ công, cần cài Gradle hoặc tạo wrapper trước. Java code có package nhất quán `com.example.boundary`.

`settings.gradle`:

```groovy
rootProject.name = 'visible-transaction-boundaries'
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

Dùng JDK 17+ cùng Gradle tương thích Spring Boot plugin. `spring-boot-starter-jdbc` cấp `JdbcTemplate`/transaction support; H2 là database trong bộ nhớ; JUnit 5 do Spring Boot starter test cung cấp. Các dependency versions cụ thể do Spring Boot dependency management quản lý.

### 8.2. Schema và datasource

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:boundaries;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_key VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE audit_entries (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    audit_key VARCHAR(80) NOT NULL UNIQUE
);
```

Tách `tx_events` và `audit_entries` giúp test `REQUIRES_NEW` không cạnh tranh update cùng row/unique key với outer T, tránh lock conflict không cần thiết trong bài học. Trong ứng dụng thật, việc commit audit độc lập có thể **không** đúng yêu cầu business, xem phần lưu ý trước đó.

### 8.3. Ứng dụng với một transaction manager

`src/main/java/com/example/boundary/VisibleBoundaryApplication.java`:

```java
package com.example.boundary;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class VisibleBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(VisibleBoundaryApplication.class, args);
    }

    @Bean("transactionManager")
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Mẫu này **không cần `@EnableTransactionManagement` chỉ để dùng TransactionTemplate**, vì boundary được gọi bằng API trực tiếp. Có một `PlatformTransactionManager` gắn với một `DataSource`. Spring Boot tự cấu hình datasource và `JdbcTemplate`; ta cung cấp transaction manager bean tường minh để biết chính xác template dùng gì.

Nếu application có nhiều manager, phải inject đúng manager/qualifier; không chọn manager cho JPA rồi dùng `JdbcTemplate` trên một datasource không liên quan và mong SQL cùng commit.

### 8.4. Repository JDBC đơn giản

`src/main/java/com/example/boundary/EventStore.java`:

```java
package com.example.boundary;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventStore {
    private final JdbcTemplate jdbc;

    public EventStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void saveEvent(String key) {
        jdbc.update(
                "INSERT INTO tx_events(event_key) VALUES (?)", key);
    }

    public void saveAudit(String key) {
        jdbc.update(
                "INSERT INTO audit_entries(audit_key) VALUES (?)", key);
    }

    public List<String> eventKeys() {
        return jdbc.queryForList(
                "SELECT event_key FROM tx_events ORDER BY event_key",
                String.class);
    }

    public List<String> auditKeys() {
        return jdbc.queryForList(
                "SELECT audit_key FROM audit_entries ORDER BY audit_key",
                String.class);
    }

    public long eventCount() {
        Long result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
        return result;
    }

    public void clearAll() {
        jdbc.update("DELETE FROM audit_entries");
        jdbc.update("DELETE FROM tx_events");
    }
}
```

`EventStore` không tự tạo transaction. Khi được gọi trong template callback, `JdbcTemplate` sẽ tham gia Spring-managed JDBC transaction trên cùng datasource. Khi test gọi `clearAll()` ở ngoài callback, từng SQL statement dùng connection autocommit theo fixture H2, giúp test chuẩn bị dữ liệu độc lập với transaction của service.

### 8.5. TransactionTemplate được cấu hình một lần trong service

`src/main/java/com/example/boundary/BoundaryService.java`:

```java
package com.example.boundary;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class BoundaryService {
    private final EventStore store;
    private final TransactionTemplate required;
    private final TransactionTemplate independent;
    private final TransactionTemplate readOnly;

    public BoundaryService(
            PlatformTransactionManager transactionManager,
            EventStore store) {

        this.store = store;

        this.required = new TransactionTemplate(transactionManager);
        this.required.setName("visible-event-write");

        this.independent = new TransactionTemplate(transactionManager);
        this.independent.setName("independent-audit");
        this.independent.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);

        this.readOnly = new TransactionTemplate(transactionManager);
        this.readOnly.setReadOnly(true);
        this.readOnly.setName("read-events");
    }

    public record Outcome(boolean accepted, String message) {
    }

    public record ScopeObservation(
            boolean activeInside,
            boolean activeAfter) {
    }

    public String saveAndReturn(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            return key;
        });
    }

    public void saveWithoutResult(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
        });
    }

    public void throwRuntimeAndRollback(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            throw new IllegalStateException("Simulated business failure");
        });
    }

    public void markRollbackOnlyWithoutThrowing(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            status.setRollbackOnly();
        });
    }

    public Outcome checkedFailureAsBusinessResult(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            try {
                checkedOperation();
                return new Outcome(true, "ACCEPTED");
            } catch (IOException ex) {
                status.setRollbackOnly();
                return new Outcome(false, "INPUT_ERROR");
            }
        });
    }

    public void wrapCheckedFailureAndRollback(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
            try {
                checkedOperation();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        });
    }

    private static void checkedOperation() throws IOException {
        throw new IOException("Simulated checked I/O failure");
    }

    public void recoverAfterSeparateFailedTransaction() {
        try {
            required.executeWithoutResult(status -> {
                store.saveEvent("failed-step");
                throw new IllegalStateException("Step failed");
            });
        } catch (IllegalStateException expected) {
            // First transaction has already completed its rollback path.
        }

        required.executeWithoutResult(status -> {
            store.saveEvent("recovered");
        });
    }

    public void rollbackOuterButKeepIndependentAudit() {
        required.executeWithoutResult(outerStatus -> {
            store.saveEvent("outer");

            independent.executeWithoutResult(innerStatus -> {
                store.saveAudit("inner-audit");
            });

            outerStatus.setRollbackOnly();
        });
    }

    public void commitThenFailOutsideBoundary(String key) {
        required.executeWithoutResult(status -> {
            store.saveEvent(key);
        });

        // Chạy SAU khi callback transaction đã hoàn tất.
        // Giả lập external notification failure.
        throw new IllegalStateException("Notification failed after DB commit");
    }

    public boolean directThisCallStillRunsExplicitTemplate(String key) {
        return this.privateHelper(key);
    }

    private boolean privateHelper(String key) {
        return required.execute(status -> {
            store.saveEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });
    }

    public long countWithReadOnlyTemplate() {
        return readOnly.execute(status -> store.eventCount());
    }

    public ScopeObservation observeBoundary(String key) {
        boolean activeInside = required.execute(status -> {
            store.saveEvent(key);
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        });

        boolean activeAfter = TransactionSynchronizationManager
                .isActualTransactionActive();

        return new ScopeObservation(activeInside, activeAfter);
    }

    public void processChunksWithIndependentCommits(List<String> keys) {
        for (String key : keys) {
            try {
                required.executeWithoutResult(status -> {
                    store.saveEvent(key);
                    if ("reject".equals(key)) {
                        throw new IllegalStateException("Bad chunk");
                    }
                });
            } catch (IllegalStateException expected) {
                // Chỉ là ví dụ policy cho phép partial success.
                // Production cần ghi nhận lỗi và dùng idempotency keys.
            }
        }
    }
}
```

**Các điểm quan trọng trong class này:**

- `required` dùng propagation mặc định `REQUIRED`, manager được inject; tên transaction được cấu hình một lần trong constructor.
- `independent` là template **khác instance** với `REQUIRES_NEW`. Không đổi propagation trên shared template giữa các lần gọi vì có race nếu nhiều request dùng cùng service singleton.
- `readOnly` là template riêng với hint `readOnly=true`. Đây là hint/setting tùy manager, không phải security permission ngăn tuyệt đối mọi SQL write.
- `saveAndReturn` và `saveWithoutResult` có thể dùng ngay trong code bình thường, không cần transaction proxy intercept method.
- `checkedOperation` cố ý throw checked `IOException`, nên callback catch và **đánh dấu rollback-only** hoặc wrap `UncheckedIOException` để template rollback.
- `rollbackOuterButKeepIndependentAudit` demo **transaction độc lập**; không nên dùng nếu audit bắt buộc rollback cùng order.
- `commitThenFailOutsideBoundary` minh họa external side effect xảy ra **sau DB commit**, nên exception đến caller không thể đảo ngược DB transaction trước.
- `directThisCallStillRunsExplicitTemplate` chứng minh self-invocation là vấn đề của **annotation proxy**, không phải của lời gọi `TransactionTemplate` trực tiếp.
- `processChunksWithIndependentCommits` phù hợp **chỉ khi** nghiệp vụ cho phép partial results; transaction mới cho từng chunk chỉ khi không có outer transaction bao ngoài.

### 8.6. JUnit integration test: quan sát DB sau boundary

`src/test/java/com/example/boundary/BoundaryServiceIntegrationTest.java`:

```java
package com.example.boundary;

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
class BoundaryServiceIntegrationTest {
    @Autowired
    private BoundaryService service;

    @Autowired
    private EventStore store;

    @BeforeEach
    void reset() {
        store.clearAll();
    }

    @Test
    void executeReturnsAValueAfterItsTransactionScopeCompletes() {
        assertEquals("alpha", service.saveAndReturn("alpha"));
        assertEquals(List.of("alpha"), store.eventKeys());
        assertFalse(TransactionSynchronizationManager
                .isActualTransactionActive());
    }

    @Test
    void executeWithoutResultCommits() {
        service.saveWithoutResult("beta");

        assertEquals(List.of("beta"), store.eventKeys());
    }

    @Test
    void runtimeExceptionRollsBackAndReachesCaller() {
        assertThrows(IllegalStateException.class,
                () -> service.throwRuntimeAndRollback("runtime"));

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void rollbackOnlyCanReturnWithoutThrowing() {
        service.markRollbackOnlyWithoutThrowing("rejected");

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void checkedFailureCanReturnARejectedBusinessResult() {
        var outcome = service.checkedFailureAsBusinessResult("checked");

        assertFalse(outcome.accepted());
        assertEquals("INPUT_ERROR", outcome.message());
        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void wrappedCheckedExceptionTriggersRollback() {
        assertThrows(UncheckedIOException.class,
                () -> service.wrapCheckedFailureAndRollback("wrapped"));

        assertEquals(List.of(), store.eventKeys());
    }

    @Test
    void secondTransactionCanCommitAfterFirstRolledBack() {
        service.recoverAfterSeparateFailedTransaction();

        assertEquals(List.of("recovered"), store.eventKeys());
    }

    @Test
    void requiresNewAuditCanSurviveOuterRollback() {
        service.rollbackOuterButKeepIndependentAudit();

        assertEquals(List.of(), store.eventKeys());
        assertEquals(List.of("inner-audit"), store.auditKeys());
    }

    @Test
    void exceptionAfterExecuteDoesNotUndoEarlierCommit() {
        assertThrows(IllegalStateException.class,
                () -> service.commitThenFailOutsideBoundary("notified"));

        assertEquals(List.of("notified"), store.eventKeys());
    }

    @Test
    void callingPrivateHelperStillUsesTemplateBoundary() {
        assertTrue(service.directThisCallStillRunsExplicitTemplate("direct"));

        assertEquals(List.of("direct"), store.eventKeys());
    }

    @Test
    void readOnlyTemplateCanRead() {
        service.saveWithoutResult("a");
        service.saveWithoutResult("b");

        assertEquals(2L, service.countWithReadOnlyTemplate());
        assertEquals(List.of("a", "b"), store.eventKeys());
    }

    @Test
    void transactionContextIsActiveOnlyInsideCallbackInThisFixture() {
        var observation = service.observeBoundary("seen");

        assertTrue(observation.activeInside());
        assertFalse(observation.activeAfter());
        assertEquals(List.of("seen"), store.eventKeys());
    }

    @Test
    void chunkFailureDoesNotUndoPreviousOrLaterCommittedChunk() {
        service.processChunksWithIndependentCommits(
                List.of("first", "reject", "third"));

        assertEquals(List.of("first", "third"), store.eventKeys());
    }
}
```

**Có 13 integration test**, mỗi test có một `@BeforeEach` dọn hai bảng. Không đặt `@Transactional` lên chính test class; nếu làm vậy, các callback `REQUIRED` có thể tham gia test-managed transaction và không commit physical ngay ở `execute`, khiến test đọc dữ liệu trong cùng transaction rồi hiểu sai outcome.

### 8.7. Chạy như thế nào?

Trong thư mục `visible-transaction-boundaries`, với Gradle Wrapper:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu tự tạo các file nhưng chưa có wrapper, dùng Gradle tương thích đã cài để tạo wrapper hoặc chạy `gradle test`. Không chạy `javac` trực tiếp nếu chưa đưa Spring/JUnit/H2 vào classpath.

**Kết quả kỳ vọng:** 13 test pass trong fixture Spring Boot 3.3.5 + JDBC/H2. Đây là kết quả dự đoán từ code và transaction semantics; không có lời khẳng định đã chạy test tại đây. JUnit không hứa thứ tự các method hoặc stdout cố định. Đọc báo cáo tại `build/reports/tests/test/index.html` khi chạy thực tế.

| Kịch bản | Outcome caller | Dữ liệu sau khi service return/throw |
| --- | --- | --- |
| `saveAndReturn("alpha")` | Return `alpha` | Event `alpha` tồn tại |
| `saveWithoutResult("beta")` | Return bình thường | Event `beta` tồn tại |
| `throwRuntimeAndRollback` | `IllegalStateException` | Không có event |
| `markRollbackOnlyWithoutThrowing` | Return bình thường | Không có event |
| Checked failure → business result | `Outcome(false,"INPUT_ERROR")` | Không có event |
| Checked failure → wrapped unchecked | `UncheckedIOException` | Không có event |
| Step 1 rollback, step 2 transaction mới | Return bình thường | Chỉ có `recovered` |
| Outer rollback; audit `REQUIRES_NEW` commit | Return bình thường | Event trống, audit `inner-audit` tồn tại |
| DB commit rồi notification fail | `IllegalStateException` | Event `notified` **vẫn tồn tại** |
| Direct private-helper call | Return `true` về active transaction | Event `direct` tồn tại |
| Read-only template | Return số lượng `2` | Events `a`, `b` |
| Observe inside/after | `activeInside=true`, `activeAfter=false` | Event `seen` tồn tại |
| Chunk giữa bị lỗi | Return bình thường theo sample policy | Chỉ có `first`, `third` |

**Tại sao kết quả này có ý nghĩa?** Test gọi service **qua bean Spring** và sau khi service method return/throw mới dùng repository để đọc DB. Các method không nằm trong outer `@Transactional` nên callback `REQUIRED` tạo actual physical transactions riêng, còn `REQUIRES_NEW` audit thực sự độc lập với outer template. Từ đó test phân biệt được method-body return, callback return, manager completion và external failure.

## 9. Xử lý exception đúng cách ở ranh giới

### 9.1. Bắt ngoài `execute` khi cần chuyển transaction failure thành domain result

```java
public BookingResult tryBook(BookingCommand command) {
    try {
        return tx.execute(status -> {
            insertBooking(command);
            return BookingResult.confirmed();
        });
    } catch (DuplicateKeyException ex) {
        return BookingResult.seatAlreadyTaken();
    }
}
```

Đây là snippet minh họa, cần class/vars và imports tương ứng. Nó đặt catch **sau phạm vi `execute`**: nếu JDBC INSERT ném `DuplicateKeyException`, Spring sẽ đưa transaction qua rollback path trước khi caller catch. **Tuy nhiên**, chỉ ánh xạ duplicate thật của đúng business constraint sang `seatAlreadyTaken`, không catch mọi `DataIntegrityViolationException` rồi kết luận seat conflict.

Nếu method gọi đoạn trên **bên trong outer transaction đang active**, `tx.execute(REQUIRED)` chỉ tham gia physical transaction của outer. Catch exception ngoài `execute` của inner chưa có nghĩa transaction owner bên ngoài đã rollback; nếu inner đã đánh dấu rollback-only, outer có thể gặp `UnexpectedRollbackException`. Kiểm tra phạm vi transaction thật.

### 9.2. Rollback-only return là một outcome khác exception

```java
Decision decision = tx.execute(status -> {
    if (!policyAllows()) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
    insertAcceptedRecord();
    return Decision.ACCEPTED;
});
```

Là snippet minh họa. Nếu business contract dùng result type thay vì exception, caller phải kiểm tra `Decision`. Một successful Java return từ `execute` **không chứng minh write đã xảy ra**, vì callback có thể chủ động mark rollback-only. Chỉ một result rõ nghĩa mới tránh “return success nhưng transaction rollback”.

### 9.3. Checked exception từ callback

`TransactionCallback<T>.doInTransaction` không khai báo `throws IOException`. Vì vậy không thể ném checked IOException trực tiếp từ Java lambda trừ khi catch/wrap/chuyển thành loại exception unchecked. `UncheckedIOException` là lựa chọn chuẩn cho IOException; cho checked business exception khác, cân nhắc domain-specific runtime wrapper, kết quả nghiệp vụ hoặc một adapter chuyên trách.

Nếu muốn dùng declarative `rollbackFor=SomeCheckedException.class` vì API public đã khai báo checked exception, `@Transactional` có thể biểu đạt contract đó tự nhiên hơn.

### 9.4. Không làm side effect trong callback rồi nghĩ nó bị rollback

```java
tx.executeWithoutResult(status -> {
    repository.saveOrder();
    emailSender.sendConfirmation(); // KHÔNG nằm trong DB transaction
});
```

Snippet giả định. Nếu email đã gửi rồi `commit` thất bại, database không có order nhưng người nhận đã có email. Kể cả email được gọi “trước khi callback return”, DB manager vẫn không điều khiển email. Cần outbox/saga/compensation/idempotency theo yêu cầu.

### 9.5. Cẩn thận với lỗi ở commit

Nếu connection đứt đúng thời điểm commit, DB có thể đã nhận commit nhưng ứng dụng nhận exception. Đừng tự gọi rollback lần nữa trên status đã hoàn tất hoặc retry create-payment không idempotent. Với transaction nhiều bước, ghi business key và dùng cơ chế đối soát trước khi thử lại.

## 10. Test và debug boundary như thế nào?

### 10.1. Kiểm tra active transaction ở đúng giai đoạn

Trong callback imperative:

```java
boolean inside = tx.execute(status ->
        TransactionSynchronizationManager.isActualTransactionActive());
```

Ngoài callback:

```java
boolean after =
        TransactionSynchronizationManager.isActualTransactionActive();
```

Đây là snippets khi `tx` có sẵn. Trong fixture **không có outer transaction**, `inside` thường `true` và `after` `false`. Nếu có outer `REQUIRED`, `after` có thể vẫn `true`; không dùng quan sát đơn lẻ để tuyên bố DB đã commit.

### 10.2. Phân biệt ba thời điểm

```text
A — Callback returns
B — TransactionTemplate.execute returns to caller
C — Owner's physical transaction commits

Nếu template tạo physical transaction:
    A -> commit/cleanup -> B; C xảy ra trên đường giữa A và B.

Nếu template JOIN outer REQUIRED:
    A -> inner logical scope completion -> B -> ... -> C (sau đó)
```

Trong thực tế, nếu manager báo lỗi ở `commit`, B sẽ không là return thành công mà có thể ném exception. Nếu callback đánh dấu rollback-only, B có thể return bình thường sau rollback tùy status/manager. Vì vậy không nhầm **A, B và C**.

### 10.3. Checklist quan sát

1. Bean transaction manager nào được inject vào template?
2. Lời gọi `execute` có nằm trong outer `@Transactional` không?
3. Propagation là `REQUIRED` hay `REQUIRES_NEW`?
4. Đo scope bằng `status.isNewTransaction()` và các log/resource phù hợp, không chỉ tên method.
5. SQL đang dùng đúng datasource/connection được manager quản lý không?
6. Exception thoát callback hay bị bắt bên trong? Có `setRollbackOnly` không?
7. Có shared transaction bị đánh dấu global rollback-only từ một participant khác không?
8. Commit/rollback path có thật sự hoàn tất trước khi caller sử dụng kết quả?
9. Phép đo dữ liệu thực hiện **sau boundary**, không chỉ từ persistence context/test transaction?
10. Có side effect ngoài database cần outbox/idempotency không?

Trong test/development, có thể bật:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log hữu ích cho hướng chẩn đoán nhưng wording/ordering thay đổi theo framework/manager. Không dựa vào một câu log như “Committing” để khẳng định database durable; readback sau boundary quan trọng hơn. Tránh log parameters chứa thông tin nhạy cảm.

## 11. Những sai lầm phổ biến khi dùng TransactionTemplate

1. **Tưởng callback return là commit.** Transaction manager còn phải completion sau callback; nếu có outer transaction, physical commit có thể đến muộn.
2. **Tưởng mọi `execute` tạo transaction mới.** `REQUIRED` sẽ tham gia transaction có sẵn.
3. **Tưởng `setRollbackOnly()` luôn ném exception.** Với owner transaction, nó có thể rollback rồi return bình thường.
4. **Tưởng catch exception bên trong callback phục hồi transaction.** DB/ORM có thể đã ở trạng thái aborted/rollback-only.
5. **Đặt một template around cả remote API/network call.** Không rollback được external side effect; tăng lock/connection hold time.
6. **Tách hai SQL thuộc cùng invariant thành hai template calls.** Đánh mất atomicity nếu hai calls commit độc lập.
7. **Thay propagation của singleton template per request.** Configuration mutable dùng chung gây race; tạo instances cố định cho policies khác nhau.
8. **Dùng `TransactionTemplate` trong Reactor pipeline để thay reactive transaction.** Imperative ThreadLocal không bao trùm publisher lifecycle; dùng `TransactionalOperator`.
9. **Cho rằng `readOnly=true` cấm writes như ACL.** Là hint có thể được manager/driver/DB tối ưu hoặc enforce khác nhau.
10. **Cho rằng `timeout=5` hủy mọi tính toán CPU/HTTP đúng 5 giây.** Timeout phụ thuộc resource và manager, cần network timeout riêng.
11. **Cho rằng template giải quyết self-invocation cho annotation ở method khác.** Nó chỉ tạo boundary cho **callback** được gọi; các `@Transactional` khác vẫn cần proxy.
12. **Bắt mọi integrity exception rồi trả thành công.** Phải phân biệt constraint/tenant/idempotency, không bỏ qua lỗi hạ tầng không dự tính.
13. **Dùng `REQUIRES_NEW` cho audit mà không kiểm tra pool.** Outer giữ resource, inner cần thêm connection; starvation có thể xảy ra.
14. **Cho rằng callback có thể throw checked exception không catch.** Java signature của `TransactionCallback` không cho làm vậy.
15. **Gọi `new TransactionTemplate()` rồi quên manager.** Template cần `PlatformTransactionManager` được cấu hình trước khi `execute`.
16. **Bật transaction ở repository rồi không có business-level boundary.** Nhiều repository calls có thể commit rời rạc, làm vỡ invariant.
17. **Đọc state trong test `@Transactional` và gọi đó là commit.** Test-managed transaction có thể rollback cuối test.
18. **Cho rằng nếu gọi execute thành công thì chắc chắn external notification thành công.** Đó là một bước khác; thiết kế outbox/delivery phù hợp.

## 12. Bảng quyết định nhanh

| Yêu cầu của flow | Cách nên cân nhắc | Lý do |
| --- | --- | --- |
| Một method service chỉ làm một atomic DB unit | `@Transactional` | Rõ, ít phụ thuộc framework trong body |
| Method dài với network/file work, chỉ DB block cần atomic | `TransactionTemplate` | Boundary ngắn và hiển thị |
| Một số ít điểm cập nhật cần transaction ở app ít transaction | `TransactionTemplate` | Ít chi phí proxy/annotation cấu trúc hơn |
| Hàng nghìn items xử lý theo chunk, partial success hợp lệ | Nhiều `execute` với checkpoint/idempotency | Tách unit of work |
| Bước độc lập trong outer transaction | `REQUIRES_NEW` với template/annotation được thiết kế rõ | Physical transaction khác, pool phù hợp |
| Cần savepoint để rollback một phần trong JDBC | `NESTED` trên manager/DB hỗ trợ | Không đồng nhất với `REQUIRES_NEW` |
| Cần rollback vì business result không ném error | `TransactionStatus.setRollbackOnly()` | Quyết định hiển thị, outcome type rõ |
| Cần atomic DB + message delivery | DB transaction + transactional outbox | Không thể rollback HTTP/email/Kafka bằng JDBC |
| Cần thay đổi transaction theo tài nguyên reactive | `TransactionalOperator` | Lifecycle reactive/Context |
| Cần hàng loạt services thống nhất semantics | `@Transactional` và transaction infrastructure | Tách boilerplate khỏi business code |
| Cần thay đổi config theo request | Tạo template riêng/theo policy, không mutate shared singleton | Tránh race |
| Nhiều database cần global atomicity | Transaction coordination hoặc workflow/saga phù hợp | Không phải khả năng tự có của template |

## 13. Câu hỏi tự kiểm tra

**1. Khi nào nên dùng TransactionTemplate thay vì đặt `@Transactional` lên toàn bộ method?**

Khi chỉ một đoạn nhỏ trong workflow cần transaction, có I/O ngoài DB không nên giữ connection/lock, hoặc cần nhiều boundaries với chính sách rõ ràng. Nếu method đã là một atomic unit, annotation thường dễ đọc hơn.

**2. `tx.execute(...)` có luôn commit DB khi nó return không?**

Không. Nếu `REQUIRED` tham gia outer transaction, physical commit còn chờ outer owner. Nếu callback gọi `setRollbackOnly()`, template có thể return bình thường sau rollback. Nếu có lỗi commit, `execute` có thể ném exception.

**3. TransactionTemplate có giải quyết self-invocation không?**

Nó không dùng proxy cho chính lời gọi callback, nên gọi `tx.execute` từ private/helper method vẫn tạo transaction scope. Nhưng nó không làm các method có `@Transactional` khác tự nhiên được intercept khi gọi bằng `this`.

**4. Vì sao nên bắt exception ngoài `execute` khi muốn thử một transaction mới sau lỗi?**

Vì manager đã có cơ hội rollback/cleanup scope lỗi trước khi code xử lý và bắt đầu scope mới. Bắt SQL error ngay trong callback rồi tiếp tục có thể để resource aborted hoặc rollback-only.

**5. Java lambda `TransactionCallback` có thể ném checked IOException trực tiếp không?**

Không theo chữ ký callback thông thường. Cần catch và quyết định rollback-only/result hoặc wrap thành unchecked exception như `UncheckedIOException`.

**6. `status.setRollbackOnly()` có giống ném `RuntimeException` không?**

Không về API và control flow: cả hai có thể dẫn tới rollback, nhưng `setRollbackOnly` có thể return bình thường và caller phải đọc kết quả business rõ ràng.

**7. Dùng `REQUIRES_NEW` để ghi audit và outer rollback thì audit ra sao?**

Nếu inner transaction độc lập commit thành công, audit có thể còn khi outer rollback. Đây là thay đổi tính nguyên tử, không phù hợp nếu audit bắt buộc là cùng một đơn vị nghiệp vụ.

**8. Tại sao đoạn `remoteClient.send` sau `tx.execute` không được đảm bảo bởi DB transaction?**

Vì network call không tham gia local JDBC transaction. Nếu send fail, DB đã có thể commit; nếu cần delivery tin cậy cần outbox/idempotent dispatcher hoặc cơ chế tích hợp phù hợp.

**9. Vì sao không dùng cùng một instance template rồi set readOnly/propagation theo từng request?**

Template giữ mutable configuration trong singleton shared object; nhiều thread có thể đua nhau thay config. Dùng các instances cấu hình một lần.

**10. Read-only và timeout trên template có phải bảo đảm cứng?**

Không. Phụ thuộc resource manager/DB, propagation và statement processing. Read-only không phải authorization, timeout không phải bộ ngắt CPU/HTTP tổng quát.

**11. Một import có 3 chunks; chunk 1 commit, chunk 2 fail, chunk 3 commit. Có phải lỗi atomicity không?**

Phụ thuộc invariant. Nếu nghiệp vụ cho partial success và retry/checkpoint, đó có thể là thiết kế hợp lệ. Nếu yêu cầu all-or-nothing, phải đặt cả ba trong một transaction; chia thành nhiều `execute` là sai.

**12. Kỹ thuật nào xác minh boundary mạnh hơn việc nhìn log 'commit'?**

Integration test gọi service không nằm trong test-managed transaction và truy vấn DB sau khi `execute` hoàn tất, đồng thời kiểm tra exception/outcome/rollback-only theo contract.

## 14. Tham khảo chính thức

- [Spring Framework — Programmatic Transaction Management (TransactionTemplate và TransactionalOperator)](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Choosing Between Programmatic and Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-decl-vs-prog.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionOperations Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html)
- [Spring Framework — DefaultTransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html)
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — Transaction Propagation: REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
