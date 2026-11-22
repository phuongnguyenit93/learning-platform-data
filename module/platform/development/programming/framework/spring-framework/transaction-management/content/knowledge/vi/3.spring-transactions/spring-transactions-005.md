# TransactionStatus, rollback-only và thông tin trạng thái trong Spring

Trong Spring Framework, `TransactionStatus` là đối tượng mô tả **trạng thái của một phạm vi giao dịch đang được Spring điều phối**. Khi một service muốn kiểm tra transaction hiện tại, chủ động yêu cầu rollback, hoặc khi `TransactionTemplate` cần truyền trạng thái vào callback, đây là API cốt lõi. Để dùng đúng, phải phân biệt **phạm vi giao dịch (logical transaction scope)** với **giao dịch tài nguyên thật (physical/resource transaction)** và hiểu rằng một cờ trạng thái không tự biến thành hành động `commit()`/`rollback()` ngay tại dòng lệnh.

Bài này thuộc nhóm **Mô hình Spring** trong **Spring Framework – transaction-management**. Nội dung tập trung vào `TransactionStatus`, ý nghĩa của `rollback-only`, thời điểm hoàn tất transaction và cách đọc thông tin trạng thái trong giao dịch imperative. Phần reactive được đối chiếu ngắn ở cuối để tránh dùng nhầm API.

## 1. TransactionStatus nằm ở đâu trong mô hình transaction của Spring?

Với transaction imperative (thường là JDBC/JPA), Spring phân chia vai trò:

- **`TransactionDefinition`** mô tả yêu cầu *trước khi bắt đầu/tham gia*: propagation, isolation, timeout, read-only, tên giao dịch.
- **`PlatformTransactionManager`** lấy hoặc tạo transaction bằng `getTransaction(definition)` và điều phối kết thúc qua `commit(status)` hoặc `rollback(status)`.
- **`TransactionStatus`** là kết quả manager cung cấp cho **scope cụ thể**, cho biết scope mới hay tham gia, có savepoint không, đã bị đánh dấu rollback-only chưa, đã hoàn tất chưa; nó cũng cho phép đánh dấu rollback-only.
- **`TransactionInterceptor`** của AOP áp dụng `@Transactional`: lấy status, gọi method nghiệp vụ, rồi nhờ manager xử lý kết thúc.
- **`TransactionTemplate`** dùng cùng abstraction nhưng cho callback nhận `TransactionStatus` trực tiếp; template tự xử lý lifecycle và exception.
- **`TransactionSynchronizationManager`** cung cấp thông tin về transaction và đồng bộ tài nguyên **gắn với thread hiện tại** (đối với imperative transaction).

Luồng programmatic dùng `TransactionTemplate`:

```text
Caller
  |
  v
TransactionTemplate.execute(status -> ...)
  |-- PlatformTransactionManager.getTransaction(definition)
  |       \-- tạo/join transaction; trả TransactionStatus
  |
  |-- chạy callback, cho phép đọc status hoặc setRollbackOnly()
  |
  |-- callback trả về / ném exception
  |       \-- template yêu cầu manager commit / rollback
  |
  \-- resource cleanup, trả kết quả hoặc ném exception
```

Luồng declarative dùng AOP:

```text
Caller --> Spring proxy --> TransactionInterceptor
                                  |
                                  +--> TransactionManager.getTransaction(...)
                                  +--> gọi service method @Transactional
                                  +--> commit/rollback theo kết quả và cờ trạng thái
```

**`TransactionStatus` không phải `Connection`, `EntityManager`, cũng không phải bản ghi lịch sử giao dịch trong database.** Nó mô tả một scope do manager kiểm soát. SQL có chạy trên cùng connection hay không phụ thuộc vào cách data-access API tham gia transaction; việc ghi thực sự được commit hay rollback tùy tài nguyên tương ứng.

## 2. API của TransactionStatus: đọc đúng từng tín hiệu

Trong Spring Framework 6.1+, `TransactionStatus` mở rộng `TransactionExecution` và `SavepointManager`, đồng thời có `hasSavepoint()` và `flush()`. Đây là các method cần hiểu:

| Method | Nó trả lời câu hỏi gì? | Cách diễn giải đúng |
| --- | --- | --- |
| `hasTransaction()` | Scope này có transaction thực sự không? | Bao gồm scope mới **hoặc** scope tham gia transaction đã có; có từ Spring 6.1. |
| `isNewTransaction()` | Manager coi scope này là transaction mới không? | `false` thường nghĩa là đang tham gia scope ngoài, nhưng cũng có thể không có transaction thực sự; không dùng một mình để kết luận. |
| `isNested()` | Scope có chạy nested bên trong scope khác không? | Tín hiệu bổ sung trong Spring 6.1+; cần xem manager và propagation đang dùng. |
| `hasSavepoint()` | Scope có mang savepoint nội bộ không? | Hữu ích khi `NESTED` được triển khai bằng savepoint; không phải mọi transaction đều có savepoint. |
| `isReadOnly()` | Scope được khai báo read-only không? | Phản ánh đặc tính transaction; **không** chứng minh DB cấm mọi câu lệnh ghi. |
| `getTransactionName()` | Tên được khai báo cho scope là gì? | Có thể rỗng; với declarative transaction thường là tên đầy đủ của lớp và method; không phải transaction ID của DB. |
| `isRollbackOnly()` | Scope/tài nguyên đã bị đánh dấu chỉ có thể rollback chưa? | Có thể do code gọi `setRollbackOnly()` hoặc do hạ tầng đánh dấu. `true` không có nghĩa transaction đã rollback xong. |
| `setRollbackOnly()` | Chủ động yêu cầu scope không được commit thành công? | Đánh dấu cờ; **không** lập tức dừng method, hủy thay đổi hay gọi `rollback()` ngay ở dòng này. |
| `isCompleted()` | Scope này đã kết thúc chưa? | Chỉ `true` sau khi scope được manager xử lý hoàn tất; không cho biết kết thúc bằng commit hay rollback. |
| `flush()` | Yêu cầu flush session tới data store? | Chỉ là hint, có thể không làm gì; **flush không phải commit**. |
| `createSavepoint()`, `rollbackToSavepoint(...)`, `releaseSavepoint(...)` | Quản lý savepoint thủ công? | Là API của `SavepointManager`; chỉ dùng khi transaction manager/tài nguyên hỗ trợ. |

### Đọc một nhóm cờ, không đọc tách rời

Giả sử phương thức A bắt đầu `@Transactional(REQUIRED)` khi trước đó chưa có transaction, rồi gọi bean B cũng dùng `REQUIRED`:

```text
A @Transactional(REQUIRED)         B @Transactional(REQUIRED)
  hasTransaction() = true           hasTransaction() = true
  isNewTransaction() = true         isNewTransaction() = false
                 \                 /
                    một physical DB transaction
```

Cả A và B có thể dùng **hai đối tượng `TransactionStatus` thuộc hai logical scope**, dù cùng chia sẻ một transaction vật lý. Vì thế `isNewTransaction() == false` ở B **không** có nghĩa B nằm ngoài transaction.

Ngược lại, với `PROPAGATION_SUPPORTS` khi không có transaction đang hoạt động, một logical scope có thể chạy **không có physical transaction**. Khi đó `isNewTransaction()` cũng là `false`; ở phiên bản hỗ trợ, `hasTransaction()` mới giúp phân biệt rõ trường hợp này.

Không nên suy luận về ID connection, số transaction của DB, hay độ cô lập chỉ từ một boolean status.

## 3. Vòng đời: active, rollback-only và completed

Hãy tưởng tượng một scope `TransactionTemplate` tạo transaction mới:

```text
T0  getTransaction()       -> status mới, completed=false
T1  chạy câu UPDATE         -> thay đổi chưa chắc đã commit
T2  status.setRollbackOnly()-> rollbackOnly=true, completed=false
T3  callback return         -> template kết thúc scope
T4  manager xử lý rollback  -> thay đổi bị rollback
T5  cleanup                -> completed=true, resource được release
```

Ở T2, dòng code tiếp theo **vẫn tiếp tục chạy** nếu không có exception hoặc lệnh điều khiển luồng khác. Dữ liệu chưa bị rollback tức thời chỉ vì bạn gọi setter. Người đọc dễ nhầm:

- `isRollbackOnly() == true` **là quyết định/ràng buộc cho kết cục**, chưa phải bằng chứng rollback đã hoàn tất.
- `isCompleted() == false` khi đang ở bên trong callback/method là bình thường; nó không cho biết cuối cùng commit hay rollback.
- `isCompleted() == true` sau khi scope kết thúc chỉ nói scope **đã xong**, không cung cấp outcome commit/rollback. Không dùng nó thay audit log hoặc phép đọc dữ liệu sau commit.
- Sau khi kết thúc một scope, không tái sử dụng status để bắt đầu transaction mới hoặc gọi `commit()` lần nữa. Mỗi lần `getTransaction()` hoặc `TransactionTemplate.execute()` tạo/chọn status cho lượt xử lý tương ứng.

Một cách phân loại dễ nhớ:

```text
Transaction definition = tôi yêu cầu gì?
Transaction status     = Spring đang làm gì với scope này?
Transaction outcome    = transaction thực sự đã commit hay rollback?
```

Status cung cấp nhiều tín hiệu để suy luận quá trình xử lý, nhưng không phải một API truy vấn lịch sử đầy đủ về outcome.

## 4. Rollback-only: dấu cờ có hệ quả mạnh nhưng không phải lệnh rollback ngay

`status.setRollbackOnly()` là cách nói với hạ tầng: *phần việc do scope này quản lý không thể kết thúc bằng commit thành công theo cách thông thường*. Trong trường hợp transaction mới do `TransactionTemplate`/interceptor sở hữu, manager sẽ phát hiện cờ khi kết thúc và thực hiện rollback.

Điểm quan trọng: **Spring xử lý rollback-only tùy scope và propagation**. Không phải mọi scope cùng dùng một physical transaction lại có thể tự commit độc lập.

### 4.1. Transaction mới: đánh dấu rollback và return bình thường

```java
transactionTemplate.execute(status -> {
    jdbcTemplate.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");
    status.setRollbackOnly();
    return "callback hoàn thành";
});
```

Đây là **đoạn minh họa**, cần `transactionTemplate`, `jdbcTemplate` và bảng `wallet` có sẵn. Nếu template tạo mới một local transaction JDBC, câu `UPDATE` sẽ bị rollback khi template hoàn tất dù callback trả về bình thường. Chuỗi trả về **không phải** bằng chứng dữ liệu đã commit. Thông thường, `setRollbackOnly()` ngay trên status của scope mới là một quyết định rollback có chủ ý, không tự động phát sinh `UnexpectedRollbackException`.

Về thiết kế API, hãy biểu đạt kết quả nghiệp vụ rõ ràng: nếu operation không được ghi vì một điều kiện nào đó, trả kiểu kết quả có trạng thái thất bại, hoặc ném exception phù hợp. Đừng để caller hiểu lầm “method trả về bình thường” = “đã ghi DB”.

### 4.2. Scope REQUIRED bên trong đánh dấu rollback-only

Xét hai **Spring bean khác nhau**; caller vào `OuterService` qua proxy, rồi `OuterService` gọi `InnerService` qua proxy:

```java
@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void markFailure() {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void process() {
        // thao tác DB
        inner.markFailure();
        // method vẫn có thể chạy tiếp
    }
}
```

Đây là **snippet minh họa, không biên dịch độc lập**; cần imports Spring, bean wiring và DB operations tùy ứng dụng. Với manager dùng semantics chuẩn của `REQUIRED`:

1. `process()` mở một physical transaction và logical scope ngoài.
2. `markFailure()` tạo logical scope **tham gia** cùng physical transaction.
3. `setRollbackOnly()` ở scope trong làm transaction chung không thể commit bình thường.
4. Scope trong có thể trả về mà không ném exception ngay; ở ranh giới ngoài, khi caller mong commit nhưng kết quả thực tế phải rollback, Spring có thể ném **`UnexpectedRollbackException`**.

Điều này không phải rollback “ngẫu nhiên”: nó bảo vệ caller khỏi hiểu lầm rằng một commit thành công. Nếu bắt exception trong transaction ngoài rồi return, cũng không có cách đơn giản “xóa” cờ rollback-only để ép cùng physical transaction commit.

**Phân biệt nguyên nhân:** gọi `setRollbackOnly()` ở outer scope sở hữu transaction và biết rõ quyết định rollback khác với outer scope bị inner scope đánh dấu rollback-only ngoài ý muốn. `UnexpectedRollbackException` thường xuất hiện trong trường hợp thứ hai; chi tiết xử lý còn tùy transaction manager và cấu hình.

### 4.3. So sánh REQUIRED, REQUIRES_NEW và NESTED

| Propagation của scope bên trong | Quan hệ với transaction ngoài | Cờ rollback-only bên trong thường ảnh hưởng gì? |
| --- | --- | --- |
| `REQUIRED` | Cùng physical transaction | Có thể khiến toàn bộ transaction chung rollback; outer commit có thể ném `UnexpectedRollbackException`. |
| `REQUIRES_NEW` | Transaction vật lý **độc lập**, tạm gác scope ngoài | Rollback transaction bên trong không tự làm transaction ngoài rollback; xử lý exception và kết quả vẫn do code quyết định. |
| `NESTED` | Thường dùng savepoint trong **cùng** physical transaction nếu hỗ trợ | Có thể rollback về savepoint và cho phép outer tiếp tục; không tương đương `REQUIRES_NEW`. |

`REQUIRES_NEW` có thể phải lấy connection bổ sung trong lúc connection của outer vẫn được giữ; hãy tính đến dung lượng pool. `NESTED` phụ thuộc sự hỗ trợ savepoint của transaction manager và database, thường dùng với JDBC. Không suy ra mọi `JpaTransactionManager` hay resource đều hỗ trợ nested/savepoint như nhau.

`status.hasSavepoint()` phản ánh việc scope *được tạo với savepoint nội bộ*. Nó khác với việc code tùy ý đã gọi `status.createSavepoint()` trên cùng status. Cần kiểm tra hỗ trợ thực tế trước khi sử dụng API savepoint thủ công.

### 4.4. Cờ local và global trong Spring

Trong các implementation Spring thường gặp, có sự phân biệt:

- **Local rollback-only:** một logical scope tự đánh dấu rollback-only trên `TransactionStatus` của nó.
- **Global rollback-only:** transaction/resource đang tham gia bị manager hoặc tài nguyên bên dưới đánh dấu không thể commit.

`AbstractTransactionStatus.isRollbackOnly()` có thể xét cả hai trạng thái này. Vì vậy, một scope có thể thấy rollback-only dù bản thân code của scope đó chưa gọi setter. Đây là một lý do `isRollbackOnly()` cần được diễn giải theo **ngữ cảnh manager và propagation**, không coi nó là biến boolean riêng của service.

Không khuyến khích application code tìm cách thao tác trực tiếp các cờ nội bộ của implementation; sử dụng API `setRollbackOnly()` và để Spring quản lý kết thúc scope.

## 5. Lấy TransactionStatus bằng cách nào?

### 5.1. TransactionTemplate: cách programmatic dễ đọc nhất

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

String result = template.execute(status -> {
    // Chạy trong phạm vi transaction do template điều phối
    if (status.isRollbackOnly()) {
        return "rollback đã được yêu cầu";
    }
    // ... xử lý nghiệp vụ ...
    return "hoàn tất";
});
```

Đây là **snippet minh họa**; `transactionManager` phải là bean phù hợp, các thao tác DB thực tế cần dùng data-access API tham gia transaction. Callback nhận trực tiếp `TransactionStatus`, không cần tìm qua AOP. Khi callback return, template xử lý commit/rollback và resource cleanup.

Nếu cần hủy transaction nhưng không cần ném exception:

```java
template.executeWithoutResult(status -> {
    if (businessRuleFailed()) {
        status.setRollbackOnly();
        return;
    }
    writeBusinessData();
});
```

Đây là **snippet minh họa**; `businessRuleFailed()` và `writeBusinessData()` là method giả định. Callback `return;` thoát khỏi callback, còn template vẫn phải hoàn tất scope. `setRollbackOnly()` mới là tín hiệu yêu cầu rollback. Việc callback không trả giá trị không chứng minh transaction commit.

Khi dùng `TransactionTemplate`, không tự gọi `transactionManager.commit(status)`/`rollback(status)` trong callback: template đã sở hữu lifecycle.

### 5.2. Declarative @Transactional: truy cập status của AOP invocation hiện tại

Trong một method đang được `TransactionInterceptor` quản lý, Spring cung cấp:

```java
@Transactional
public void updateAccount(long id) {
    // ... cập nhật DB ...
    TransactionStatus status =
            TransactionAspectSupport.currentTransactionStatus();

    if (mustRejectOperation(id)) {
        status.setRollbackOnly();
    }
}
```

Đây là **snippet minh họa**; `mustRejectOperation` cần được định nghĩa. `TransactionAspectSupport.currentTransactionStatus()` lấy trạng thái của **AOP transaction boundary hiện tại**, kể cả khi boundary đó đang tham gia một outer transaction.

Không dùng API này như một phép hỏi trạng thái an toàn trong mọi đoạn code. Nếu không có AOP invocation context thích hợp, nó ném `NoTransactionException`. Một lời gọi self-invocation như `this.innerMethod()` không tạo thêm AOP boundary cho annotation của inner method; `currentTransactionStatus()` có thể vẫn lấy status **của outer boundary** nếu đang ở trong một outer invocation, chứ không biến inner method thành scope độc lập.

Trong thiết kế thông thường, ưu tiên `@Transactional` và quy tắc exception/`rollbackFor`. Đánh dấu rollback bằng tay hữu ích khi **cần chủ động hủy nhưng vẫn muốn xử lý hoặc chuyển đổi kết quả**, song nó làm business code gắn trực tiếp với Spring API.

### 5.3. PlatformTransactionManager: chủ động sở hữu toàn bộ lifecycle

```java
DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
TransactionStatus status = manager.getTransaction(definition);

try {
    performBusinessOperations();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

Đây là **snippet minh họa** cần `manager`, `performBusinessOperations()` và các imports. `getTransaction()` chọn tạo/tham gia theo `definition`; code phải đảm bảo kết thúc scope đúng một lần. Kiểm tra `isCompleted()` tránh cố rollback lại một scope đã kết thúc, chẳng hạn sau lỗi phát sinh ngay trong `commit()`. Cách code trực tiếp này dễ sai và khó xử lý hơn `TransactionTemplate`; chỉ nên dùng khi thực sự cần kiểm soát trình tự ở tầng hạ tầng.

**Không trộn quyền sở hữu:** Nếu AOP/template đã quản lý transaction, đừng tự `commit()` hay `rollback()` status lấy qua API của nó. Ngược lại, nếu tự dùng manager, phải chủ động xử lý các đường đi exception và cleanup.

## 6. “Thông tin trạng thái” từ TransactionStatus khác gì TransactionSynchronizationManager?

Với **imperative transaction**, `TransactionSynchronizationManager` lưu thông tin đồng bộ và tài nguyên liên quan đến execution **theo thread**. Các method tiêu biểu:

```java
boolean actual =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean synchronization =
        TransactionSynchronizationManager.isSynchronizationActive();
String name =
        TransactionSynchronizationManager.getCurrentTransactionName();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();
```

Đây là **snippet minh họa**; cần import `org.springframework.transaction.support.TransactionSynchronizationManager` và một ngữ cảnh Spring phù hợp.

| Câu hỏi | API phù hợp |
| --- | --- |
| Callback/template hoặc AOP scope này có đánh dấu rollback-only không? | `TransactionStatus.isRollbackOnly()` |
| Scope do manager coi là mới hay join? | `TransactionStatus.isNewTransaction()`, xem thêm `hasTransaction()` |
| Scope đã hoàn tất chưa? | `TransactionStatus.isCompleted()` |
| Thread hiện tại có physical/resource transaction Spring đang active? | `TransactionSynchronizationManager.isActualTransactionActive()` |
| Spring transaction synchronization đang active? | `TransactionSynchronizationManager.isSynchronizationActive()` |
| Tên/read-only/isolation hiện được gắn với thread? | Các getter tương ứng của `TransactionSynchronizationManager` |

Điểm khác rất quan trọng: **`isSynchronizationActive()` có thể `true` trong khi `isActualTransactionActive()` là `false`**, ví dụ một scope chỉ kích hoạt transaction synchronization nhưng không có transaction vật lý. Do đó không thể dùng synchronization active để kết luận thao tác DB chắc chắn được rollback.

`TransactionAspectSupport.currentTransactionStatus()` phản ánh **AOP boundary cục bộ**. `TransactionSynchronizationManager` mô tả metadata ngữ cảnh thực thi đang gắn với thread, có thể phản ánh transaction tài nguyên bên ngoài mà scope cục bộ tham gia. Các API này phục vụ mục đích khác nhau; không dùng cái này thay thế cái kia một cách máy móc.

Đối với reactive transaction, Spring dùng **Reactor Context**, không dựa vào thread-bound `TransactionSynchronizationManager` imperative. Với R2DBC, tương ứng thường là `ReactiveTransactionManager`, `TransactionalOperator`, `ReactiveTransaction` và reactive transaction synchronization API. Thread switching không tự mang transaction imperative sang thread mới; cũng không suy từ `ThreadLocal` ra trạng thái của một reactive chain.

## 7. `isRollbackOnly`, exception và flush phối hợp ra sao?

### 7.1. Exception không đồng nghĩa với một cờ đã được set ngay lập tức

Ở `@Transactional` mặc định của Spring, unchecked `RuntimeException` và `Error` thường kích hoạt rollback khi **exception thoát ra khỏi transactional invocation**. Checked exception mặc định không tự kích hoạt rollback, trừ khi có rule phù hợp như `rollbackFor`.

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    // IOException thoát khỏi method cũng yêu cầu rollback transaction
}
```

Đây là **snippet minh họa**; cần import `java.io.IOException`. Nếu code bắt và nuốt exception rồi return bình thường, interceptor có thể đi theo nhánh commit khi chưa có dấu rollback-only. Không thể chỉ nhìn stack trace hay một câu `catch` để kết luận DB đã rollback.

`setRollbackOnly()` là **lựa chọn chủ động** khi muốn rollback dù exception không thoát ra. Nó không thay thế việc báo cho caller biết kết quả nghiệp vụ. Việc kiểm tra `status.isRollbackOnly()` trước hay sau khi một ngoại lệ được xử lý tùy trạng thái mà transaction manager/resource đã đánh dấu; đừng dựa vào việc cờ luôn chuyển ngay tại một thời điểm cố định.

### 7.2. Flush không phải commit

`status.flush()` có thể yêu cầu JPA/Hibernate session đẩy SQL đang chờ xuống database, hoặc là no-op tùy manager. Ngay cả khi SQL đã được flush:

1. transaction vẫn có thể chưa commit;
2. `status.setRollbackOnly()` vẫn có thể khiến thay đổi bị rollback;
3. dữ liệu quan sát từ connection khác phụ thuộc isolation và DB;
4. lỗi khi flush có thể làm transaction bị đánh dấu rollback-only.

Đừng dùng `flush()` để “thử commit” hoặc làm cờ rollback-only biến mất. Nếu cần kiểm tra commit thực tế, hãy quan sát **sau khi boundary kết thúc** và dùng tài nguyên/transaction phù hợp.

### 7.3. `isCompleted()` không phải “thành công”

Một status đã hoàn tất bằng rollback cũng trả `isCompleted() == true`. Trong callback/template, trước khi template kết thúc, `isCompleted()` thường là `false` dù nghiệp vụ đã chạy xong tất cả câu lệnh. Muốn biết thao tác có hiệu lực, cần chính sách kết quả/exception rõ ràng và kiểm chứng hậu điều kiện sau transaction; `isCompleted()` một mình không đủ.

## 8. Ví dụ Java 17 chạy độc lập: ba cách rollback-only xuất hiện

Ví dụ này dùng **Java 17**, **Spring Boot 3.3.5**, **Spring JDBC** và **H2 in-memory**. Nó minh họa:

1. `TransactionTemplate` tạo transaction mới, callback nhận `TransactionStatus`, gọi `setRollbackOnly()` rồi trả về bình thường.
2. Bean `@Transactional` lấy `TransactionStatus` qua AOP và chủ động đánh dấu rollback-only.
3. Inner bean `REQUIRED` tham gia transaction ngoài, tự đánh dấu rollback-only, làm outer commit báo `UnexpectedRollbackException`.

Điều kiện chạy: **JDK 17+**, **Maven 3.9+**, có thể tải dependency Maven. Các class service được khai báo `public static` bên trong application để ví dụ chỉ cần một file Java; chúng vẫn là Spring-managed beans nhờ `@Service`.

Cấu trúc:

```text
tx-status-demo/
├── pom.xml
└── src/main/java/demo/TxStatusDemoApplication.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>tx-status-demo</artifactId>
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

File `src/main/java/demo/TxStatusDemoApplication.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxStatusDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxStatusDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager,
            FlaggingService flagging,
            OuterService outer) {

        return args -> {
            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            System.out.println("START=" + balance(jdbc));

            // Trường hợp 1: callback sở hữu status mới.
            TransactionTemplate template = new TransactionTemplate(manager);
            AtomicReference<TransactionStatus> saved = new AtomicReference<>();

            template.execute(status -> {
                saved.set(status);
                jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");

                System.out.println("TEMPLATE before: new=" + status.isNewTransaction()
                        + ", rollback=" + status.isRollbackOnly()
                        + ", completed=" + status.isCompleted());

                status.setRollbackOnly();
                System.out.println("TEMPLATE after mark: rollback="
                        + status.isRollbackOnly());
                return null;
            });

            System.out.println("TEMPLATE after scope: completed="
                    + saved.get().isCompleted()
                    + ", balance=" + balance(jdbc));

            // Trường hợp 2: status từ AOP invocation.
            flagging.debitAndMarkRollback();
            System.out.println("AOP after scope: balance=" + balance(jdbc));

            // Trường hợp 3: REQUIRED scope bên trong tham gia transaction ngoài.
            try {
                outer.updateThenCallInner();
            } catch (UnexpectedRollbackException expected) {
                System.out.println("OUTER: UnexpectedRollbackException");
            }

            System.out.println("END=" + balance(jdbc));
        };
    }

    private static int balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1",
                Integer.class);
    }

    @Service
    public static class FlaggingService {
        private final JdbcTemplate jdbc;

        public FlaggingService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void debitAndMarkRollback() {
            jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id = 1");
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println("AOP inside: active=" + status.hasTransaction()
                    + ", new=" + status.isNewTransaction());

            status.setRollbackOnly();
        }
    }

    @Service
    public static class InnerService {
        @Transactional
        public void markRollback() {
            TransactionStatus status =
                    TransactionAspectSupport.currentTransactionStatus();

            System.out.println("INNER: new=" + status.isNewTransaction());
            status.setRollbackOnly();
        }
    }

    @Service
    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void updateThenCallInner() {
            jdbc.update("UPDATE wallet SET balance = balance - 20 WHERE id = 1");
            inner.markRollback();
            // Outer method return bình thường, nhưng transaction đã bị đánh dấu.
        }
    }
}
```

Chạy tại thư mục `tx-status-demo`:

```bash
mvn -q spring-boot:run
```

Các dòng **do chương trình tự in ra** (không tính startup log Maven/Spring Boot) là:

```text
START=100
TEMPLATE before: new=true, rollback=false, completed=false
TEMPLATE after mark: rollback=true
TEMPLATE after scope: completed=true, balance=100
AOP inside: active=true, new=true
AOP after scope: balance=100
INNER: new=false
OUTER: UnexpectedRollbackException
END=100
```

Phân tích theo thứ tự:

- **TEMPLATE:** `TransactionTemplate` tạo transaction mới, nên `new=true`; trước khi đánh dấu, `rollback=false`, `completed=false`. Sau setter, `rollback=true` ngay trong callback, nhưng callback vẫn return bình thường. Template hoàn tất scope bằng rollback; `isCompleted()` của status đã lưu là `true` và số dư vẫn 100.
- **AOP:** `FlaggingService` là Spring bean được gọi từ runner qua proxy, nên `currentTransactionStatus()` lấy được status của transactional invocation đang hoạt động. Gọi setter làm phần trừ 10 không được commit; số dư ngoài scope vẫn 100.
- **INNER/OUTER:** `OuterService` đã mở transaction vật lý, `InnerService` được gọi qua một proxy riêng và tham gia nó (`new=false`). Inner đánh dấu rollback-only. Outer return bình thường nhưng nỗ lực commit ở ranh giới ngoài không thể thành công; Spring báo `UnexpectedRollbackException`. Cuối cùng số dư vẫn là 100.

Demo cố tình dùng **một** H2 datasource và manager, không có thread switching, không có `REQUIRES_NEW`, để quan sát từng trạng thái theo cách xác định. Ứng dụng thực tế cần mô hình lỗi nghiệp vụ rõ ràng, giới hạn transaction và kiểm soát đồng thời phù hợp; ví dụ này chỉ minh họa trạng thái và lifecycle.

## 9. Tình huống dễ nhầm và cách xử lý

### Lỗi 1 — Đọc `isNewTransaction() == false` rồi kết luận không có transaction

**Sai vì:** inner `REQUIRED` tham gia outer transaction cũng trả `false`. Trong Spring 6.1+, xem thêm `hasTransaction()`. Khi chẩn đoán imperative runtime, có thể đối chiếu `TransactionSynchronizationManager.isActualTransactionActive()`.

### Lỗi 2 — Tưởng gọi `setRollbackOnly()` là dữ liệu lập tức bị undo

**Sai vì:** setter chỉ yêu cầu kết cục rollback. Mã tiếp theo vẫn có thể chạy, các resource và DB lock có thể còn bị giữ tới khi boundary thật sự kết thúc. Nếu một nhánh nghiệp vụ không nên tiếp tục, hãy điều khiển luồng rõ ràng (`return`, exception, result type).

### Lỗi 3 — Bắt exception trong `@Transactional` rồi tưởng Spring tự rollback

**Sai vì:** interceptor dựa vào exception thoát khỏi method và quy tắc rollback; exception đã bị nuốt có thể khiến method return bình thường. Đổi chính sách với `rollbackFor`, để exception thoát ra, hoặc chủ động đánh dấu rollback-only khi thật sự cần.

### Lỗi 4 — Inner REQUIRED hủy, outer cố commit rồi bị `UnexpectedRollbackException`

Đây thường là hậu quả dự kiến của nhiều logical scope cùng dùng physical transaction. Hãy xác định rõ scope nào quyết định kết cục nghiệp vụ; đừng bắt rồi cố “reset” rollback-only. Nếu bắt buộc tách transaction độc lập, cân nhắc `REQUIRES_NEW` cùng tác động tài nguyên và tính nhất quán.

### Lỗi 5 — Gọi `currentTransactionStatus()` ở bất cứ method nào

API này phụ thuộc **AOP transaction invocation context**. Một helper gọi ngoài invocation tương ứng có thể ném `NoTransactionException`; phương thức được tự gọi bằng `this.method()` không tạo thêm proxy boundary như nhiều người nghĩ. Với luồng programmatic, callback `TransactionTemplate` đã có status được truyền vào, không cần tìm qua AOP.

### Lỗi 6 — Nhầm `flush()` hoặc `isCompleted()` với commit

`flush()` có thể chỉ đẩy thao tác tới DB trước commit hoặc không làm gì. `isCompleted()` không chứa outcome success/failure. Muốn chứng minh commit, kiểm tra hậu điều kiện sau boundary cùng cơ chế kiểm thử thích hợp.

### Lỗi 7 — Mang `TransactionStatus` sang thread khác hoặc giữ làm state trong singleton

Status thuộc một invocation/scope, không phải trạng thái dùng chung cho cả service. Trong imperative Spring transaction, tài nguyên thường gắn với thread; `@Async`, `CompletableFuture` hay `new Thread` không tự kế thừa DB transaction đang hoạt động. Không cache status vào field của singleton để một request khác đọc.

### Lỗi 8 — Dùng chung transaction manager cho mọi loại resource theo giả định

`isRollbackOnly() == true` chỉ phản ánh phạm vi manager đang điều phối. Nó **không** khiến HTTP request, email, file write hay một datasource độc lập tự rollback theo database transaction. Nếu nhiều resource cần phối hợp, cần chiến lược giao dịch hoặc bù trừ cụ thể.

## 10. Kiểm thử và quan sát thực tế

Để kiểm chứng thay vì chỉ đọc log:

1. Tạo DB test với dữ liệu ban đầu đã commit, ví dụ `wallet.balance=100`.
2. Gọi public transactional service method **qua Spring proxy**.
3. Trong method cập nhật dữ liệu rồi `setRollbackOnly()` hoặc phát sinh unchecked exception.
4. Để scope kết thúc. Truy vấn dữ liệu từ caller ngoài scope; so sánh số dư với ban đầu.
5. Với hai bean `REQUIRED`, kiểm tra inner có `isNewTransaction()==false` và outer có thể nhận `UnexpectedRollbackException`.
6. Trường hợp kiểm thử bằng Spring Test có `@Transactional` đặt trên test method, lưu ý test framework thường tự rollback khi kết thúc test. Đừng lấy rollback của **test method** làm bằng chứng service tự rollback đúng khi chạy thực tế.

Có thể bật log chọn lọc trong môi trường development:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log hỗ trợ quan sát begin/join/rollback/commit và binding. Tuy vậy, **log transaction không thay thế phép xác nhận dữ liệu sau transaction**. Không bật logging quá chi tiết trong production nếu không có lý do vì chi phí và dữ liệu có thể xuất hiện trong log.

Một mô hình test nhỏ và hữu ích:

| Trường hợp | Kỳ vọng cuối scope |
| --- | --- |
| `TransactionTemplate`: callback return bình thường, không set cờ | Commit nếu không có lỗi/tình trạng rollback-only nào khác. |
| `TransactionTemplate`: callback gọi `setRollbackOnly()` | Rollback những thay đổi cùng transaction. |
| `@Transactional`: unchecked exception thoát khỏi method | Rollback theo quy tắc mặc định. |
| `@Transactional`: exception được catch và return bình thường | Có thể commit nếu transaction chưa bị đánh dấu rollback-only. |
| Inner `REQUIRED` đánh dấu rollback-only, outer vẫn cố commit | Toàn bộ physical transaction rollback; outer có thể nhận `UnexpectedRollbackException`. |
| Inner `REQUIRES_NEW` rollback, outer không yêu cầu rollback | Transaction ngoài có thể commit độc lập, tùy logic/exception của caller. |

## 11. Tự kiểm tra kiến thức

**Câu 1.** Một method có `@Transactional(REQUIRED)` đang tham gia transaction của caller. `status.isNewTransaction()` là `false`. Có chắc không có transaction DB?

**Giải thích:** không. Đây là trường hợp bình thường khi tham gia physical transaction hiện có; `hasTransaction()` mới giúp nhận biết có transaction thực sự hay không ở Spring 6.1+.

**Câu 2.** Trong callback, `status.setRollbackOnly()` rồi `return 42`. Callback có chạy hết không, và caller có thể nhận `42` dù update bị rollback?

**Giải thích:** có thể. Setter không tự ném exception hay dừng method; template hoàn tất scope bằng rollback, còn kết quả callback có thể vẫn được trả về. Vì vậy contract nghiệp vụ cần diễn đạt được việc không commit.

**Câu 3.** `status.isCompleted()` đã thành `true`. Có thể khẳng định transaction đã commit không?

**Giải thích:** không. `isCompleted()` cũng `true` sau rollback; đây là cờ lifecycle của scope.

**Câu 4.** `isSynchronizationActive()` là `true` nhưng `isActualTransactionActive()` là `false`. Có mâu thuẫn không?

**Giải thích:** không. Spring có thể đang quản lý synchronization mà không có physical transaction, ví dụ một số trường hợp `SUPPORTS`. Hai API trả lời hai câu hỏi khác nhau.

**Câu 5.** Một inner `REQUIRED` đặt rollback-only, outer method không ném exception. Outer có chắc commit được không?

**Giải thích:** không. Hai logical scope có thể chung physical transaction; outer commit có thể gặp `UnexpectedRollbackException` khi transaction buộc phải rollback.

**Câu 6.** Dùng `status.flush()` rồi `status.setRollbackOnly()`. Các SQL đã flush có bắt buộc được lưu lại không?

**Giải thích:** không. Flush và commit là hai hành động khác nhau; thay đổi đã flush nhưng chưa commit vẫn có thể bị rollback.

## 12. Ghi nhớ nhanh

- `TransactionDefinition` = *yêu cầu transaction*.
- `TransactionStatus` = *trạng thái/điều khiển của scope transaction hiện tại*.
- `hasTransaction()` = *có actual transaction không?*; `isNewTransaction()` = *scope này được manager coi là mới không?*
- `setRollbackOnly()` = *yêu cầu không commit thành công*; `isRollbackOnly()` = *đã có dấu rollback-only chưa?*
- `isCompleted()` = *scope đã kết thúc chưa?*, **không** đồng nghĩa *đã commit*.
- `TransactionTemplate` hoặc AOP interceptor sở hữu việc kết thúc scope; code nghiệp vụ không tự commit status do chúng quản lý.
- Với `REQUIRED`, nhiều logical scope có thể chia sẻ một physical transaction; inner đánh dấu rollback-only có thể làm outer commit thất bại.
- `TransactionSynchronizationManager` là thông tin transaction/resource **theo thread** của mô hình imperative; reactive transaction cần API theo Reactor Context.

Khi gỡ lỗi, nên tự hỏi theo thứ tự: **Đây là status của scope nào? Scope có thực sự tham gia transaction không? Ai đã đánh dấu rollback-only? Ai sở hữu kết thúc? Điều gì được commit/rollback ở tài nguyên thật?**

## Tài liệu Spring chính thức

- [Transaction Management — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Transaction Management — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Transaction Management — Declarative Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [API — TransactionStatus, Spring Framework 6.2](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [API — TransactionExecution, Spring Framework 6.2](https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/transaction/TransactionExecution.html)
- [API — TransactionAspectSupport, Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html)