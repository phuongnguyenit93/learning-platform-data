# Chọn propagation từ yêu cầu nghiệp vụ thay vì tránh lỗi cấu hình

> **Spring Framework — Transaction Management → Propagation khác.** Chọn `@Transactional(propagation = ...)` không phải là chọn một cách làm cho exception biến mất, cũng không phải chỉnh tham số đến khi chương trình “chạy qua”. Mỗi propagation value là một **cam kết về ranh giới giao dịch**, tác động trực tiếp đến tính nguyên tử, sự tồn tại của dữ liệu sau rollback, khả năng nhìn thấy dữ liệu, việc giữ khóa và nhu cầu connection. Bài này đưa ra quy trình lựa chọn dựa trên **yêu cầu nghiệp vụ**, minh họa những quyết định đúng/sai và kiểm chứng bằng ví dụ Java 17+.

## 1. Quy tắc mở đầu: hỏi về kết quả dữ liệu trước khi hỏi annotation

Giả sử nghiệp vụ tạo đơn hàng có ba bước:

1. Ghi đơn hàng.
2. Trừ số lượng tồn kho.
3. Ghi một bản ghi audit.

Trước khi chọn propagation, phải trả lời các câu hỏi:

- Nếu bước 2 lỗi thì **đơn hàng và tồn kho** có bắt buộc quay về trạng thái ban đầu cùng nhau không?
- Bản audit cần lưu **chỉ khi đơn hàng thành công** hay cần lưu **kể cả khi đơn hàng bị rollback**?
- Audit có cần tham chiếu đến dữ liệu đơn hàng **chưa commit** không?
- Một method có được phép tự chạy độc lập hay **bắt buộc caller đã mở transaction**?
- Một phần việc bị lỗi có được phép hủy riêng mà **không hủy toàn bộ** nghiệp vụ?
- Nếu không có transaction, thao tác có an toàn/đúng nghĩa không?

Những câu trả lời đó quyết định `REQUIRED`, `REQUIRES_NEW`, `NESTED`, `MANDATORY` hoặc propagation khác. Nếu chưa xác định được các invariant trên, thay đổi propagation chỉ vì thấy `UnexpectedRollbackException` hay “No existing transaction found” là một quyết định thiếu cơ sở.

**Phát biểu mục tiêu bằng ngôn ngữ nghiệp vụ:**

> “Đơn hàng và tồn kho phải commit hoặc rollback cùng nhau; log về một lần thử thanh toán được giữ lại ngay cả khi đơn hàng thất bại; thao tác cập nhật số dư không bao giờ được gọi khi chưa có transaction.”

Phát biểu này có giá trị hơn:

> “Đặt `REQUIRES_NEW` để tránh rollback error” hoặc “đổi `MANDATORY` thành `REQUIRED` để hết exception”.

## 2. Hai khái niệm cần tách: logical scope và physical transaction

Một lời gọi qua Spring proxy vào method `@Transactional` có thể tạo **logical transaction scope**, nhưng không phải lúc nào cũng tạo một **physical transaction** mới. Đây là nền tảng để hiểu propagation.

```text
Caller
  |
  +-- OrderService.placeOrder() @Transactional(REQUIRED)
  |       |
  |       +-- logical scope A
  |       |       physical transaction T1
  |       |
  |       +-- StockService.reserve() @Transactional(REQUIRED)
  |       |       logical scope B tham gia T1
  |       |
  |       +-- AuditService.recordAttempt() @Transactional(REQUIRES_NEW)
  |               |
  |               +-- logical scope C, physical transaction T2 riêng
  |                       T1 tạm suspend (không mặc nhiên nhả locks)
  |
  +-- T1 hoàn tất sau khi outer method trở về
```

Trong phương án `REQUIRED`, A và B có các scope logic riêng, nhưng thường cùng **một transaction vật lý** khi dùng đúng một manager và tài nguyên. Commit thực hiện ở boundary của T1; inner B không tự commit phần mình.

Trong `REQUIRES_NEW`, C có **T2 độc lập**. C có thể commit và dữ liệu còn tồn tại dù T1 về sau rollback. Ngược lại, T2 có thể rollback trong khi T1 vẫn được tiếp tục khi lỗi T2 được xử lý phù hợp. Nhưng T2 cần tài nguyên riêng, thường thêm JDBC connection, và không tự có quyền đọc dữ liệu chưa commit của T1.

Trong `NESTED` (khi manager hỗ trợ), inner thường dùng **savepoint bên trong T1**. Nó không phải một T2 độc lập: nếu T1 rollback, dữ liệu inner vẫn rollback.

**Từ khóa:** physical transaction quyết định phạm vi atomicity thực, không phải chỉ số lượng dấu `@Transactional` trong call stack.

## 3. Bảy propagation values: diễn đạt bằng cam kết nghiệp vụ

`Propagation` nằm trong `org.springframework.transaction.annotation.Propagation`; giá trị mặc định của Spring `@Transactional` là `REQUIRED`.

| Propagation | Khi đã có transaction phù hợp | Khi chưa có transaction | Câu hỏi nghiệp vụ mà nó giúp trả lời |
| --- | --- | --- | --- |
| `REQUIRED` *(mặc định)* | Tham gia transaction đang có | Mở transaction mới | “Công việc này thuộc cùng đơn vị all-or-nothing với caller, nhưng cũng được phép là entry point độc lập?” |
| `REQUIRES_NEW` | Suspend transaction ngoài, mở physical transaction riêng | Mở transaction mới | “Kết quả inner có quyền commit/rollback độc lập với caller?” |
| `NESTED` | Tạo nested boundary/savepoint nếu manager hỗ trợ | Thường mở transaction mới | “Cho phép rollback một phần thao tác và tiếp tục outer **trong cùng transaction vật lý**?” |
| `SUPPORTS` | Tham gia transaction đang có | Có thể chạy không có actual transaction | “Công việc này vẫn đúng khi caller không dùng transaction, nhưng có thể tham gia nếu có?” |
| `MANDATORY` | Tham gia transaction đang có | Báo lỗi | “Method chỉ hợp lệ nếu caller sở hữu transaction boundary?” |
| `NOT_SUPPORTED` | Suspend transaction ngoài; thực thi không có transaction của manager đó | Thực thi không có transaction | “Đoạn này cần chạy bên ngoài transaction do Spring đang quản lý?” |
| `NEVER` | Báo lỗi | Thực thi không có transaction | “Cấm gọi method khi có transaction đang active?” |

**Giới hạn quan trọng:** bảng tóm tắt semantics của Spring propagation. Việc suspend, savepoint, connection binding, transaction synchronization, isolation/read-only và hỗ trợ reactive/JTA/JPA phụ thuộc transaction manager và resource. `NESTED` không bảo đảm hoạt động với mọi JPA provider. `SUPPORTS`/`NOT_SUPPORTED` không đồng nghĩa mọi I/O bên dưới đều an toàn hoặc rollback được.

### 3.1. `REQUIRED` — nên là mặc định khi cùng một đơn vị atomicity

Ví dụ:

```java
@Transactional
public void createOrder(OrderRequest input) {
    orders.insert(input);
    stock.reserve(input.productId(), input.quantity());
}
```

Fragment: `orders`, `stock` và `OrderRequest` là thành phần giả định của ứng dụng. Nếu hai ghi dữ liệu bắt buộc **cùng commit hoặc cùng rollback**, service outer làm transaction boundary và những operations inner tham gia bằng `REQUIRED` là mô hình hợp lý.

Khi không có transaction, outer khởi tạo một transaction. Khi đã có, outer có thể tham gia transaction hiện tại. Điều này cũng có nghĩa caller cao hơn có thể kéo dài scope, ảnh hưởng thời gian giữ connection/locks; cần thiết kế ranh giới hợp lý.

### 3.2. `REQUIRES_NEW` — chọn khi có yêu cầu commit độc lập thật

Ví dụ audit bắt buộc ghi nhận **lần thử** thất bại, không phải audit khẳng định “order đã thành công”:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAttempt(long attemptId, String outcome) {
    auditRepository.insert(attemptId, outcome);
}
```

Fragment. Nếu outer rollback mà bản audit vẫn cần tồn tại, độc lập transaction là một yêu cầu nghiệp vụ có thể biện minh `REQUIRES_NEW`. Nhưng cần kiểm tra:

- Audit không dùng foreign key phụ thuộc một order **chưa commit** của outer.
- Audit không cập nhật cùng row mà outer đang khóa.
- Connection pool có capacity khi outer vẫn giữ tài nguyên.
- Ghi audit thất bại phải được xử lý/báo cáo đúng hợp đồng nghiệp vụ.
- Audit mô tả chính xác “đã thử” hoặc “đã thấy lỗi”, không được hiểu nhầm thành “đơn hàng đã commit”.

Nếu audit chỉ cần tồn tại khi order commit, thường **không** nên dùng `REQUIRES_NEW` cho bản audit đó.

### 3.3. `NESTED` — chọn vì partial rollback và savepoint, không phải independent commit

Một batch gồm các nhóm thao tác có thể cần “nhóm thất bại thì hoàn tác nhóm đó, các nhóm khác vẫn tiếp tục” trong **một transaction vật lý**:

```java
@Transactional(propagation = Propagation.NESTED)
public void importOneGroup(Group group) {
    // Có thể rollback về savepoint nếu dữ liệu nhóm này không hợp lệ.
}
```

Fragment giả định `Group`. Với manager hỗ trợ JDBC savepoint, một nested scope có thể rollback về savepoint mà outer vẫn tiếp tục. Nhưng nếu outer cuối cùng rollback, **tất cả những thay đổi trong transaction vật lý** đều rollback.

Không chọn `NESTED` khi yêu cầu “inner đã commit là phải còn dù outer rollback”. Đó là semantics độc lập, khác nested savepoint.

### 3.4. `SUPPORTS` — khi operation hợp lệ dù không có transaction

Một hàm đọc thông tin không yêu cầu snapshot nhất quán qua nhiều query có thể chạy cả trong và ngoài transaction:

```java
@Transactional(propagation = Propagation.SUPPORTS, readOnly = true)
public ProductView findVisibleProduct(long id) {
    return repository.findVisible(id);
}
```

Fragment. `SUPPORTS` không đảm bảo có physical transaction nếu caller không có. Với datasource/cơ chế đồng bộ cụ thể, vẫn có thể có transaction synchronization scope; không đánh đồng với “luôn không có resource binding”.

Nếu use case cần các lệnh SELECT cùng snapshot/isolation nhất quán thì phải lựa chọn transaction boundary tương ứng, không mặc nhiên chọn `SUPPORTS` chỉ vì operation là “read”.

### 3.5. `MANDATORY` — biến hợp đồng “caller phải mở transaction” thành kiểm tra runtime

Một helper thay đổi nhiều bảng chỉ hợp lệ trong use case rộng hơn:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void applyAccountDelta(long accountId, long delta) {
    accountRepository.changeBalance(accountId, delta);
}
```

Fragment. `MANDATORY` báo lỗi nếu được gọi qua proxy mà không có transaction phù hợp. Đây có thể là một guard **đúng theo thiết kế**, chứ không phải lỗi cần sửa bằng cách chuyển sang `REQUIRED` cho hết exception.

Nếu chuyển `MANDATORY` sang `REQUIRED`, helper có thể tự mở/commit transaction khi caller quên transaction, khiến các thao tác ở tầng nghiệp vụ bên ngoài không còn atomic như yêu cầu. Hãy sửa missing boundary của caller trước, thay vì gỡ đi guard.

### 3.6. `NOT_SUPPORTED` — khi thật sự cần chạy ngoài transaction

Ví dụ một đoạn đọc tham chiếu ngoài atomic unit, nơi không muốn giữ thêm resource/transaction của outer:

```java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public SystemHealthSnapshot gatherDiagnostics() {
    return diagnosticRepository.readSnapshot();
}
```

Fragment. Nếu caller có transaction, manager tạm treo transaction đó và thực hiện đoạn này bên ngoài **transaction do manager đang quản lý**. Tùy datasource/provider, các statements không có transaction có thể tự commit và thấy dữ liệu khác isolation snapshot của outer.

Không coi `NOT_SUPPORTED` là “transaction nhỏ hơn” hay một cách bảo đảm độc lập commit. Nó **không có transaction riêng**; nếu code ghi nhiều câu SQL ở autocommit mode, một phần có thể đã commit trước khi bước tiếp theo thất bại.

### 3.7. `NEVER` — phát hiện sai contract, không phải tối ưu hiệu năng

```java
@Transactional(propagation = Propagation.NEVER)
public void requireNonTransactionalCall() {
    // Một API chỉ được gọi khi không có Spring-managed transaction.
}
```

Fragment. Khi đã có transaction, `NEVER` báo lỗi thay vì tiếp tục. Nó phù hợp nếu gọi trong transaction **vi phạm kiến trúc**, chẳng hạn một API phải được điều phối hoàn toàn ngoài boundary của DB transaction. Nhưng dùng `NEVER` trên mọi lời gọi HTTP không tự bảo đảm HTTP side effects/DB state nhất quán; cần thiết kế orchestration phù hợp.

## 4. Cây quyết định: chọn theo business invariant

```text
BƯỚC A: Có nhiều thay đổi phải commit/rollback cùng nhau?
  |
  +-- CÓ ------------------------------------------------------+
  |                                                           |
  |   Công việc có thể là transaction entry point độc lập?      |
  |       +-- CÓ --> REQUIRED                                   |
  |       +-- KHÔNG, caller bắt buộc mở --> MANDATORY            |
  |                                                           |
  +-- KHÔNG hoặc có yêu cầu đặc biệt ---------------------------+
                  |
                  v
       Inner cần COMMIT độc lập, tồn tại khi outer rollback?
                  |
           +------+------+
           |             |
          CÓ            KHÔNG
           |             |
       REQUIRES_NEW      |
           |             v
           |     Cần ROLLBACK một phần bằng savepoint
           |     mà vẫn ở trong transaction vật lý outer?
           |             |
           |         +---+----+
           |         |        |
           |        CÓ       KHÔNG
           |         |        |
           |    NESTED*       v
           |             Operation hợp lệ không có transaction?
           |                +-- CÓ và cho phép tham gia --> SUPPORTS
           |                +-- CÓ nhưng cần ở ngoài --> NOT_SUPPORTED
           |                +-- BẮT BUỘC không được có --> NEVER
           |
           +-- Kiểm tra pool, locks, độc lập dữ liệu, retries

*NESTED chỉ khi transaction manager/resource hỗ trợ savepoint.
```

Cây quyết định là công cụ đặt câu hỏi, **không thay thế review**. Ví dụ một hoạt động “không cần cùng atomicity” có thể vẫn là một phần của `REQUIRED` để giảm complexity, hoặc được đưa ra ngoài transaction qua orchestration thay vì dùng `NOT_SUPPORTED`. Điều quan trọng là lý do phải được mô tả thành một yêu cầu và được kiểm thử.

## 5. Bảng ánh xạ yêu cầu nghiệp vụ sang propagation

| Tình huống | Bất biến cần giữ | Lựa chọn thường phù hợp | Cần thận trọng |
| --- | --- | --- | --- |
| Tạo order + trừ stock | Cùng thành công hoặc cùng rollback | `REQUIRED` | Cùng manager/resource; rollback rules; có thể cần isolation/locking để tránh oversell |
| Thay đổi số dư trong nghiệp vụ chuyển tiền | Không được tự commit một nửa transfer | Outer `REQUIRED`; helper `MANDATORY` nếu cần enforce caller | Đổi helper sang `REQUIRES_NEW` có thể tạo số dư lệch |
| Lưu audit “attempt failed” dù order rollback | Audit vẫn tồn tại độc lập | `REQUIRES_NEW`, hoặc kênh ghi nhận độc lập đáng tin cậy | Không tham chiếu row uncommitted của outer; pool và lock contention |
| Lưu sự kiện “order committed” | Không được phát sự kiện về order chưa commit | Outbox cùng `REQUIRED`, publisher sau commit | `REQUIRES_NEW` trước outer commit làm sai thông tin |
| Nhập nhiều nhóm dữ liệu, nhóm lỗi được bỏ qua | Các nhóm hợp lệ được giữ nếu outer cuối cùng commit | `NESTED` với savepoint hoặc thiết kế mỗi nhóm transaction riêng | `NESTED` không commit độc lập; giới hạn manager |
| Tra cứu danh mục đơn giản | Có thể chạy cả có và không có transaction | `SUPPORTS` hoặc ranh giới đọc riêng | Không suy ra tính nhất quán của nhiều SELECT |
| Method phục vụ orchestration không được gọi khi DB transaction mở | Caller vi phạm phải được phát hiện | `NEVER` hoặc kiến trúc tách layer | Không phải workaround cho sai transaction manager |
| Telemetry/diagnostics không cần tham gia T1 | Tách khỏi transaction outer | `NOT_SUPPORTED` hoặc chạy trước/sau transaction | Không có atomicity cho các writes |
| Operation buộc được bao bởi unit of work của caller | Không bao giờ tự commit riêng | `MANDATORY` | Lỗi thiếu transaction là dấu hiệu cần sửa caller |

**Đừng đồng nhất audit, events và log.** “Lưu log” có ít nhất ba semantics khác nhau: log kỹ thuật best-effort, audit pháp lý phải bền vững, và business event chỉ đúng khi business state đã commit. Cùng một tên method `record()` nhưng có thể cần ba thiết kế giao dịch khác nhau.

## 6. Anti-pattern 1: đổi sang REQUIRES_NEW để “chữa” UnexpectedRollbackException

### Hiện tượng

```text
Outer @Transactional REQUIRED
  -> Inner @Transactional REQUIRED
       -> ném RuntimeException
       -> inner interceptor đánh dấu shared transaction rollback-only
  -> Outer bắt RuntimeException và return bình thường
  -> Outer cố commit
       -> UnexpectedRollbackException
```

`UnexpectedRollbackException` không phải bug cần “tắt”, mà là tín hiệu caller đã đi đến ranh giới commit **trong khi physical transaction không thể commit**. Nguyên nhân có thể là participating inner rollback, explicit `setRollbackOnly()`, lỗi resource hoặc nhiều cơ chế khác.

### Cách sửa sai

```java
// Không đổi propagation chỉ để exception biến mất.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void updateInventory() {
    // Inner bỗng commit độc lập với order.
}
```

Nếu updateInventory chuyển sang `REQUIRES_NEW`, inventory có thể commit trong khi order rollback. Đôi khi cái giá của việc “không còn UnexpectedRollbackException” là **bất biến dữ liệu bị vi phạm**. Bản thân lỗi biến mất không chứng minh semantics mới đúng.

### Cách phân tích đúng

- Inventory và order cần atomic cùng nhau? Giữ chung transaction, chấp nhận rollback toàn bộ, sửa cách báo lỗi/caller.
- Lỗi inner là nghiệp vụ bình thường có thể bỏ qua? Thiết kế savepoint `NESTED` khi phù hợp, hoặc thay đổi boundary để lỗi không poison shared transaction.
- Inner thực sự độc lập, có thể commit dù outer rollback? Khi đó `REQUIRES_NEW` hợp lý, nhưng phải review pool/locking/idempotency.
- Caller bắt exception sai chỗ? Xác định outermost transactional proxy boundary và viết test ở ngoài proxy để thấy exception cuối.

Đặc biệt, bắt exception ở outer không tự xóa `rollback-only` đã được inner đánh dấu. Không tắt `globalRollbackOnParticipationFailure` bừa bãi chỉ để “commit thành công”, vì underlying DB/JPA resource vẫn có thể ở trạng thái không thể commit.

## 7. Anti-pattern 2: đổi MANDATORY thành REQUIRED để không còn lỗi

Một domain helper chỉ hợp lệ khi transaction của use case bao toàn bộ nhiều thao tác:

```java
@Transactional(propagation = Propagation.MANDATORY)
public void debit(long accountId, long amount) {
    jdbc.update("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, accountId);
}
```

Đoạn này là fragment, không phải chương trình độc lập. Khi caller gọi helper mà không mở transaction, Spring ném `IllegalTransactionStateException`; điều đó có thể là **đúng hợp đồng**. Nếu thay thành:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void debit(long accountId, long amount) {
    // ...
}
```

thì helper có thể tự commit khoản trừ tiền. Caller sau đó lỗi trước khi credit tài khoản nhận; lúc này một nửa transfer đã được xác nhận. Việc không còn exception là “thành công” giả.

Giải pháp là mở transaction ở **use-case façade**:

```java
@Transactional // REQUIRED
public void transfer(long fromId, long toId, long amount) {
    accountOperations.debit(fromId, amount);   // MANDATORY
    accountOperations.credit(toId, amount);    // MANDATORY
}
```

Fragment cần hai beans thực sự được Spring proxy; caller phải đi vào façade qua proxy. Với cùng manager/datasource, toàn bộ transfer commit/rollback chung. Ngoài transaction boundary còn cần kiểm tra số dư không âm, lock/optimistic concurrency và idempotency để tránh race conditions.

## 8. Anti-pattern 3: dùng SUPPORTS để bỏ lỗi thiếu transaction

Nếu JPA operation cần transaction để flush/lock hoặc business invariant cần các cập nhật atomic, việc đổi `REQUIRED` hay `MANDATORY` sang `SUPPORTS` **không tạo transaction** khi caller chưa có. Nó có thể làm lỗi xuất hiện **muộn hơn**, hoặc tạo partial writes theo autocommit.

```java
// Thiết kế sai nếu method cần atomic multi-statement update.
@Transactional(propagation = Propagation.SUPPORTS)
public void settleInvoice() {
    updateInvoice();
    updateLedger();
}
```

Không nên chọn `SUPPORTS` dựa trên nhận xét “mấy câu query chỉ cần chạy là được”. Nếu `updateInvoice()` đã autocommit rồi `updateLedger()` thất bại, nghiệp vụ có thể không rollback đồng bộ. Với JPA, các cập nhật có thể cần actual transaction và fail theo provider.

Trước tiên xác định **transaction owner**. Nếu method có thể được gọi độc lập và cần atomicity, `REQUIRED` thường hợp lý. Nếu phải tham gia caller, `MANDATORY` làm hợp đồng rõ hơn.

## 9. Anti-pattern 4: dùng NOT_SUPPORTED hoặc NEVER để che lỗi manager/annotation

### Transaction manager sai tài nguyên

Một ứng dụng có hai datasources `ordersDataSource` và `auditDataSource` nhưng service dùng default `ordersTransactionManager` cho JDBC audit có thể dẫn đến “Spring đang có transaction, nhưng SQL audit vẫn autocommit”. Đổi `REQUIRED` thành `REQUIRES_NEW`/`NOT_SUPPORTED` không thể sửa việc dùng **sai manager**.

Phải xác định đúng `DataSource`, `EntityManagerFactory` hoặc `ConnectionFactory` và chọn manager tương ứng. Nếu nghiệp vụ cần atomicity trên nhiều resource độc lập, một local manager không tự tạo distributed transaction; cần JTA/XA khi phù hợp hoặc thiết kế saga/outbox.

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void saveOrder() {
    // Order repository phải thực sự dùng resource của manager này.
}
```

Fragment. Tham số `transactionManager` chọn bean phù hợp, không thay đổi propagation semantics.

### Self-invocation

```java
@Service
class BillingService {
    public void process() {
        this.persist(); // không đi qua proxy cho persist().
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void persist() {
        // Annotation riêng của persist không được intercept ở lời gọi này.
    }
}
```

Fragment. Trong Spring proxy mode mặc định, self-invocation bypass transaction advice cho inner method. Đổi `REQUIRES_NEW` thành `REQUIRED` hay `NESTED` **không sửa proxy bypass**. Tách transactional boundary sang bean khác và inject Spring proxy, hoặc cân nhắc `TransactionTemplate`/AspectJ mode khi có lý do rõ ràng.

### Checked exceptions và rollback rules

`@Transactional` mặc định rollback cho `RuntimeException` và `Error`, không tự rollback checked `Exception` (trừ cấu hình/rollback policy thay đổi). Nếu một checked `IOException` thoát khỏi method và transaction vẫn commit, cần xem `rollbackFor`/`noRollbackFor`:

```java
@Transactional(rollbackFor = IOException.class)
public void importLedger() throws IOException {
    // ...
}
```

Fragment. Thay `REQUIRED` thành `REQUIRES_NEW` để có rollback vì checked exception là không đúng tầng giải pháp. Propagation quyết định *quan hệ với transaction ngoài*, còn rollback rules quyết định *exception nào yêu cầu rollback*.

## 10. Quyết định propagation theo ranh giới người sở hữu giao dịch

Hãy đặt rõ ba vai trò:

1. **Entry point use case**: thường sở hữu transaction boundary mà client có thể gọi, ví dụ `TransferService.transfer()`.
2. **Domain operation**: thực hiện một phần nghiệp vụ trong transaction caller; có thể dùng `MANDATORY` nếu phải enforce contract.
3. **Independent work**: được phép có kết quả commit độc lập; chỉ ở đây mới cân nhắc `REQUIRES_NEW` sau khi đánh giá side effects và resources.

Ví dụ cấu trúc:

```text
TransferController
    |
    v
TransferService.transfer()                   @Transactional(REQUIRED)
    |
    +-- AccountOperations.debit()           @Transactional(MANDATORY)
    +-- AccountOperations.credit()          @Transactional(MANDATORY)
    +-- OutboxRepository.appendEvent()       tham gia T1
    |
    v
COMMIT T1
    |
    v
OutboxPublisher (giao dịch khác ở thời điểm khác)
    |
    +-- gửi message, retry/idempotency riêng
```

Toàn bộ trừ/ghi tiền và outbox record commit cùng T1. Publisher đọc outbox **sau commit** và gửi message ở giao dịch/hoạt động khác. Đây là lựa chọn thường vững hơn việc gửi message ngoài DB transaction rồi hy vọng propagation nào đó làm hai thao tác atomic.

Nếu có yêu cầu “ghi lại mọi lần chuyển tiền thất bại”, một audit stream/transaction độc lập có thể đúng; nhưng phải đặt tên sự kiện là “transfer attempt”, không phải “transfer completed”.

### Quan hệ với transaction timeout/isolation/readOnly

Đổi propagation còn ảnh hưởng thời điểm các thuộc tính `isolation`, `readOnly`, `timeout` có hiệu lực:

- `REQUIRED` tham gia transaction hiện có thường dùng đặc tính **physical transaction ngoài**, không tạo isolation hoặc timeout vật lý riêng cho inner.
- `REQUIRES_NEW` tạo physical transaction mới nên có thể đặt thuộc tính riêng cho T2 theo khả năng manager/resource.
- `SUPPORTS` khi không có transaction không đem lại các bảo đảm isolation transactional.
- `NOT_SUPPORTED` thực thi ngoài transaction của manager; không hiểu `readOnly=true` là rào chắn quyền ghi tuyệt đối.
- `MANDATORY` chỉ yêu cầu existing transaction; nó không “nâng” isolation của transaction ngoài.
- `NESTED` có thể dùng savepoint của cùng physical transaction, không phải một isolation level riêng.

Nếu một yêu cầu đến từ isolation/read-only mismatch, có thể bật `validateExistingTransaction` ở manager phù hợp hoặc tái thiết kế transaction owner; đừng đổi propagation chỉ để tránh validation error.

## 11. Java 17+ runnable demo: cùng dữ liệu, ba yêu cầu nghiệp vụ khác nhau

Ví dụ hoàn chỉnh dùng Spring Framework 6.2.8, Spring JDBC và H2 in-memory, không cần Spring Boot. Mục tiêu:

1. **REQUIRED:** Order và audit thuộc cùng unit of work; outer fail thì cả hai rollback.
2. **REQUIRES_NEW:** Audit là “attempt record” độc lập; outer fail nhưng audit đã commit vẫn còn.
3. **SUPPORTS / MANDATORY:** Probe có thể hoạt động không có transaction; helper bắt buộc caller phải mở transaction, cho thấy việc báo lỗi khi thiếu boundary là một guard hữu ích.
4. **Successful REQUIRED:** Order và audit commit cùng nhau; các helpers tham gia đúng transaction.

**Lưu ý mô hình:** hai bảng không có foreign key với nhau để audit của T2 không bị phụ thuộc vào row order chưa commit trong T1. Điều đó **cố ý** tránh tạo lock conflict trong demo, không phải khuyến nghị bỏ mọi foreign key trong ứng dụng thực tế.

### 11.1. Cấu trúc tệp

```text
propagation-business-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── PropagationBusinessDemo.java
```

### 11.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>propagation-business-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.PropagationBusinessDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 11.3. `PropagationBusinessDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class PropagationBusinessDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:business_tx;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        RequiredAudit requiredAudit(JdbcTemplate jdbc) {
            return new RequiredAudit(jdbc);
        }

        @Bean
        IndependentAudit independentAudit(JdbcTemplate jdbc) {
            return new IndependentAudit(jdbc);
        }

        @Bean
        TransactionProbe transactionProbe() {
            return new TransactionProbe();
        }

        @Bean
        MandatoryGuard mandatoryGuard() {
            return new MandatoryGuard();
        }

        @Bean
        OrderService orderService(
                JdbcTemplate jdbc,
                RequiredAudit requiredAudit,
                IndependentAudit independentAudit,
                TransactionProbe probe,
                MandatoryGuard guard) {
            return new OrderService(
                    jdbc, requiredAudit, independentAudit, probe, guard);
        }
    }

    public static class RequiredAudit {
        private final JdbcTemplate jdbc;

        public RequiredAudit(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Audit thuộc cùng atomic unit với OrderService.
        @Transactional(propagation = Propagation.REQUIRED)
        public void record(int id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, detail) VALUES (?, ?)",
                    id, "committed together");
        }
    }

    public static class IndependentAudit {
        private final JdbcTemplate jdbc;

        public IndependentAudit(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Audit của lần THỬ, được phép tồn tại dù outer rollback.
        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void recordAttempt(int id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, detail) VALUES (?, ?)",
                    id, "attempt recorded independently");
        }
    }

    public static class TransactionProbe {
        // Được phép chạy cả trong và ngoài actual transaction.
        @Transactional(propagation = Propagation.SUPPORTS)
        public boolean isActualTransactionActive() {
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        }
    }

    public static class MandatoryGuard {
        // Contract: chỉ được gọi khi caller đã mở transaction.
        @Transactional(propagation = Propagation.MANDATORY)
        public void requireCallerTransaction() {
            System.out.println(
                    "mandatory.inside="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final RequiredAudit requiredAudit;
        private final IndependentAudit independentAudit;
        private final TransactionProbe probe;
        private final MandatoryGuard guard;

        public OrderService(
                JdbcTemplate jdbc,
                RequiredAudit requiredAudit,
                IndependentAudit independentAudit,
                TransactionProbe probe,
                MandatoryGuard guard) {
            this.jdbc = jdbc;
            this.requiredAudit = requiredAudit;
            this.independentAudit = independentAudit;
            this.probe = probe;
            this.guard = guard;
        }

        // Business invariant: order và audit này luôn rollback cùng nhau.
        @Transactional
        public void rollbackTogether() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    1, "required order");
            requiredAudit.record(1);
            throw new IllegalStateException("rollback together");
        }

        // Business invariant khác: audit ghi nhận lần THỬ độc lập.
        @Transactional
        public void failButKeepAttempt() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    2, "independent audit order");
            independentAudit.recordAttempt(2);
            throw new IllegalStateException("outer failed");
        }

        // Thành công thông thường: cùng transaction, helper MANDATORY hợp lệ.
        @Transactional
        public void createSuccessfully() {
            jdbc.update(
                    "INSERT INTO orders (id, label) VALUES (?, ?)",
                    3, "success");
            requiredAudit.record(3);

            System.out.println(
                    "supports.inside="
                    + probe.isActualTransactionActive());

            guard.requireCallerTransaction();
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table, Integer.class);
    }

    private static void printCounts(JdbcTemplate jdbc, String prefix) {
        System.out.println(
                prefix
                + " orders=" + count(jdbc, "orders")
                + " audits=" + count(jdbc, "audit_events"));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        id INT PRIMARY KEY,
                        detail VARCHAR(100) NOT NULL
                    )
                    """);

            // SUPPORTS: hợp lệ khi caller không có transaction.
            System.out.println(
                    "supports.outside="
                    + context.getBean(TransactionProbe.class)
                            .isActualTransactionActive());

            // MANDATORY: gọi trực tiếp không có transaction phải fail.
            try {
                context.getBean(MandatoryGuard.class)
                        .requireCallerTransaction();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                        "mandatory.outside="
                        + ex.getClass().getSimpleName());
            }

            OrderService service = context.getBean(OrderService.class);

            try {
                service.rollbackTogether();
            } catch (IllegalStateException ex) {
                System.out.println("required.failed=" + ex.getMessage());
            }
            printCounts(jdbc, "afterRequired");

            try {
                service.failButKeepAttempt();
            } catch (IllegalStateException ex) {
                System.out.println("independent.failed=" + ex.getMessage());
            }
            printCounts(jdbc, "afterIndependent");

            service.createSuccessfully();
            printCounts(jdbc, "afterSuccess");
        }
    }
}
```

### 11.4. Chạy và kiểm tra

Yêu cầu JDK 17+ và Maven 3.x. Trong thư mục `propagation-business-demo`:

```bash
mvn -q clean compile exec:java
```

Các dòng **do chính chương trình in ra** theo thứ tự kỳ vọng (không tính log tùy môi trường):

```text
supports.outside=false
mandatory.outside=IllegalTransactionStateException
required.failed=rollback together
afterRequired orders=0 audits=0
independent.failed=outer failed
afterIndependent orders=0 audits=1
supports.inside=true
mandatory.inside=true
afterSuccess orders=1 audits=2
```

**Giải thích từng kết quả:**

1. `supports.outside=false`: method `SUPPORTS` chạy được khi chưa có physical transaction; không tự khởi tạo transaction chỉ để trả boolean.
2. `mandatory.outside=IllegalTransactionStateException`: giao kèo caller phải mở transaction được enforce. Đây là kết quả **đúng**, không phải lỗi bắt buộc đổi propagation.
3. `rollbackTogether()` dùng outer `REQUIRED` và inner `RequiredAudit.REQUIRED` qua **hai Spring beans**. Inner tham gia transaction outer. Khi outer ném unchecked exception, cả order và audit rollback: hai số đếm bằng 0.
4. `failButKeepAttempt()` dùng outer T1 và independent audit T2. Audit ghi vào bảng riêng, không tham chiếu order chưa commit; T2 commit trước khi T1 rollback. Vì vậy `afterIndependent orders=0 audits=1`.
5. `createSuccessfully()` mở transaction mới, ghi order ID 3 và audit ID 3 vào cùng physical transaction. `SUPPORTS` probe nhận thấy actual transaction active; `MANDATORY` guard hoạt động hợp lệ.
6. Khi outer thành công, order ID 3 và audit ID 3 được commit. Audit ID 2 từ lần trước vẫn tồn tại, nên `afterSuccess orders=1 audits=2`.

**Lưu ý:** Ví dụ kiểm thử *semantics* của propagation trên một JDBC datasource, không mô phỏng toàn bộ load/concurrency thực tế. Dự kiến output dựa trên cấu hình Spring/H2 đã nêu; nếu muốn xác nhận trực tiếp phải chạy Maven. Mỗi class được tạo thành Spring bean qua `@Bean` và các lời gọi cross-bean đi qua proxy — một điều kiện quan trọng mà ví dụ `this.method()` không đáp ứng.

### 11.5. Những thay đổi có chủ đích để tự học

**Thử A — đổi `IndependentAudit.REQUIRES_NEW` thành `REQUIRED`.** Khi outer fail, cả order và audit sẽ rollback. `afterIndependent orders=0 audits=0`. Đó không phải chỉ là “tối ưu” mà là thay đổi business semantics: mất bản ghi về lần thử đã thất bại.

**Thử B — đổi `MandatoryGuard.MANDATORY` thành `REQUIRED`.** Lời gọi ngoài transaction không còn fail và có thể mở transaction mới. Việc này giúp minh họa vì sao đổi propagation để tránh lỗi có thể **loại bỏ một contract bảo vệ thiết kế**, dù output không còn dòng exception.

**Thử C — đổi `RequiredAudit.REQUIRED` thành `REQUIRES_NEW`.** Case `rollbackTogether()` sẽ để lại audit ID 1 dù order rollback. Nếu audit đó mô tả “order đã commit”, nó trở thành **dữ liệu sai ngữ nghĩa**.

**Thử D — gọi `requiredAudit.record()` mà không đi qua outer và không có transaction.** `REQUIRED` tự tạo transaction mới. Điều này có thể phù hợp cho một API được phép dùng độc lập, nhưng không phù hợp nếu helper phải có caller-owned transaction — lúc đó cân nhắc `MANDATORY`.

**Thử E — dùng một helper `@Transactional(NESTED)` trên JDBC savepoint** để rollback phần helper mà outer tiếp tục. Kiểm tra manager hỗ trợ trước, rồi xác nhận cuối cùng outer rollback vẫn loại bỏ tất cả thay đổi còn trong physical transaction. Đừng diễn giải nested savepoint thành independent commit.

## 12. Một số quyết định tinh tế khi codebase lớn

### 12.1. Không nhất thiết mọi repository/helper phải tự khai báo propagation

Khi service façade đã sở hữu transaction boundary, việc thêm `@Transactional` cho **từng method** không tự làm code an toàn hơn. Các annotation ở tầng thấp có thể che business boundary thật, khiến người đọc tưởng mọi helper là một transaction độc lập.

Dùng quy ước rõ:

- Transaction entry point ở application service/use-case.
- Internal operations tham gia transaction của owner; `MANDATORY` khi cần enforce contract.
- `REQUIRES_NEW` là ngoại lệ được **giải thích bằng hành vi commit độc lập**, có test.
- Các read-only operation dùng `SUPPORTS`/`REQUIRED` tùy yêu cầu consistency, không chọn chỉ theo tên `find...`.

### 12.2. Transaction propagation không quyết định isolation

`REQUIRED`, `REQUIRES_NEW` không tự giải quyết lost update, write skew hay overselling. Còn cần database constraints, optimistic/pessimistic locking, isolation level và retry strategy. Ví dụ hai orders đồng thời trừ stock có thể tranh cùng row, dù mỗi transaction đều được đặt đúng `REQUIRED`.

Tránh câu “chọn `SERIALIZABLE` rồi khỏi cần transaction design”: isolation mạnh hơn có thể tăng contention/serialization failures và vẫn cần retry/idempotency.

### 12.3. Transaction “suspend” không đồng nghĩa “unlock”

Với outer transaction T1 đang giữ connection và locks, inner `REQUIRES_NEW` trên cùng datasource có thể cần connection B và **chờ lock do T1 nắm giữ**. T1 chỉ có thể tiếp tục commit khi inner trả quyền điều khiển. Pool sizing, lock ordering và phạm vi transaction phải được xét. Không tự đổi sang `REQUIRES_NEW` trong nhiều helpers của một request.

### 12.4. Propagation không tự bao phủ mạng, file hay message broker

DB rollback không tự hoàn tác HTTP call, email đã gửi hoặc message đã publish nếu các tài nguyên đó không ở cùng transaction coordinator. Một use case trải nhiều microservices có thể cần **saga, outbox, idempotency và compensation**. Đổi `REQUIRED` thành `REQUIRES_NEW` không tạo distributed atomicity giữa database và API bên ngoài.

### 12.5. Chú ý imperative vs reactive

`PlatformTransactionManager` gắn với các tài nguyên imperative như JDBC/JPA và thường dùng thread-bound context; `ReactiveTransactionManager` với R2DBC dùng reactive context. Quyết định nghiệp vụ về atomicity vẫn quan trọng, nhưng mechanics của propagation và support tùy manager. Không lấy ví dụ JDBC thread-local để kết luận mọi `Mono`/`Flux` cũng hoạt động giống hệt.

## 13. Quy trình điều tra trước khi sửa propagation

Khi có lỗi transaction, **tách lỗi cấu hình khỏi yêu cầu nghiệp vụ**:

### Bước 1 — ghi lại yêu cầu dữ liệu

Viết một câu mô tả dữ liệu nào phải cùng commit/rollback, dữ liệu nào có thể độc lập. Nếu không thống nhất được câu đó, chưa đủ cơ sở đổi propagation.

### Bước 2 — xác định outermost boundary

Method nào là entry point? Caller có đi qua Spring proxy? Nếu caller tự `new Service()`, hoặc method tự gọi `this.inner()`, propagation annotation có thể không được áp dụng. Sửa cách đi qua proxy thay vì thay enum.

### Bước 3 — kiểm tra manager và datasource

`JdbcTemplate` đang dùng datasource nào? `JpaTransactionManager` đang quản lý `EntityManagerFactory` nào? Có nhiều transaction managers chưa khai báo qualifier? Một annotation đúng propagation nhưng manager sai có thể khiến SQL chạy ngoài transaction mong muốn.

### Bước 4 — quan sát rollback-only và exceptions

- Exception có thoát khỏi inner transactional boundary không?
- Có `TransactionStatus.setRollbackOnly()` không?
- Outer có bắt và nuốt exception không?
- Default rollback rules có khớp loại exception thực tế không?
- `UnexpectedRollbackException` phát sinh ở boundary nào?

Nếu lỗi là rollback-only do inner, cần quyết định nghiệp vụ có nên hủy outer hay không, rồi mới chọn thiết kế.

### Bước 5 — xem resource limitations

Có connection pool exhaustion khi dùng `REQUIRES_NEW`? Có lock wait, deadlock, timeout? Có `NESTED` nhưng manager/driver không hỗ trợ savepoint? Có JPA flush/persistence context mismatch? Những nguyên nhân này **không biến mất** khi đặt một propagation khác ngẫu nhiên.

### Bước 6 — test kết quả cuối trên DB thực

Test không chỉ kiểm tra exception class hay số lần gọi repository. Hãy query dữ liệu sau khi transaction kết thúc và khẳng định chính xác bảng/record nào tồn tại.

```text
Given: trạng thái dữ liệu ban đầu
When : chạy use-case qua Spring bean proxy và gây lỗi có chủ đích
Then : đúng các record nghiệp vụ rollback/commit như hợp đồng
And  : không có orphan records, partial transfer hoặc event giả
```

## 14. Test matrix cho các lựa chọn propagation

| Test | Setup | Kết quả mong muốn |
| --- | --- | --- |
| REQUIRED all-or-nothing | Outer và inner cùng manager; inner ghi; outer ném runtime exception | Không còn ghi của cả outer và inner |
| REQUIRED success | Outer và inner ghi, cùng hoàn tất thành công | Cả hai cùng commit |
| REQUIRES_NEW independence | Inner audit không phụ thuộc row uncommitted, đã commit; outer rollback | Audit còn, outer changes mất |
| MANDATORY contract | Gọi helper trực tiếp không có transaction | Báo `IllegalTransactionStateException` |
| MANDATORY valid caller | Caller có transaction phù hợp | Helper tham gia, không tự commit riêng |
| SUPPORTS outside | Không có outer transaction | Method hoạt động nếu logic cho phép; không đòi actual transaction |
| SUPPORTS inside | Có outer transaction | Tham gia transaction đang có |
| NOT_SUPPORTED | Gọi dưới outer transaction | Method thực thi ngoài transaction của manager; cần xác nhận resource semantics |
| NEVER | Gọi dưới outer transaction | Báo lỗi, không âm thầm chạy tiếp |
| NESTED savepoint | Manager hỗ trợ JDBC savepoints; inner lỗi được xử lý phù hợp | Có thể rollback phần inner, outer có thể tiếp tục; outer rollback vẫn hủy tất cả |
| Self-invocation | Outer gọi `this.inner()` | Annotation inner không được intercept trong proxy mode |
| Wrong transaction manager | Method dùng datasource không được manager điều phối | Test phát hiện SQL không rollback như kỳ vọng; cần sửa manager/resource |
| Checked exception | Checked exception thoát khỏi boundary | Kết quả theo `rollbackFor` và default rollback policy thực tế |

**Cẩn thận với test-managed transactions:** Một test method `@Transactional` của Spring TestContext có thể rollback cuối test, che khuất independent commit/rollback của service. Khi kiểm chứng actual commit, cần thiết kế test boundary và queries độc lập phù hợp hoặc dùng `TestTransaction`.

## 15. Những câu hỏi thường gặp

**Hỏi 1. Tại sao không đặt mọi method là `REQUIRES_NEW` để chúng không ảnh hưởng nhau?**

Vì nó phá tính nguyên tử giữa các bước vốn cần cùng commit, có thể lưu partial state, tăng số physical transactions/connections và tăng lock contention. Chỉ dùng khi independent commit là yêu cầu nghiệp vụ.

**Hỏi 2. `REQUIRED` luôn tốt hơn `MANDATORY` không?**

Không. `REQUIRED` cho phép method tự mở transaction. `MANDATORY` enforce caller-owned transaction. Nếu operation chỉ là một phần của transfer lớn, `MANDATORY` có thể ngăn tình huống caller quên transaction và helper tự commit một phần.

**Hỏi 3. Có thể đổi `MANDATORY` thành `SUPPORTS` để hỗ trợ thêm caller không có transaction?**

Chỉ khi operation **thật sự đúng và an toàn** khi không có transaction. Nếu method thực hiện nhiều writes cần atomicity, đổi như vậy là nới lỏng contract nguy hiểm.

**Hỏi 4. Nếu inner muốn rollback riêng nhưng không tạo transaction độc lập, chọn gì?**

Cân nhắc `NESTED`/savepoint nếu JDBC manager và resource hỗ trợ, và nếu outer rollback thì kết quả inner cũng phải mất. Nếu inner phải commit độc lập, `NESTED` không đáp ứng.

**Hỏi 5. `NOT_SUPPORTED` có giống `REQUIRES_NEW` không?**

Không. `REQUIRES_NEW` bắt đầu một physical transaction **mới**, còn `NOT_SUPPORTED` tạm treo outer và thực hiện **không có actual transaction của manager**. Nhiều SQL statements có thể autocommit riêng lẻ khi không có transaction.

**Hỏi 6. `NEVER` có nghĩa method không bao giờ truy cập database?**

Không. Nó chỉ cấm chạy khi có transaction hiện hành tương ứng. Method vẫn có thể truy cập database theo nontransactional/autocommit semantics của resource, nếu được thiết kế như vậy.

**Hỏi 7. Có phải mọi exception trong inner `REQUIRED` làm outer rollback?**

Không tự động cho mọi exception. Spring rollback rules mặc định tập trung vào unchecked exceptions và `Error`; checked exceptions có thể cần `rollbackFor`, và exception bị bắt trước khi thoát khỏi proxy có thể không kích hoạt rule. DB/provider cũng có thể tự đánh dấu transaction rollback-only.

**Hỏi 8. Có thể coi `UnexpectedRollbackException` là một ngoại lệ vô hại và bỏ qua không?**

Không. Nó thông báo transaction mà caller mong commit đã rollback. Bỏ qua dễ khiến hệ thống trả success response dù dữ liệu không được lưu. Cần truy nguyên inner scope/resource và xác định semantics mong muốn.

**Hỏi 9. Một method được gắn `@Transactional` có chắc chắn đi qua transaction interceptor?**

Không. Cần bean do Spring quản lý, transaction infrastructure active, lời gọi qua proxy và method phù hợp với loại proxy. Self-invocation có thể bypass.

**Hỏi 10. Nếu business event phải xuất hiện chính xác một lần sau commit thì chọn `REQUIRES_NEW` cho event publisher?**

Không mặc nhiên. Có thể dùng transactional outbox + publisher idempotent và deduplication để xử lý giao hàng ít nhất một lần. Independent DB commit trước outer commit không chứng minh event tương ứng với business state đã commit.

## 16. Checklist cuối cho code review

- [ ] Mỗi propagation khác `REQUIRED` có **lý do nghiệp vụ** được ghi rõ và kiểm thử.
- [ ] Đã mô tả những dữ liệu nào phải commit/rollback cùng nhau.
- [ ] Đã phân biệt independent commit, partial rollback/savepoint và no transaction.
- [ ] `MANDATORY`/`NEVER` được xem như **contract guards**, không tự ý đổi chỉ để bỏ exception.
- [ ] Lựa chọn `SUPPORTS` không vô tình bỏ atomicity của nhiều câu SQL.
- [ ] `REQUIRES_NEW` không để lại business event/record sai ngữ nghĩa khi outer rollback.
- [ ] Đã xem xét connection pool, locks, isolation, retry và idempotency cho independent transaction.
- [ ] Các method thực sự chạy qua Spring proxy; không có self-invocation vô ý.
- [ ] Transaction manager đúng datasource/JPA/connection factory.
- [ ] Rollback rules phản ánh checked/unchecked exception thực tế.
- [ ] `NESTED` chỉ dùng khi savepoint được hỗ trợ và semantics phù hợp.
- [ ] Tests kiểm tra **dữ liệu sau transaction boundary**, không chỉ mocks/logs.
- [ ] Không đổi propagation như phương pháp mặc định để “giải quyết” lỗi cấu hình.

## 17. Kết luận

**Propagation là lựa chọn về chủ sở hữu và phạm vi tính nguyên tử của transaction.** Chọn dựa trên kết quả dữ liệu mà doanh nghiệp chấp nhận:

- **`REQUIRED`:** cùng một đơn vị all-or-nothing nếu có transaction, hoặc mở đơn vị đó nếu chưa có.
- **`MANDATORY`:** chỉ hợp lệ khi caller đã mở transaction; hữu ích để enforce một contract.
- **`REQUIRES_NEW`:** independent physical transaction; chỉ dùng khi commit/rollback độc lập được chủ đích và có đủ resource.
- **`NESTED`:** partial rollback bằng savepoint trên cùng physical transaction nếu được hỗ trợ, không phải independent commit.
- **`SUPPORTS`:** operation có thể chạy không có actual transaction.
- **`NOT_SUPPORTED`:** chạy bên ngoài transaction đang có, không phải một transaction mới.
- **`NEVER`:** cấm gọi khi transaction đang active; thể hiện giới hạn kiến trúc.

Khi gặp lỗi, hãy sửa **transaction boundary, proxy, manager, rollback rules, resource, isolation hoặc workflow** theo nguyên nhân; đừng chọn một enum propagation chỉ vì nó làm biến mất stack trace.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED` và phân biệt physical/logical transactions.
2. [Spring Framework — `Propagation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html): định nghĩa chính thức của bảy propagation values và điều kiện hỗ trợ.
3. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): defaults, transaction manager, proxy semantics, method visibility, isolation/readOnly/timeout.
4. [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): interceptor, proxy và ranh giới xử lý commit/rollback.
5. [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): exception rollback rules và `setRollbackOnly()`.
6. [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): `PlatformTransactionManager` và các resource-specific managers.
7. [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): liên hệ sự kiện và transaction phase; khi cần bảo đảm gửi sự kiện đáng tin nên cân nhắc outbox.
