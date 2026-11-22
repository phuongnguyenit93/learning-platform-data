# Quản lý commit, rollback và ngoại lệ ở từng giai đoạn bằng API giao dịch trực tiếp của Spring

## 1. Mục tiêu: kiểm soát một transaction từ lúc bắt đầu đến lúc kết thúc

Trong Spring Framework, ngoài cách khai báo `@Transactional`, ứng dụng có thể chủ động điều khiển giao dịch bằng API imperative:

- `PlatformTransactionManager`: bắt đầu/tham gia, commit và rollback một transaction.
- `TransactionDefinition`: mô tả propagation, isolation, timeout, read-only và tên transaction.
- `TransactionStatus`: trạng thái riêng của scope, gồm thông tin transaction mới hay tham gia, rollback-only, completed, savepoint khi hỗ trợ.
- `TransactionTemplate`: bao gói các bước begin, thực thi callback, commit/rollback và xử lý exception, để giảm boilerplate.

Đề bài **“Quản lý commit, rollback và ngoại lệ ở từng giai đoạn”** yêu cầu phân biệt những thời điểm rất dễ xử lý sai:

1. **Trước khi có `TransactionStatus`**: `getTransaction(...)` có thể thất bại khi tìm/bắt đầu transaction; không có status hợp lệ để rollback.
2. **Trong thân nghiệp vụ**: lỗi có thể là checked exception, unchecked exception hoặc `Error`. Với API trực tiếp, **chính code của bạn** quyết định gọi `commit` hay `rollback`; đừng áp máy móc default rollback rule của `@Transactional`.
3. **Khi commit**: commit có thể thành công, phát hiện rollback-only hoặc ném lỗi từ flush, synchronization, database hay transaction manager. Theo contract `PlatformTransactionManager`, sau khi **đã gọi `commit(status)` và lời gọi đó kết thúc (kể cả kết thúc bằng exception)**, transaction status đã hoàn tất/được dọn. **Không gọi `rollback(status)` để “sửa” một commit đã ném lỗi**.
4. **Khi rollback**: rollback cũng có thể ném `TransactionException`/system error. Cần không đánh mất dấu vết exception gốc và không dùng lại status đã hoàn tất.
5. **Sau completion**: chỉ tiến hành bước hậu giao dịch dựa trên kết quả hoàn tất thực tế. SQL UPDATE đã chạy không đồng nghĩa transaction đã commit.

Mấu chốt của bài: **mỗi transaction status chỉ được hoàn tất một lần** bằng một lời gọi commit hoặc rollback phù hợp; còn exception ở giai đoạn hoàn tất phải được xử lý **khác** exception từ business code.

## 2. Bốn đối tượng và trách nhiệm trong Spring imperative transaction API

| Đối tượng/API | Công việc | Điều không nên nhầm |
| --- | --- | --- |
| `TransactionDefinition` | Định nghĩa propagation, isolation, timeout, read-only, name | Chỉ là yêu cầu; không phải một transaction đang chạy |
| `PlatformTransactionManager.getTransaction(def)` | Trả `TransactionStatus` đại diện scope mới/tham gia theo definition | Không phải lúc nào cũng mở physical transaction mới |
| `TransactionStatus` | Cho biết `isNewTransaction()`, `isRollbackOnly()`, `isCompleted()`; cho phép `setRollbackOnly()` | Không phải object dùng lại để begin/commit nhiều lần |
| `PlatformTransactionManager.commit(status)` | Hoàn tất scope theo trạng thái, có thể rollback nếu rollback-only | “Gọi commit” không bảo đảm DB đã commit |
| `PlatformTransactionManager.rollback(status)` | Yêu cầu rollback scope; nếu tham gia transaction ngoài có thể chỉ đánh dấu rollback-only | Không phải mọi rollback đều rollback một physical transaction riêng |
| `TransactionTemplate.execute(...)` | Chạy callback trong transaction, lo lifecycle và exception handling | Không cho business code tự commit cùng status của callback |
| `JdbcTransactionManager` / `DataSourceTransactionManager` | Triển khai JDBC transaction manager cho `DataSource` | Không dùng thay `ReactiveTransactionManager` cho luồng R2DBC |

Ví dụ khởi tạo một definition:

~~~java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("checkout-manual");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15);
def.setReadOnly(false);
~~~

Đây là trích đoạn cần imports `org.springframework.transaction.support.DefaultTransactionDefinition` và `org.springframework.transaction.TransactionDefinition`; không phải chương trình độc lập. Các thuộc tính **isolation/timeout** thường chỉ áp dụng khi manager **thực sự bắt đầu transaction mới**, chứ không tự sửa physical transaction đang có khi `REQUIRED` tham gia.

### 2.1. Chọn đúng manager và tài nguyên

Với Spring JDBC, code truy cập dữ liệu nên dùng `JdbcTemplate`/`DataSourceUtils` cùng `DataSource` mà transaction manager quản lý. Nếu một DAO tự tạo `new Connection` từ nguồn khác hoặc dùng một `DataSource` khác, các câu SQL ấy có thể không nằm trong transaction đang điều khiển.

Nếu có nhiều manager, cần inject hoặc qualifier đúng bean; `PlatformTransactionManager` là abstraction **imperative**. Với reactive database flow, dùng `ReactiveTransactionManager`/`TransactionalOperator` và Reactor subscriber context, không dùng nguyên mẫu imperative dựa trên thread-local.

## 3. Toàn bộ lifecycle được chia thành những giai đoạn nào?

### Giai đoạn A — Lấy hoặc bắt đầu transaction

~~~java
TransactionStatus status = txManager.getTransaction(def);
~~~

Với `PROPAGATION_REQUIRED`, manager tham gia transaction sẵn có hoặc mở transaction vật lý mới. Một manager JDBC có thể lấy connection, tắt auto-commit, cấu hình isolation/read-only và bind resource vào thread.

**Lỗi ở giai đoạn A** thường thuộc nhóm:

- `CannotCreateTransactionException`: không thể bắt đầu transaction (ví dụ không lấy được connection).
- `IllegalTransactionStateException`: definition mâu thuẫn với tình trạng hiện tại, ví dụ `MANDATORY` khi không có transaction.
- `InvalidIsolationLevelException`/lỗi backend khác: yêu cầu không được manager/tài nguyên hỗ trợ.
- `TransactionException` nói chung: lỗi khi tìm hoặc tạo status.

Khi `getTransaction(...)` **ném exception trước khi trả status**, application **chưa sở hữu một status hợp lệ**. Không viết `txManager.rollback(status)` trong một catch khi biến `status` chưa được cấp, và không tự tạo một status giả. Hãy để manager xử lý cleanup phù hợp của pha begin và báo lỗi cho caller.

### Giai đoạn B — Thực thi nghiệp vụ trong scope

Sau khi có status, ứng dụng chạy SQL và logic nghiệp vụ. Có ba hướng:

- **Thành công:** yêu cầu commit sau khi body kết thúc bình thường.
- **Thất bại cần hủy:** yêu cầu rollback, rồi chuyển tiếp exception gốc (hoặc lỗi nghiệp vụ có nghĩa).
- **Xử lý lỗi và muốn chọn kết quả khác:** một policy nghiệp vụ **tường minh** có thể quyết định commit dù lỗi checked đã được bắt, hoặc đánh dấu rollback-only và trả kết quả. Không được để việc nuốt exception vô tình quyết định kết quả.

Exception từ SQL có thể là Spring `DataAccessException` (unchecked); `IOException` hoặc exception nghiệp vụ checked là loại khác. **Khi dùng `PlatformTransactionManager` trực tiếp, annotation rollbackFor không tự chạy trên đoạn code này**: chính application chịu trách nhiệm gọi completion method đúng.

### Giai đoạn C — Quyết định completion

Chỉ **sau body** mới chọn một trong:

~~~java
txManager.commit(status);   // Khi muốn commit và chưa hoàn tất.
~~~

hoặc:

~~~java
txManager.rollback(status); // Khi muốn rollback và chưa hoàn tất.
~~~

Hai dòng trên là **hai lựa chọn loại trừ nhau**, không chạy nối tiếp trên cùng `TransactionStatus`. `commit` cũng có thể thực thi rollback nếu status đã `setRollbackOnly()` hoặc physical transaction bị đánh dấu global rollback-only.

### Giai đoạn D — Commit/rollback, synchronization và cleanup

Trong JDBC, quá trình hoàn tất có thể bao gồm callbacks before-commit/before-completion, flush, commit hoặc rollback của physical connection, after-commit/after-completion và cleanup/release connection. Trình tự/hành vi cụ thể tùy manager, resource và việc đang tham gia transaction hay mở mới.

**Điểm bất biến của API:** sau khi lời gọi `PlatformTransactionManager.commit(status)` hoàn tất, **dù return bình thường hay ném exception**, transaction được coi là completed/cleaned up về phía manager; không được rollback lại status đó. Tương tự, không tiếp tục commit một status đã rollback.

## 4. Sơ đồ quyết định ở từng stage

~~~mermaid
flowchart TD
    A["Nhận yêu cầu nghiệp vụ"] --> B["txManager.getTransaction(definition)"]
    B --> C{"Begin thành công?"}
    C -->|"Không"| D["Báo lỗi begin<br/>KHÔNG có status để rollback"]
    C -->|"Có"| E["Có TransactionStatus"]
    E --> F["Thực thi nghiệp vụ"]
    F --> G{"Body có lỗi cần rollback?"}
    G -->|"Có"| H["txManager.rollback(status)"]
    H --> I{"Rollback thành công?"}
    I -->|"Có"| J["Chuyển tiếp lỗi gốc"]
    I -->|"Không"| K["Báo lỗi rollback;<br/>giữ original như cause/suppressed"]
    G -->|"Không"| L["txManager.commit(status)"]
    L --> M{"Commit thành công?"}
    M -->|"Có"| N["Hoàn tất theo kết quả transaction"]
    M -->|"Không"| O["Báo lỗi commit;<br/>KHÔNG rollback lại status"]
    N --> P["Trả kết quả / tiếp tục sau completion"]
~~~

**Không áp dụng sơ đồ một cách máy móc cho case “body có lỗi nhưng nghiệp vụ chủ động cho phép commit”**: cần nêu rõ policy và chỉ commit khi tài nguyên vẫn hợp lệ. Tương tự, một `commit(status)` trên **status rollback-only** có thể dẫn đến rollback; không nên gọi kết quả “COMMITTED” chỉ vì không có exception.

## 5. Mẫu code an toàn cho API trực tiếp: commit nằm ngoài catch của body

Một mẫu quan trọng là **không đặt `commit(status)` bên trong cùng `try` có `catch` gọi rollback**, bởi vì catch ấy có thể bắt cả exception từ commit và cố rollback lại status đã completed.

### 5.1. Sai: catch bao trùm commit rồi rollback lần hai

~~~java
// ANTI-PATTERN — không dùng trong ứng dụng:
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
    manager.commit(status); // Có thể ném TransactionException ở completion.
} catch (RuntimeException ex) {
    manager.rollback(status); // SAI nếu exception đến từ commit!
    throw ex;
}
~~~

Đây là đoạn minh họa chưa có imports/definitions. Theo contract `PlatformTransactionManager`, nếu `commit` ném lỗi, transaction đã được dọn; `rollback(status)` sau đó có thể ném `IllegalTransactionStateException` (“already completed”) và che mất nguyên nhân thật của commit failure.

### 5.2. Đúng: chỉ bao body bằng catch rollback, commit sau đó

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
} catch (RuntimeException | Error original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
    throw original;
}
manager.commit(status); // Nằm NGOÀI catch của business body.
~~~

Đây cũng là mẫu trích đoạn; cần định nghĩa manager, definition và helper. Nó minh họa một chiến lược **best effort bảo toàn exception gốc**: khi rollback thất bại, ghi nhận rollback error thành suppressed exception rồi vẫn ném original. Tùy yêu cầu sản phẩm, có thể chọn exception rollback làm chính và gắn original vào cause; điểm bắt buộc là **không làm mất cả hai**.

Nếu `getTransaction(def)` ném lỗi, code chưa vào `try`, không gọi rollback. Nếu `commit(status)` ném lỗi, code không quay vào catch đang gọi rollback. Nếu body lỗi, callback rollback được gọi **một lần** trước khi rethrow.

**Không tự cho rằng chỉ RuntimeException mới cần rollback.** Mẫu bắt `RuntimeException | Error` là policy phổ biến. Nếu business API dùng checked exception làm lỗi cần rollback, phải catch loại checked ấy hoặc dùng cơ chế callback/lambda xử lý rõ ràng.

## 6. Checked exception: ở API trực tiếp, quyết định rollback không tự động

Với declarative `@Transactional`, default rollback rule thường rollback với `RuntimeException`/`Error` và không tự rollback checked `Exception` (có thể tùy chỉnh). Nhưng với direct API:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    performJdbcWrites();
    readExternalFile(); // có thể ném IOException
} catch (IOException ex) {
    manager.rollback(status); // Chính bạn chọn rollback khi IOException xảy ra.
    throw ex;
} catch (RuntimeException | Error ex) {
    manager.rollback(status);
    throw ex;
}
manager.commit(status);
~~~

Đây là trích đoạn minh họa, không phải file chạy độc lập. Với policy nghiệp vụ cần atomicity, `IOException` dù checked vẫn là lý do rollback vì application **đã chủ động gọi rollback**.

Ngược lại, đôi khi một checked exception có nghĩa “ghi dữ liệu xong nhưng cần thông báo warning”. Nếu xác nhận các thao tác DB đã hợp lệ và tài nguyên vẫn có thể commit, code có thể **catch checked exception, lưu lại để báo caller, gọi commit, rồi mới throw**. Khi ấy caller thấy exception nhưng dữ liệu **đã commit** — phải ghi rõ contract nghiệp vụ và test kết quả, không chọn ngẫu nhiên.

**Cảnh báo:** “Checked exception thì commit” không phải quy tắc cưỡng chế của `PlatformTransactionManager`. Trạng thái transaction có thể rollback-only hoặc DB đã từ chối SQL, khiến commit không thể thành công dù bạn muốn.

## 7. TransactionStatus: các trạng thái phải đọc đúng

Một vài API của `TransactionStatus` và `TransactionExecution` hữu ích:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `isNewTransaction()` | Scope có đại diện transaction vật lý mới? | Với `REQUIRED` tham gia thì thường false |
| `isRollbackOnly()` | Transaction/status bị đánh dấu rollback-only? | True không đồng nghĩa rollback đã hoàn tất |
| `setRollbackOnly()` | Chủ động yêu cầu rollback khi scope hoàn tất | Không tự rollback ngay tại lời gọi này |
| `isCompleted()` | Scope status đã hoàn tất theo manager? | Không dùng status để commit/rollback lần hai |
| `hasSavepoint()` | Status có savepoint? | Cần manager/driver hỗ trợ nested/savepoint |
| `flush()` | Gợi ý flush resource bên dưới nếu được hỗ trợ | Không tương đương commit vật lý |

**Phân biệt rollback-only với rollback đã thực thi:**

~~~java
TransactionStatus status = manager.getTransaction(definition);
status.setRollbackOnly();
manager.commit(status);  // Có thể thực hiện rollback thay vì commit.
~~~

Nếu scope là **transaction mới** và code chủ động đánh dấu local rollback-only, `commit(status)` có thể rollback **mà không nhất thiết ném `UnexpectedRollbackException`**. Ngược lại, nếu một inner `REQUIRED` đã đánh dấu physical transaction chung global rollback-only rồi outer vẫn cố commit, outer có thể nhận `UnexpectedRollbackException`. Hai tình huống có cùng hướng “không commit” nhưng khác về kỳ vọng của outer.

Đừng dùng `isCompleted()` để tự suy ra “database commit thành công”: nó chỉ nói transaction **status đã hoàn tất**. Một status đã rollback vẫn completed, và một commit thất bại vẫn cần cleanup.

## 8. Failure ở giai đoạn bắt đầu, khi body, tại commit và tại rollback

| Giai đoạn | Ví dụ exception | Status đang có? | Điều cần làm |
| --- | --- | --- | --- |
| `getTransaction` | `CannotCreateTransactionException` do pool hết connection | Chưa có status trả về | Báo lỗi begin; không rollback một status không tồn tại |
| Body/SQL | `DataAccessException`, `IllegalArgumentException`, `IOException` | Có status | Áp policy: rollback hoặc xử lý rõ ràng; không “nuốt” lỗi vô ý |
| `commit(status)` | `UnexpectedRollbackException`, `TransactionSystemException`, lỗi flush trước commit | Status sẽ được hoàn tất/cleanup | Không gọi rollback cùng status sau commit failure |
| `rollback(status)` | `TransactionSystemException`/resource failure | Status đang được hoàn tất | Không lặp rollback; giữ lại cả lỗi gốc và lỗi rollback |
| Sau commit | Lỗi HTTP/Kafka/email riêng | DB transaction có thể đã commit | Không thể đảo ngược commit bằng rollback cùng status; dùng outbox/compensation |
| Dùng status lần 2 | `IllegalTransactionStateException` “already completed” | Completed | Sửa cấu trúc code: một completion cho một status |

### 8.1. Commit failure không luôn có cùng ý nghĩa

Khi `commit(status)` ném exception, nguồn lỗi có thể thuộc nhiều nhóm:

- **Before-commit/flush exception:** callback hoặc ORM flush lỗi trước khi DB commit; manager thường rollback hoặc xử lý tương ứng.
- **Global rollback-only:** một participating logical scope đã làm physical transaction không còn có thể commit, dẫn tới `UnexpectedRollbackException` khi outer cố commit.
- **Database commit/system failure:** connection hỏng, network không rõ kết quả, transaction coordinator báo heuristic. Kết quả vật lý có thể **không chắc chắn** từ phía client nếu liên lạc mất đúng lúc.
- **After-commit callback failure:** callback sau khi DB commit có thể gặp lỗi; một exception được truyền ra caller lúc này **không đồng nghĩa** dữ liệu chưa commit.

Vì vậy đừng log tất cả commit exceptions là “rolled back” nếu chưa có bằng chứng từ manager/tài nguyên. Đặc biệt trong failure network, không retry một giao dịch ghi thiếu idempotency key/unique invariant.

### 8.2. Rollback failure không cho phép giả định thành công

Nếu business exception xảy ra, application gọi `rollback(status)` nhưng rollback cũng ném lỗi, cần ghi nhận cả hai. Không dùng chính status đã thất bại để lặp commit/rollback tùy tiện. Trong hệ thống có external effects, transaction manager không tự hủy email, HTTP call hoặc Kafka publish đã thực hiện.

`TransactionSystemException` có thể giữ application exception trong một số trường hợp; nhưng không phụ thuộc việc exception nào cũng có `getCause()` hữu ích. Bảo toàn original và rollback failure trong log/exception chain là trách nhiệm thiết kế.

## 9. TransactionTemplate: lựa chọn được Spring khuyến nghị cho imperative flows

Spring thường khuyến nghị `TransactionTemplate` thay vì viết trực tiếp boilerplate `getTransaction → try/catch → commit/rollback` nếu ứng dụng chỉ cần một phạm vi transaction rõ ràng.

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.executeWithoutResult(status -> {
    jdbc.update("UPDATE ledger SET balance = balance + 10 WHERE id = 1");
});
~~~

Đây là trích đoạn trong bean đã inject `PlatformTransactionManager` và `JdbcTemplate`. Template lo lifecycle và exception handling:

- Callback **return bình thường**: template cố hoàn tất theo hướng commit.
- Callback ném **RuntimeException** hoặc **Error**: template rollback rồi chuyển tiếp exception, trừ khi rollback itself lỗi.
- Callback gọi `status.setRollbackOnly()` rồi return: template yêu cầu rollback khi scope kết thúc mà callback không cần ném exception.
- Callback muốn trả giá trị: dùng `template.execute(status -> result)`.
- Callback không trực tiếp gọi `manager.commit(status)` hay `manager.rollback(status)` trên status mà template đang sở hữu, vì template đã chịu trách nhiệm completion.

`TransactionTemplate` implements `TransactionOperations`; các instance dùng chung có thể thread-safe **khi cấu hình không thay đổi trong lúc đang sử dụng**. Nếu cần propagation/timeout/isolation khác nhau, tạo template riêng cho từng policy thay vì mutate shared instance đồng thời.

### 9.1. Checked exception trong callback

`TransactionCallback<T>` không khai báo checked exception tùy ý như `IOException` trong chữ ký lambda. Nếu thao tác có checked exception, ứng dụng phải:

- Bắt bên trong callback rồi `status.setRollbackOnly()` và trả kết quả lỗi phù hợp.
- Hoặc wrap thành một unchecked exception có cause, để template rollback theo convention.
- Hoặc sử dụng API trực tiếp khi cần giữ nguyên checked exception và policy rõ ràng.

Đừng catch `IOException` rồi return một DTO thành công mà quên đánh dấu rollback-only nếu nghiệp vụ cần atomicity.

### 9.2. Programmatic TransactionTemplate cũng tuân theo propagation

~~~java
TransactionTemplate independent = new TransactionTemplate(manager);
independent.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
independent.executeWithoutResult(status -> {
    // Work ở physical transaction độc lập với outer nếu có.
});
~~~

Đây là trích đoạn minh họa. `REQUIRES_NEW` vẫn suspend outer và có thể cần connection bổ sung từ pool khi outer giữ một connection. Template không biến hai physical transactions thành một chỉ vì cả hai cùng chạy trên một thread.

## 10. REQUIRED tham gia transaction: rollback của inner không phải rollback riêng

Một thay đổi quan trọng khi lập trình trực tiếp là **không phải status nào cũng đại diện physical transaction mới**. Ví dụ:

~~~java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

TransactionStatus outer = manager.getTransaction(def); // Mở T1 khi chưa có.
TransactionStatus inner = manager.getTransaction(def); // Join T1.

manager.rollback(inner); // Thường chỉ đánh dấu T1 rollback-only.
manager.commit(outer);   // Có thể ném UnexpectedRollbackException.
~~~

Trích đoạn này giả định cùng thread, cùng manager và không có lỗi khác. `rollback(inner)` trên participating status **không** ngay lập tức rollback riêng các SQL của inner rồi để outer commit bình thường. Với các manager dựa trên `AbstractPlatformTransactionManager` ở chế độ mặc định, participating scope thất bại có thể đánh dấu **global rollback-only**. Khi outer cố commit T1, Spring rollback toàn bộ và ném `UnexpectedRollbackException` để tránh trả “success” giả.

Nếu inner thực sự cần rollback/commit độc lập, `REQUIRES_NEW` tạo physical transaction riêng. Nếu cần rollback một phần nhưng vẫn cùng physical transaction, `PROPAGATION_NESTED` có thể dùng JDBC savepoint khi được hỗ trợ; không suy rằng nested có commit độc lập.

## 11. REQUIRES_NEW, connection pool và sự cố ở stage begin

Một outer transaction đã dùng JDBC connection C1 có thể tiếp tục **giữ C1** khi bị suspend. Inner `REQUIRES_NEW` cần một connection C2 từ pool để mở physical transaction mới.

- Nếu pool tối đa **một** connection và outer đang giữ C1, inner có thể chờ `connectionTimeout` rồi lỗi **ngay tại `getTransaction`**; lúc đó chưa có inner `TransactionStatus` để rollback.
- Nếu inner thành công rồi commit, outer rollback sau đó **không hủy** inner đã commit.
- Nếu outer giữ lock trên hàng mà inner muốn cập nhật, inner có thể chờ database lock ngay cả khi pool có đủ C2.
- Đừng thay mọi `REQUIRED` thành `REQUIRES_NEW` chỉ để tránh ảnh hưởng rollback-only mà không xem atomicity, lock và connection budget.

Chọn propagation theo nghiệp vụ, kiểm thử trên DB/pool gần production, theo dõi active/idle/pending connection và thời gian giữ transaction.

## 12. Synchronization callback: quan sát trước/sau completion đúng chỗ

Một số hệ thống cần thêm hành vi sau commit hoặc sau rollback, ví dụ cập nhật cache, phát thông báo, ghi metric. Spring cung cấp `TransactionSynchronizationManager` và `TransactionSynchronization` khi transaction synchronization đang active.

Trích đoạn minh họa **bên trong transaction imperative có synchronization active**:

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Chỉ sau khi transaction commit thành công.
            }

            @Override
            public void afterCompletion(int status) {
                if (status == STATUS_COMMITTED) {
                    // Transaction hoàn tất với trạng thái committed.
                } else if (status == STATUS_ROLLED_BACK) {
                    // Transaction hoàn tất với trạng thái rolled back.
                } else {
                    // STATUS_UNKNOWN: manager không xác nhận kết quả chắc chắn.
                }
            }
        }
    );
}
~~~

Cần imports `org.springframework.transaction.support.TransactionSynchronizationManager` và `org.springframework.transaction.support.TransactionSynchronization`. Đây là code minh họa, không là class chạy độc lập.

**Tránh bốn ngộ nhận:**

1. `beforeCommit` có thể chạy **trước** khi DB thực sự commit; không nên gửi sự kiện không thể hoàn tác ở đó chỉ vì callback được gọi.
2. `afterCommit` chạy sau commit transaction chính, nhưng các resource cũ có thể vẫn gắn với thread trong một số pha cleanup. Nếu callback phải ghi DB bằng transaction riêng, dùng scope `REQUIRES_NEW` có chủ đích, không ngầm kỳ vọng một commit thứ hai.
3. Một exception sau DB commit không thể được “sửa” bằng rollback status đã hoàn tất.
4. `afterCompletion(STATUS_UNKNOWN)` đòi hỏi xử lý bất định theo cơ chế của manager. Đừng tuyên bố chắc chắn dữ liệu đã commit hay rollback khi thực sự không biết.

Với event/message cần bảo đảm phối hợp DB, cân nhắc **transactional outbox** thay vì gửi trực tiếp trong trước-commit hoặc after-commit mà không có cơ chế retry/idempotency.

## 13. Ví dụ chạy độc lập: Java 17+, Spring Boot, JDBC, H2

### 13.1. Mục đích của ví dụ

Ứng dụng CLI dùng **Spring Boot 3.3.5 / Spring Framework 6.1.x**, Java 17+, Maven, `JdbcTransactionManager`, `JdbcTemplate` và H2 in-memory. Nó không cần HTTP server hoặc database bên ngoài. Một bảng `ledger` có hai dòng ban đầu: id 1 có balance **100**, id 2 có balance **1000**.

Chương trình lần lượt minh họa:

1. Commit một transaction thủ công.
2. Business RuntimeException kích hoạt **rollback thủ công**.
3. Checked `IOException` kích hoạt **rollback thủ công** vì ứng dụng chọn policy ấy.
4. Checked `IOException` được giữ để báo caller nhưng ứng dụng **chủ động commit** dữ liệu hợp lệ.
5. `setRollbackOnly` rồi gọi commit: transaction mới rollback thay vì commit.
6. `TransactionTemplate` commit callback thành công.
7. Template rollback khi callback ném unchecked exception.
8. Template rollback khi callback return bình thường nhưng setRollbackOnly.
9. Inner `REQUIRED` tham gia physical transaction ngoài; rollback inner dẫn đến `UnexpectedRollbackException` khi outer cố commit.
10. Inner `REQUIRES_NEW` commit riêng trên hàng id 2, sau đó outer rollback phần của mình trên hàng id 1.

Không phụ thuộc vào việc self-invocation được AOP intercept: các transaction **đều được mở bằng API trực tiếp**, và `CommandLineRunner` không gắn `@Transactional`.

### 13.2. Cấu trúc ba tệp

~~~text
programmatic-tx-demo/
├── pom.xml
└── src/main/java/example/programmatictx/
    ├── ProgrammaticTxDemoApplication.java
    └── TxScenarios.java
~~~

### 13.3. pom.xml

~~~xml
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

    <groupId>example</groupId>
    <artifactId>programmatic-tx-demo</artifactId>
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
~~~

Không cần `spring-boot-starter-aop` vì ví dụ này **dùng API giao dịch trực tiếp**, không yêu cầu `@Transactional` proxy.

### 13.4. src/main/java/example/programmatictx/ProgrammaticTxDemoApplication.java

~~~java
package example.programmatictx;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootApplication
public class ProgrammaticTxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProgrammaticTxDemoApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TxScenarios cases) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO ledger (id, balance) VALUES (?, ?)", 1, 100
            );
            jdbc.update(
                "INSERT INTO ledger (id, balance) VALUES (?, ?)", 2, 1000
            );
            System.out.println("START=" + balances(jdbc));

            cases.manualCommit();
            System.out.println("AFTER_MANUAL_COMMIT=" + balances(jdbc));

            try {
                cases.manualRuntimeRollback();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_RUNTIME=" + ex.getMessage());
            }
            System.out.println("AFTER_RUNTIME_ROLLBACK=" + balances(jdbc));

            try {
                cases.manualCheckedRollback();
            } catch (IOException ex) {
                System.out.println("CAUGHT_CHECKED_ROLLBACK=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED_ROLLBACK=" + balances(jdbc));

            try {
                cases.manualCheckedCommit();
            } catch (IOException ex) {
                System.out.println("CAUGHT_CHECKED_COMMIT=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED_COMMIT=" + balances(jdbc));

            cases.manualMarkRollbackOnly();
            System.out.println("AFTER_MARK_ONLY=" + balances(jdbc));

            cases.templateCommit();
            System.out.println("AFTER_TEMPLATE_COMMIT=" + balances(jdbc));

            try {
                cases.templateRuntimeRollback();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_TEMPLATE=" + ex.getMessage());
            }
            System.out.println("AFTER_TEMPLATE_RUNTIME=" + balances(jdbc));

            cases.templateMarkRollbackOnly();
            System.out.println("AFTER_TEMPLATE_MARK=" + balances(jdbc));

            try {
                cases.participatingRollback();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CAUGHT_UNEXPECTED=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_PARTICIPATING=" + balances(jdbc));

            cases.independentRequiresNew();
            System.out.println("AFTER_REQUIRES_NEW=" + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer one = jdbc.queryForObject(
            "SELECT balance FROM ledger WHERE id = ?", Integer.class, 1
        );
        Integer two = jdbc.queryForObject(
            "SELECT balance FROM ledger WHERE id = ?", Integer.class, 2
        );
        return one + "/" + two;
    }
}
~~~

### 13.5. src/main/java/example/programmatictx/TxScenarios.java

~~~java
package example.programmatictx;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class TxScenarios {

    private final JdbcTemplate jdbc;
    private final PlatformTransactionManager manager;
    private final TransactionTemplate template;

    public TxScenarios(
            JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.manager = manager;
        this.template = new TransactionTemplate(manager);
    }

    private TransactionStatus begin(String name) {
        DefaultTransactionDefinition def = new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        return manager.getTransaction(def);
    }

    private void add(int id, int delta) {
        jdbc.update(
            "UPDATE ledger SET balance = balance + ? WHERE id = ?",
            delta, id
        );
    }

    private void failChecked() throws IOException {
        throw new IOException("checked-failed");
    }

    // Nếu rollback lỗi, giữ original và bổ sung rollbackFailure.
    // Không được gọi rollback lặp lại trên status ấy.
    private void rollbackPreserving(
            TransactionStatus status, Throwable original) {
        try {
            manager.rollback(status);
        } catch (TransactionException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
    }

    // Case 1: hoàn tất thành công.
    public void manualCommit() {
        TransactionStatus status = begin("manualCommit");
        try {
            add(1, 10);
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // Ngoài catch để không rollback sau commit error.
    }

    // Case 2: RuntimeException -> ứng dụng chủ động rollback.
    public void manualRuntimeRollback() {
        TransactionStatus status = begin("manualRuntimeRollback");
        try {
            add(1, 20);
            throw new IllegalStateException("runtime-failed");
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
    }

    // Case 3: checked IOException -> ứng dụng CHỌN rollback.
    public void manualCheckedRollback() throws IOException {
        TransactionStatus status = begin("manualCheckedRollback");
        try {
            add(1, 30);
            failChecked();
        } catch (IOException original) {
            rollbackPreserving(status, original);
            throw original;
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status);
    }

    // Case 4: checked IOException được coi là warning:
    // ứng dụng chủ động commit rồi mới ném checked exception.
    public void manualCheckedCommit() throws IOException {
        TransactionStatus status = begin("manualCheckedCommit");
        IOException pending = null;
        try {
            add(1, 40);
            failChecked();
        } catch (IOException ex) {
            pending = ex;
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // Nếu commit lỗi, IOException không che commit failure.
        if (pending != null) {
            throw pending;
        }
    }

    // Case 5: local rollback-only, không phải đã rollback ngay lập tức.
    public void manualMarkRollbackOnly() {
        TransactionStatus status = begin("manualMarkRollbackOnly");
        try {
            add(1, 50);
            status.setRollbackOnly();
            System.out.println("MARK_ONLY=" + status.isRollbackOnly());
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // Manager rollback thay cho commit.
    }

    // Case 6: template tự commit callback hoàn tất bình thường.
    public void templateCommit() {
        template.executeWithoutResult(status -> add(1, 60));
    }

    // Case 7: template rollback khi callback ném unchecked exception.
    public void templateRuntimeRollback() {
        template.executeWithoutResult(status -> {
            add(1, 70);
            throw new IllegalStateException("template-failed");
        });
    }

    // Case 8: callback return bình thường nhưng rollback-only.
    public void templateMarkRollbackOnly() {
        template.executeWithoutResult(status -> {
            add(1, 80);
            status.setRollbackOnly();
        });
    }

    // Case 9: hai logical REQUIRED scopes trên cùng physical transaction.
    public void participatingRollback() {
        TransactionStatus outer = begin("outerRequired");
        try {
            add(1, 90);
            TransactionStatus inner = begin("innerRequired");
            try {
                add(1, 100);
            } catch (RuntimeException | Error original) {
                rollbackPreserving(inner, original);
                throw original;
            }
            manager.rollback(inner); // Mark global rollback-only, không commit.
            add(1, 5);
            System.out.println(
                "OUTER_ROLLBACK_ONLY=" + outer.isRollbackOnly()
            );
        } catch (RuntimeException | Error original) {
            rollbackPreserving(outer, original);
            throw original;
        }
        manager.commit(outer); // Outer muốn commit, nhưng shared T1 bị rollback.
    }

    // Case 10: inner physical transaction commit độc lập.
    public void independentRequiresNew() {
        TransactionStatus outer = begin("outerForNew");
        try {
            add(1, 1);
            DefaultTransactionDefinition def =
                new DefaultTransactionDefinition();
            def.setName("innerRequiresNew");
            def.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
            );
            TransactionStatus inner = manager.getTransaction(def);
            try {
                add(2, 5); // Hàng khác để tránh row-lock dependency.
            } catch (RuntimeException | Error original) {
                rollbackPreserving(inner, original);
                throw original;
            }
            manager.commit(inner); // Hoàn tất status inner, resume outer.
        } catch (RuntimeException | Error original) {
            rollbackPreserving(outer, original);
            throw original;
        }
        manager.rollback(outer); // Hủy +1 trên id=1, giữ +5 đã commit id=2.
    }
}
~~~

**Điểm kiểm tra quan trọng trong code:**

- `begin(name)` luôn gọi `getTransaction` **trước** `try/catch` xử lý business body; nếu begin lỗi, không có status để rollback.
- Tại các method hoàn tất bằng commit, `manager.commit(status)` nằm **sau** catch rollback của body.
- Với lỗi từ body, `rollbackPreserving` giữ original làm exception chính và thêm rollbackFailure vào `getSuppressed()` nếu rollback itself lỗi. Đây là một policy logging có chủ đích, không bắt buộc là policy cho mọi ứng dụng.
- `manualCheckedRollback()` và `manualCheckedCommit()` minh họa **hai quyết định nghiệp vụ khác nhau** trước cùng checked exception. Không phải Spring tự phân loại checked exception rồi commit trong API trực tiếp.
- `template.*` dùng chung `TransactionTemplate` có cấu hình bất biến sau constructor.
- `participatingRollback()` tạo inner `REQUIRED` bằng API trực tiếp **trên cùng thread và manager**, vì vậy manager nhận transaction đang có; rollback(inner) đặt shared rollback-only.
- `independentRequiresNew()` mở inner T2, commit nó, rồi rollback outer T1. Hai hàng khác nhau để tránh việc T2 chờ lock của T1.

### 13.6. Cách chạy

Tại thư mục chứa `pom.xml`, với JDK 17+ và Maven:

~~~bash
mvn -q spring-boot:run
~~~

Spring Boot/HikariCP có thể in log riêng. Phần dưới chỉ gồm **stdout do ứng dụng in**, với H2 và transaction manager trong project này:

~~~text
START=100/1000
AFTER_MANUAL_COMMIT=110/1000
CAUGHT_RUNTIME=runtime-failed
AFTER_RUNTIME_ROLLBACK=110/1000
CAUGHT_CHECKED_ROLLBACK=checked-failed
AFTER_CHECKED_ROLLBACK=110/1000
CAUGHT_CHECKED_COMMIT=checked-failed
AFTER_CHECKED_COMMIT=150/1000
MARK_ONLY=true
AFTER_MARK_ONLY=150/1000
AFTER_TEMPLATE_COMMIT=210/1000
CAUGHT_TEMPLATE=template-failed
AFTER_TEMPLATE_RUNTIME=210/1000
AFTER_TEMPLATE_MARK=210/1000
OUTER_ROLLBACK_ONLY=true
CAUGHT_UNEXPECTED=UnexpectedRollbackException
AFTER_PARTICIPATING=210/1000
AFTER_REQUIRES_NEW=210/1005
~~~

### 13.7. Giải thích từng mốc số dư và completion

| Case | SQL trong transaction | Completion | Số dư sau |
| --- | --- | --- | --- |
| Thủ công thành công | id1 +10 | `commit(status)` thành công | 110 / 1000 |
| RuntimeException từ body | id1 +20 | `rollback(status)`, rethrow original | 110 / 1000 |
| IOException, chọn rollback | id1 +30 | `rollback(status)`, rethrow checked error | 110 / 1000 |
| IOException, chọn commit | id1 +40 | `commit(status)` rồi rethrow checked warning | 150 / 1000 |
| Mark rollback-only | id1 +50 | `commit(status)` thấy local rollback-only và rollback | 150 / 1000 |
| Template success | id1 +60 | Template commit | 210 / 1000 |
| Template runtime error | id1 +70 | Template rollback rồi propagate | 210 / 1000 |
| Template mark rollback-only | id1 +80 | Template rollback khi return | 210 / 1000 |
| Inner `REQUIRED` tham gia | outer id1 +90, inner +100, outer +5 | Inner status rollback đánh dấu T1 rollback-only; outer commit rollback, caller thấy `UnexpectedRollbackException` | 210 / 1000 |
| Inner `REQUIRES_NEW` | outer id1 +1, inner id2 +5 | Inner T2 commit; outer T1 rollback | 210 / 1005 |

**Đọc kết quả đúng:** `CAUGHT_CHECKED_COMMIT` xuất hiện **cùng** thay đổi id1 +40 đã commit. Điều này không mâu thuẫn: lỗi checked được báo lại **sau** khi ứng dụng chủ động commit vì contract case 4 cho phép. Nếu nghiệp vụ thực sự coi `IOException` là failure không được ghi, phải dùng case 3.

`CAUGHT_UNEXPECTED` chỉ xuất hiện sau khi outer `commit(status)` cố hoàn tất transaction T1 đã global rollback-only; không phải vì bản thân một lệnh UPDATE ném exception. `manager.rollback(inner)` đã quyết định làm physical transaction chung không thể commit.

`AFTER_REQUIRES_NEW` chứng minh T2 commit độc lập: outer rollback id1 +1 nhưng id2 +5 vẫn tồn tại. H2 in-memory với HikariCP và mặc định pool đủ hai connection là môi trường minh họa, không phải bài kiểm thử throughput.

## 14. Tránh những anti-pattern làm sai kết quả hoặc che nguyên nhân

### 14.1. Rollback sau commit exception

~~~java
try {
    doWork();
    manager.commit(status);
} catch (Exception ex) {
    manager.rollback(status); // SAI nếu lỗi đến từ commit.
}
~~~

Không dùng mẫu này. Theo contract, commit đã hoàn tất cleanup dù lỗi. Một rollback sau commit failure có thể ném `IllegalTransactionStateException` và che mất commit error.

### 14.2. Commit sau rollback

~~~java
manager.rollback(status);
manager.commit(status); // SAI: status đã completed.
~~~

Không thể “thử commit” lại status đã kết thúc. Nếu cần retry nghiệp vụ, hãy tạo **transaction mới** qua `getTransaction`, và chỉ retry khi operation idempotent và trạng thái bên ngoài đã được xác định.

### 14.3. Catch lỗi rồi trả success

~~~java
TransactionStatus status = manager.getTransaction(def);
try {
    writeStepOne();
    writeStepTwo(); // ném lỗi nhưng bị catch ở dưới
} catch (RuntimeException ignored) {
    // Anti-pattern: bỏ qua lỗi và tiếp tục commit.
}
manager.commit(status);
~~~

Không có “mặc định tự rollback khi RuntimeException đã từng xuất hiện” với API trực tiếp. Nếu exception bị catch và status chưa rollback-only, `commit` có thể thành công, tạo partial state. Một SQL error còn có thể khiến DB transaction aborted; commit lúc đó có thể thất bại. Phải chọn policy rõ ràng thay vì nuốt lỗi.

### 14.4. Không bắt lỗi từ rollback

~~~java
catch (RuntimeException original) {
    manager.rollback(status); // Nếu rollback ném lỗi, original có thể bị che.
    throw original;
}
~~~

Cấu trúc này rất phổ biến nhưng rollbackFailure có thể làm exception gốc bị mất khỏi stack top. Khi cần forensics, lưu cả hai. Chiến lược `addSuppressed` trong demo là một lựa chọn.

### 14.5. Dùng một TransactionStatus cho nhiều thread

Các status/resource trong imperative transaction management thường gắn với scope và thread thực thi. Không giữ `TransactionStatus` trong singleton field để nhiều request cùng commit/rollback, không truyền nó qua thread khác rồi kỳ vọng manager tự di chuyển connection/thread-local context. Dùng transaction boundary riêng cho từng execution.

### 14.6. Gọi JDBC connection ngoài Spring transaction awareness

Lấy connection trực tiếp từ datasource/pool khác có thể làm query không tham gia đúng transaction. Dùng `JdbcTemplate` hoặc `DataSourceUtils` tương thích manager, tránh tự commit/rollback JDBC connection mà Spring đang quản lý.

### 14.7. Gửi thông báo không thể hoàn tác trước commit

Nếu gửi email hoặc publish message rồi DB transaction rollback, side effect không tự bị hủy. Dùng outbox và cơ chế delivery/idempotency nếu hệ thống yêu cầu consistency giữa database và message broker.

## 15. Chiến lược xử lý exception cho các giai đoạn khác nhau

Một service production nên có **bảng chính sách** trước khi viết catch:

| Giai đoạn | Lỗi thường gặp | Phản ứng phù hợp |
| --- | --- | --- |
| Acquire/begin | Pool connection timeout, DB down, isolation không hỗ trợ | Đánh dấu request thất bại, retry có giới hạn nếu an toàn; không rollback status chưa có |
| Business validation **trước khi ghi** | Dữ liệu đầu vào không hợp lệ | Trả lỗi có ý nghĩa; thường chưa cần bắt đầu transaction |
| Business validation **sau khi ghi** | Domain rule violated | Rollback status hiện có; giữ exception nghiệp vụ |
| SQL execution | Constraint violation, deadlock, query timeout | Rollback status, xác định mã lỗi và retry đúng loại nếu an toàn |
| Commit | Rollback-only, flush fail, network/system failure | Không rollback lại status; phân loại kết quả chắc chắn hay bất định, điều tra DB/idempotency |
| Rollback | Connection lỗi, manager system failure | Giữ cả lỗi gốc và lỗi rollback, không giả định dữ liệu đã được hủy |
| After-completion | Notification fail, event delivery fail | Retry side effect có idempotency/outbox; không dùng lại status DB |
| Retry toàn request | Duplicate execution, race | Transaction mới, unique constraints/idempotency key và bounded backoff |

**Đặc biệt với commit failure do mạng:** server có thể đã commit nhưng client không nhận được ACK. Tự retry toàn bộ INSERT/transfer có thể gây duplicate nếu không có khóa idempotency hoặc một cách truy vấn trạng thái đáng tin. Không khẳng định mọi `TransactionSystemException` chắc chắn rollback.

### Tách lỗi nghiệp vụ và lỗi quản lý transaction

- `IllegalArgumentException` từ domain validation là một thông tin nghiệp vụ.
- `DataIntegrityViolationException` có thể nói SQL vi phạm constraint.
- `UnexpectedRollbackException` nói yêu cầu commit bị biến thành rollback do rollback-only.
- `CannotCreateTransactionException` báo transaction chưa được tạo.
- `TransactionSystemException` báo lỗi hạ tầng ở commit/rollback hoặc transaction coordinator.

Các loại exception này không thay thế lẫn nhau. Một handler ở controller có thể chuyển chúng thành response phù hợp, nhưng **không** được che nguồn lỗi transaction đến mức trả “success” trong khi DB chưa commit.

## 16. Bài tập phân tích từng stage

**Câu 1.** `getTransaction(def)` ném `CannotCreateTransactionException` vì Hikari pool hết connection. Có thể gọi `rollback(status)` không?

**Đáp án:** Không có `TransactionStatus` trả về, nên không có status hợp lệ. Hãy xử lý failure ở begin stage; manager chịu trách nhiệm cleanup nội bộ.

**Câu 2.** Trong direct API, method INSERT rồi ném checked `IOException`. Không dùng `@Transactional`. Spring có tự áp rollbackFor mặc định không?

**Đáp án:** Không. Code trực tiếp phải gọi `rollback(status)` theo policy của nó, hoặc chọn commit có chủ đích khi nghiệp vụ cho phép. Loại checked/unchecked không tự hoàn tất API này.

**Câu 3.** Code đặt `manager.commit(status)` trong `try`, `catch(RuntimeException)` gọi `manager.rollback(status)`. Lỗi gì?

**Đáp án:** Nếu commit ném exception, catch có thể rollback một status đã completed, gây `IllegalTransactionStateException` và che commit error. Đưa commit ra ngoài catch của business body.

**Câu 4.** Body return bình thường nhưng `status.setRollbackOnly()` được gọi. `manager.commit(status)` chắc chắn commit không?

**Đáp án:** Không. Manager có thể rollback thay cho commit. Với một **new transaction** được local mark rollback-only, completion có thể return bình thường sau rollback, nên phải biết marker và không coi tên method `commit` là chứng cứ DB đã commit.

**Câu 5.** Inner `REQUIRED` nhận participating status, code gọi `manager.rollback(inner)`, outer lại gọi `manager.commit(outer)`. Điều gì có thể xảy ra?

**Đáp án:** Inner rollback có thể chỉ đánh dấu physical transaction chung rollback-only, outer commit bị chuyển thành rollback và ném `UnexpectedRollbackException`. Không có rollback riêng của inner `REQUIRED`.

**Câu 6.** Inner `REQUIRES_NEW` commit thành công, outer rollback ngay sau đó. Inner update còn tồn tại không?

**Đáp án:** Có thể còn tồn tại vì inner có physical transaction độc lập. Chính sách này phải được nghiệp vụ chấp nhận; pool/locking phải đủ.

**Câu 7.** Rollback sau lỗi business ném thêm một `TransactionSystemException`. Có nên bỏ exception business?

**Đáp án:** Không nên mất cả hai. Có thể giữ business error làm chính và thêm rollback failure vào `suppressed` hoặc chọn rollback failure làm chính và gắn cause, tùy policy; cần log đủ để xác định kết quả transaction có thể bất định.

**Câu 8.** DB đã commit xong, nhưng `afterCommit()` gửi email thất bại. Gọi rollback status cũ để hủy DB data có đúng không?

**Đáp án:** Không. Transaction DB đã hoàn tất; cần retry side effect hoặc cơ chế outbox/compensation, không rollback một completed status.

## 17. Checklist triển khai code transaction trực tiếp

- [ ] Chỉ dùng API trực tiếp khi cần điều khiển rõ ràng; ưu tiên `TransactionTemplate` để giảm boilerplate nếu đủ chức năng.
- [ ] Định nghĩa rõ propagation/isolation/timeout và manager/datasource đúng.
- [ ] Phân biệt `getTransaction` có thể lỗi **trước khi status tồn tại**.
- [ ] Với business exception: chọn rollback/commit **có chủ đích** cho cả checked và unchecked.
- [ ] Đặt `commit(status)` **ngoài catch** có `rollback(status)` của business body.
- [ ] Không commit/rollback lại status đã `isCompleted()`.
- [ ] Kiểm tra `setRollbackOnly()` và participating scopes; `commit` không nhất thiết commit vật lý.
- [ ] Không nuốt lỗi SQL rồi giả định connection vẫn có thể commit.
- [ ] Nếu rollback thất bại, giữ cả rollbackFailure và original.
- [ ] Với commit failure, không mặc định kết quả DB chắc chắn rollback; thiết kế retry/idempotency.
- [ ] Không dùng `TransactionStatus` chung qua các request threads.
- [ ] Viết integration test đọc DB **sau khi scope hoàn tất**, không chỉ kiểm tra log UPDATE.
- [ ] Khi có `REQUIRES_NEW`, kiểm tra pool size/row locks và independent commit.
- [ ] Xử lý external side effects theo outbox/after-completion policy.
- [ ] Với reactive flows, dùng `TransactionalOperator` thay vì sao chép imperatively managed ThreadLocal code.

## 18. Kết luận

**Quản lý transaction trực tiếp là quản lý một chu trình một chiều: begin → business work → đúng một completion → cleanup.** `PlatformTransactionManager` cung cấp API nhất quán; `TransactionStatus` lưu trạng thái của scope; `TransactionTemplate` tự động hóa phần lớn công việc này.

Hai lỗi nguy hiểm nhất là **nghĩ checked/unchecked tự có rollback rule như `@Transactional` khi code dùng manager trực tiếp**, và **gọi rollback sau khi commit đã ném exception**. Hãy quyết định exception policy cho từng stage, tách catch business khỏi completion, ghi nhận lỗi rollback mà không che original, và xác minh kết quả DB sau hoàn tất. Với nhiều logical scopes, phân biệt transaction tham gia và transaction vật lý mới; với commit failure, luôn tính đến khả năng kết quả bất định.

## Tài liệu tham khảo chính thức

- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`, `PlatformTransactionManager`, `TransactionDefinition` và `TransactionStatus`.
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): hợp đồng getTransaction/commit/rollback, đặc biệt **không rollback sau commit failure**.
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): isRollbackOnly, setRollbackOnly, isCompleted, savepoints.
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): lifecycle và xử lý exception callback.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): participating REQUIRED, rollback-only/UnexpectedRollbackException, REQUIRES_NEW.
- [Spring Framework — Transaction Synchronization](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): callbacks beforeCommit, afterCommit, afterCompletion.
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): DataSourceTransactionManager, transaction-aware connection usage.
