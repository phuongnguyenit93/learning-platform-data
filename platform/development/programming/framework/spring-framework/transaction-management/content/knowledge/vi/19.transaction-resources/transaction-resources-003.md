# Phân biệt isSynchronizationActive với isActualTransactionActive trong Spring Transaction Management

## 1. Một tình huống tưởng có transaction nhưng thực tế không có

Bạn đang debug một service Java Spring và thấy:

```java
TransactionSynchronizationManager.isSynchronizationActive() // true
```

Bạn kết luận: “Đã có transaction, mọi SQL đang được bao bởi commit/rollback.” **Kết luận đó có thể sai.** Với một số cấu hình Spring, phương thức dùng `PROPAGATION_SUPPORTS`, khi **chưa có transaction DB bên ngoài**, vẫn mở **phạm vi transaction synchronization** để quản lý tài nguyên/callbacks theo thread. Lúc đó:

```text
isSynchronizationActive()    = true
isActualTransactionActive()  = false
```

Một câu `INSERT` chạy bằng JDBC với connection `autoCommit=true` có thể được commit ngay; sau đó ném exception trong `SUPPORTS` **không làm database đảo ngược INSERT**, dù synchronization đã active.

Hai method đang nói đến đều thuộc:

```java
org.springframework.transaction.support.TransactionSynchronizationManager
```

và trong mô hình Spring transaction **imperative**, chúng là các phương thức `static` đọc metadata gắn với **thread hiện tại**. Chúng trả lời **hai câu hỏi khác nhau**, không phải hai cách viết của “đã có transaction hay chưa”.

**Mục tiêu học tập:**

1. Phân biệt **transaction synchronization scope** với **actual resource transaction** (JDBC/JPA).
2. Nắm cơ chế Spring quản lý `TransactionSynchronizationManager`, thread-bound resources, callback lifecycle.
3. Hiểu chính xác khi nào hai flag khác nhau: `SUPPORTS` không có owner, `NOT_SUPPORTED` tạm ngưng outer, `REQUIRED`/`REQUIRES_NEW`, và chính sách `SYNCHRONIZATION_ALWAYS`.
4. Biết ảnh hưởng của `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` và `SYNCHRONIZATION_NEVER`.
5. Chạy ví dụ Java 17 + Spring Boot + Spring JDBC + H2 quan sát **flag true/false** và **sự khác biệt commit/rollback thật**.
6. Không lạm dụng flag synchronization để quyết định nghiệp vụ hay phát side effects sau commit.

> **Nguyên tắc đọc API:** `isSynchronizationActive()` cho biết Spring synchronization đang mở để có thể đăng ký các callback tương ứng; `isActualTransactionActive()` cho biết Spring hiện **đánh dấu thread gắn với actual transaction**. Cả hai là **metadata theo thread và transaction manager**, không phải một câu SQL hỏi trực tiếp database có commit đang chờ hay không.

## 2. Hai API và ý nghĩa chính xác

### 2.1. `isSynchronizationActive()`

Chữ ký:

```java
public static boolean isSynchronizationActive()
```

Nó trả `true` nếu Spring transaction synchronization đã được kích hoạt cho **thread hiện tại**, thông thường thông qua `TransactionSynchronizationManager.initSynchronization()` được gọi bởi transaction infrastructure.

Synchronization là cơ chế đăng ký các đối tượng `TransactionSynchronization` để nhận các thông báo như:

- trước khi commit hoặc hoàn tất scope;
- sau khi commit theo semantics của transaction manager;
- sau khi hoàn tất với trạng thái commit/rollback/unknown;
- suspend/resume khi một scope transaction bị tạm ngưng.

Tài nguyên như connection hoặc persistence session có thể được Spring quản lý/bind trong scope synchronization, kể cả trường hợp **không có backend transaction vật lý**. Vì vậy flag này chủ yếu trả lời:

**“Hiện tại tôi có thể tham gia cơ chế Spring transaction synchronization và đăng ký một synchronization không?”**

Nó **không trả lời**:

- Có transaction JDBC đang mở với `autoCommit=false` hay không?
- Một câu `UPDATE` vừa chạy sẽ rollback được hay đã auto-commit?
- Có bao nhiêu connection hoặc resource đã được bind?
- Transaction nào sẽ là owner cuối cùng của commit?
- Callback `afterCommit` nhất định tương ứng với một `COMMIT` ở database hay không?

`isSynchronizationActive()` cũng không đếm số synchronization đã đăng ký. Nó có thể là `true` ngay cả khi danh sách callback hiện tại rỗng.

### 2.2. `isActualTransactionActive()`

Chữ ký:

```java
public static boolean isActualTransactionActive()
```

Theo Spring Javadoc, method này phân biệt **thread được liên kết với một actual transaction** và **thread chỉ có synchronization scope**. Trong đường thực thi thông dụng của `AbstractPlatformTransactionManager` với synchronization đang bật, transaction manager thiết lập marker:

```java
TransactionSynchronizationManager.setActualTransactionActive(
    status.hasTransaction()
);
```

Dòng trên diễn giải cách manager gắn metadata khi chuẩn bị synchronization. Bạn **không nên** gọi setter để tự khai báo một transaction DB trong business code; đổi boolean trong thread-local không làm JDBC connection bắt đầu transaction.

Ví dụ thông thường:

- `@Transactional(propagation = REQUIRED)` được gọi qua Spring proxy, không có outer: manager mở một JDBC transaction thật → `actual=true`.
- `PROPAGATION_SUPPORTS` không có outer: không mở backend transaction → `actual=false`.
- `PROPAGATION_SUPPORTS` tham gia outer transaction: actual transaction đã có → `actual=true`.
- `PROPAGATION_NOT_SUPPORTED` tạm ngưng một outer transaction: bên trong scope không có backend transaction đang tham gia → `actual=false`.

**Giới hạn quan trọng:** đây là **marker do Spring transaction infrastructure phơi bày**, không phải kiểm tra tự động tất cả transaction do code ngoài Spring hay driver khác quản lý. Nếu application tự gọi `Connection.setAutoCommit(false)` ở một connection riêng, hai flag Spring có thể vẫn là `false` dù JDBC transaction bên ngoài đã mở.

### 2.3. Đặt cạnh nhau

| Tiêu chí | `isSynchronizationActive()` | `isActualTransactionActive()` |
| --- | --- | --- |
| Câu hỏi trả lời | Synchronization scope của Spring có active? | Spring có đánh dấu actual transaction active? |
| Đối tượng chính | Danh sách callback đồng bộ hóa + quản lý resource | Trạng thái transaction vật lý theo manager |
| Có thể `true` khi không có backend transaction? | **Có** | Thông thường **không** |
| Phù hợp để kiểm tra trước `registerSynchronization`? | **Có** | Không đủ: actual=true không tự đảm bảo synchronization active |
| `true` có phải bằng chứng `COMMIT` đã/sẽ thành công? | Không | **Không** |
| Phụ thuộc thread hiện tại? | Có, với imperative Spring | Có, với imperative Spring |
| Có thay cho `TransactionStatus`/rollback rules? | Không | Không |
| Có đo trạng thái một R2DBC reactive transaction qua static ThreadLocal? | Không | Không |

**Mẹo ghi nhớ:** “Synchronization là **cơ chế theo dõi/đăng ký callback**; actual transaction là **phạm vi tài nguyên có giao dịch**.” Hai khái niệm thường đi cùng nhau nhưng **không đồng nhất**.

## 3. TransactionSynchronizationManager gắn gì vào thread?

Trong Spring JDBC imperative, `TransactionSynchronizationManager` quản lý các cấu trúc theo thread (không phải biến global dùng chung cho mọi request):

```text
Thread hiện tại
  |
  +-- resources: Map<resource-key, resource-holder>
  |       ví dụ DataSource -> ConnectionHolder
  |
  +-- synchronizations: các TransactionSynchronization
  |       được đăng ký nếu synchronization active
  |
  +-- transactionName
  +-- currentTransactionReadOnly
  +-- currentTransactionIsolationLevel
  +-- actualTransactionActive
```

Một số API cần phân biệt:

| API | Ý nghĩa |
| --- | --- |
| `getResource(key)` | Lấy resource đã bind với key trên thread, nếu có |
| `hasResource(key)` | Kiểm tra key có resource được bind hay không |
| `bindResource(key, resource)` | Gắn resource vào thread; hạ tầng Spring thường chịu trách nhiệm |
| `unbindResource(key)` | Gỡ resource; hạ tầng Spring thường chịu trách nhiệm |
| `isSynchronizationActive()` | Có danh sách synchronization active cho thread? |
| `registerSynchronization(synchronization)` | Đăng ký callback; cần synchronization active |
| `getSynchronizations()` | Lấy snapshot danh sách callbacks; cần synchronization active |
| `isActualTransactionActive()` | Marker actual transaction theo thread |
| `getCurrentTransactionName()` | Tên transaction được phơi bày, có thể `null` |
| `isCurrentTransactionReadOnly()` | Metadata read-only hiện tại; không tự bảo đảm DB cấm ghi |
| `getCurrentTransactionIsolationLevel()` | Mức isolation khai rõ hoặc `null`; không phải luôn là giá trị thực driver đang dùng |

Một connection **được bind** không đương nhiên là connection đang nằm trong transaction thật. Trong `SUPPORTS` không có backend transaction, Spring có thể bind/reuse một JDBC connection cho cùng synchronization scope để quản lý lifecycle, trong khi connection vẫn ở chế độ **auto-commit**.

Ngược lại, một transaction manager có thể bắt đầu transaction DB thật mà **không kích hoạt transaction synchronization** nếu bị cấu hình như vậy. Vì thế **không được suy bằng một chiều** rằng “có resources” hoặc “có synchronization” tức chắc chắn có transaction, và cũng không nên dùng `!isSynchronizationActive()` làm chứng cứ tuyệt đối “không có backend transaction”.

### 3.1. Không tự ý gọi API hạ tầng

`initSynchronization()`, `clearSynchronization()`, `setActualTransactionActive(...)`, `bindResource(...)` và `unbindResource(...)` dành chủ yếu cho framework/resource management. Code nghiệp vụ tự gọi chúng có thể phá lịch cleanup, làm thất lạc connection hoặc tạo marker khác với trạng thái DB thật.

Code business thông thường nên dùng:

- `@Transactional` qua Spring proxy;
- `TransactionTemplate` với đúng manager;
- `JdbcTemplate`/Spring Data JPA sử dụng resource do Spring điều phối.

Dùng các API đọc `is...Active()` phục vụ **debug, diagnostics hoặc resource integration**, không dùng setter để “bật transaction bằng tay”.

## 4. Bảng bốn kết hợp boolean: đừng suy luận quá mức

| Synchronization | Actual | Ý nghĩa thường gặp |
| --- | --- | --- |
| `false` | `false` | Đang ở ngoài Spring transaction/synchronization scope; cũng có thể đang dùng chính sách synchronization bị tắt hoặc transaction từ ngoài Spring |
| `true` | `false` | **Có synchronization nhưng không có backend transaction**: `SUPPORTS` không outer, `NOT_SUPPORTED` trong chế độ mặc định `SYNCHRONIZATION_ALWAYS` |
| `true` | `true` | Scope transaction thông thường qua manager: `REQUIRED`, `REQUIRES_NEW`, hoặc `SUPPORTS` tham gia outer |
| `false` | `true` | Không phải trạng thái mặc định điển hình của manager imperative nêu trong lab; nếu gặp, kiểm tra custom manager, marker, suspend/resume và luồng điều phối |

Bảng này **không phải phép ánh xạ tuyệt đối** cho mọi implementation `TransactionManager`. Nên luôn nêu rõ transaction manager, synchronization policy, propagation và việc lời gọi có thực sự đi qua Spring transaction infrastructure hay không.

### 4.1. Vì sao `true/false` hoàn toàn hợp lệ?

Ví dụ:

```text
Caller không có transaction DB
   |
   v
Spring proxy: @Transactional(SUPPORTS)
   |
   +-- Không tạo actual DB transaction
   +-- Nhưng manager chọn SYNCHRONIZATION_ALWAYS
   +-- initSynchronization() cho thread
   |
   v
method body:
  isSynchronizationActive()   -> true
  isActualTransactionActive() -> false
   |
   v
method kết thúc, cleanup synchronization
```

Trạng thái này được Spring thiết kế **có chủ đích** để hỗ trợ resource binding và các callbacks đồng bộ hóa trong “empty transaction scope”. Không gọi nó là “Spring báo sai”.

### 4.2. Vì sao `true/true` chưa bảo đảm có commit ngay?

`SUPPORTS` tham gia `REQUIRED` outer cũng có thể thấy `true/true`. Khi method inner trả về, transaction vật lý do outer sở hữu vẫn chưa kết thúc. Nếu outer tiếp tục rồi rollback, mọi SQL trong transaction chung vẫn có thể bị hủy. Hai flag không tiết lộ **ai là transaction owner** hoặc **scope sẽ commit ở thời điểm nào**.

## 5. Chính sách synchronization của AbstractPlatformTransactionManager

`AbstractPlatformTransactionManager` hỗ trợ ba mode chính, cấu hình bằng:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_ALWAYS
);
```

Tên constant và tác dụng:

| Mode | Synchronization khi actual transaction active | Synchronization cho “empty” SUPPORTS/NOT_SUPPORTED |
| --- | --- | --- |
| `SYNCHRONIZATION_ALWAYS` | Có | **Có** |
| `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` | Có | **Không** |
| `SYNCHRONIZATION_NEVER` | Không | Không |

`SYNCHRONIZATION_ALWAYS` là mặc định của `AbstractPlatformTransactionManager` trong mô hình truyền thống của Spring 6.x. “Always” nghĩa là *kích hoạt synchronization cả cho empty scope khi manager xử lý scope đó*, **không** có nghĩa mọi thread trong JVM lúc nào cũng sync=true.

### 5.1. Với ALWAYS (mặc định): SUPPORTS có thể true/false

```java
TransactionTemplate supports =
    new TransactionTemplate(transactionManager);

supports.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_SUPPORTS);

supports.executeWithoutResult(status -> {
    System.out.println(
        TransactionSynchronizationManager.isSynchronizationActive()
            + " / " +
        TransactionSynchronizationManager.isActualTransactionActive()
    );
});
```

Đây là **mảnh minh họa**, cần manager Spring thật và code chạy trên thread không có outer transaction. Khi dùng manager hỗ trợ cờ với `SYNCHRONIZATION_ALWAYS`, sẽ in:

```text
true / false
```

Nếu `SUPPORTS` được gọi trong outer `REQUIRED`, kết quả thông thường là `true / true`. Chính propagation **và trạng thái outer** cùng quyết định behavior, không phải chỉ nhãn SUPPORTS.

### 5.2. Với ON_ACTUAL: giảm việc mở synchronization “rỗng”

Cấu hình:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager
        .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION
);
```

Khi `SUPPORTS` không có transaction ngoài và manager không mở actual transaction, synchronization không được tạo; kết quả thông thường trở thành:

```text
isSynchronizationActive()   = false
isActualTransactionActive() = false
```

Trong một transaction `REQUIRED` thật do manager mở, synchronization vẫn được bật và thường là `true/true`. Đây là thay đổi **chính sách của manager**, có thể ảnh hưởng resource reuse/cleanup và các integrations dựa trên callbacks. Không đổi setting này trong một hệ thống lớn chỉ để một log “trông hợp lý hơn”.

### 5.3. Với NEVER: một ngoại lệ quan trọng khi diễn giải marker

`SYNCHRONIZATION_NEVER` tắt cơ chế synchronization **kể cả khi manager mở actual resource transaction**. Ở đường thực thi của `AbstractPlatformTransactionManager`, việc phơi bày thread-local marker `actualTransactionActive` thường được thực hiện trong `prepareSynchronization(...)` **khi có new synchronization**. Do đó, ở một lần thực thi riêng với `SYNCHRONIZATION_NEVER`, có thể quan sát:

```text
isSynchronizationActive()   = false
isActualTransactionActive() = false
```

**Dù transaction JDBC vật lý đang tồn tại.** Đây là ví dụ vì sao `isActualTransactionActive()` vẫn là **Spring-exposed marker**, không phải oracle độc lập với cấu hình infrastructure. Nếu business logic bắt buộc biết có transaction hay không, hãy chọn đúng boundary/API theo contract thay vì chỉ kiểm tra hai thread-local booleans.

Điều này không có nghĩa `SYNCHRONIZATION_NEVER` tự tắt database transaction. Nó thay đổi cơ chế đồng bộ hóa và marker exposure. Với manager/resource tùy chỉnh, behavior khác có thể có; luôn test đúng môi trường.

### 5.4. Không kích hoạt synchronization bởi nhiều manager trên cùng thread

Spring Javadoc cảnh báo synchronization không được thiết kế để **nhiều transaction manager khác nhau đồng thời kích hoạt cùng một thread-bound synchronization context**. Trong hệ thống nhiều DataSource/manager, hãy đặt ranh giới rõ ràng, xem manager nào điều phối thread và resource nào được bind. Không nghĩ gọi `isSynchronizationActive()` cho biết “manager A đã bật” hay “manager B đã bật”: method này không trả danh tính manager.

## 6. Propagation thay đổi hai flag như thế nào?

Giả sử `JdbcTransactionManager`/`DataSourceTransactionManager` thuộc `AbstractPlatformTransactionManager`, synchronization policy `ALWAYS`, Spring proxy/template áp dụng thật và một thread có ranh giới được kiểm soát:

| Scope đang chạy | Có transaction ngoài lúc vào? | Sync | Actual | Ghi chú |
| --- | --- | --- | --- | --- |
| Code bên ngoài mọi Spring transaction boundary | Không | `false` | `false` | Chỉ khi thread đã được cleanup đúng |
| `REQUIRED` | Không | `true` | `true` | Mở physical JDBC transaction mới |
| `REQUIRED` | Có | `true` | `true` | Tham gia transaction hiện hữu |
| `REQUIRES_NEW` | Có hoặc không | `true` | `true` | Mở physical transaction mới, suspend outer nếu có |
| `SUPPORTS` | **Không** | **`true`** | **`false`** | “Empty” scope, không backend transaction |
| `SUPPORTS` | **Có** | `true` | `true` | Tham gia actual transaction của outer |
| `NOT_SUPPORTED` | Có | **`true`** | **`false`** | Tạm ngưng outer, scope rỗng có synchronization |
| `NOT_SUPPORTED` | Không | `true` | `false` | Scope không backend transaction |
| `NEVER` | Không | `true` | `false` | Có thể có empty synchronization theo ALWAYS |
| `NEVER` | Có | Không đi đến body | Không đi đến body | Spring báo lỗi vì propagation cấm existing transaction |
| `MANDATORY` | Không | Không đi đến body | Không đi đến body | Spring báo lỗi vì bắt buộc có existing transaction |
| `MANDATORY` | Có | `true` | `true` | Tham gia outer |
| `NESTED` (JDBC savepoint) | Có | `true` | `true` | Chia sẻ physical transaction, nested savepoint |
| `NESTED` | Không | `true` | `true` | Thường tạo actual transaction mới tương tự REQUIRED |

Các dòng là **kịch bản điển hình** với `ALWAYS`. Không dùng bảng làm quy luật cho manager reactive, manager tùy chỉnh hoặc cấu hình `ON_ACTUAL`/`NEVER`.

### 6.1. NOT_SUPPORTED: outer bị suspend nhưng không bị commit

Giả sử:

```text
outer @Transactional(REQUIRED)
  |
  +-- sync=true, actual=true, transaction T đang hoạt động
  |
  +-- inner @Transactional(NOT_SUPPORTED)
  |      - suspend T và synchronizations liên quan
  |      - sync=true, actual=false (khi ALWAYS)
  |      - SQL tại đây không thuộc transaction T
  |
  +-- inner kết thúc
  +-- resume T và original synchronizations
  |
  +-- sync=true, actual=true
  +-- outer cuối cùng commit hoặc rollback T
```

“NOT_SUPPORTED không có transaction” **không đồng nghĩa** “synchronization luôn false”. Đây chính là trường hợp phân biệt hai flag quan trọng.

Một `INSERT` chạy trong `NOT_SUPPORTED` bằng connection auto-commit có thể được commit **độc lập** với outer T. Nếu outer rollback sau đó, dữ liệu đã commit trong vùng NOT_SUPPORTED **không tự bị hoàn tác**.

### 6.2. SUPPORTS tham gia outer

`SUPPORTS` có nghĩa:

- Đã có transaction → **tham gia** transaction đó.
- Chưa có transaction → **không tạo backend transaction mới**.

Với `ALWAYS`, synchronization có thể vẫn active trong trường hợp thứ hai. Vì thế nhãn `SUPPORTS` tự nó không đủ để suy ra `actual=false` hoặc `actual=true` nếu chưa biết outer.

### 6.3. REQUIRES_NEW

`REQUIRES_NEW` có actual transaction độc lập trong scope của nó, nên trong body thông thường `true/true`. Điều này **không** cho biết liệu outer đã commit; outer có thể còn bị suspend và sau đó rollback. Cần phân biệt actual transaction đang active với **atomicity chung của toàn luồng nghiệp vụ**.

## 7. Kiểm tra flags đúng thời điểm và đúng thread

### 7.1. Đừng kiểm tra trước khi proxy mở transaction

Ví dụ một caller:

```java
System.out.println(
    TransactionSynchronizationManager.isActualTransactionActive()
);
orderService.placeOrder();
```

Dòng println chạy **trước** khi lời gọi đi qua proxy `@Transactional` của `placeOrder()`, nên có thể in `false` dù bên trong `placeOrder()` có transaction thật.

Để debug, log **bên trong** method đã được Spring intercept hoặc ở đoạn callback `TransactionTemplate` đang chạy.

### 7.2. Self-invocation có thể khiến annotation không được áp dụng

```java
@Service
public class ReportService {

    public void run() {
        this.supportsMethod(); // Không đi qua proxy trong Spring AOP mode.
    }

    @Transactional(propagation = Propagation.SUPPORTS)
    public void supportsMethod() {
        // Tại đây không tự mở SUPPORTS synchronization do annotation
        // nếu lời gọi là this.supportsMethod() và không có advice khác.
    }
}
```

Đây là **code minh họa**, cần imports và môi trường Spring. Nếu muốn quan sát flag do annotation tạo, gọi method từ **một bean khác qua injected proxy**. `TransactionTemplate` trong ví dụ phần 10 hoạt động thông qua lời gọi trực tiếp vào template nên tránh nhầm lẫn self-invocation khi học hai flag.

### 7.3. @Async, ExecutorService và thread khác

`TransactionSynchronizationManager` của imperative Spring là **thread-bound**. Tạo thread mới không tự sao chép transaction context:

```java
@Transactional
public void parent() {
    // Thread A: sync=true, actual=true

    executor.execute(() -> {
        // Thread B: không tự kế thừa transaction của Thread A.
        // Hai flag có thể đều false nếu B không mở scope Spring riêng.
    });
}
```

Mảnh code minh họa; `executor` cần được cung cấp. Nếu asynchronous task phải ghi dữ liệu atomic, hãy mở **transaction riêng** trên worker thread thông qua Spring bean/proxy hoặc template phù hợp. Không sao chép thô các ThreadLocal/resource holders giữa threads để “truyền transaction”, vì connection và cleanup cần owner rõ ràng.

### 7.4. Reactive TransactionSynchronizationManager là loại khác

Với Reactor/R2DBC, Spring có class:

```java
org.springframework.transaction.reactive.TransactionSynchronizationManager
```

Đây là API khác với:

```java
org.springframework.transaction.support.TransactionSynchronizationManager
```

Reactive transactions gắn với **Reactor context**, không dựa thuần túy vào ThreadLocal imperative. Đọc hai static flags của class `support` bên trong một reactive pipeline **không chứng minh** transaction R2DBC đang active hay inactive.

Đối với reactive transaction, dùng `ReactiveTransactionManager`/`TransactionalOperator` và các API quản lý reactive context tương ứng. Không dùng `JdbcTemplate` blocking hoặc `TransactionTemplate` imperative rồi giả định chúng tự chia transaction context với R2DBC.

## 8. Khi nào đăng ký synchronization callback?

### 8.1. Điều kiện kỹ thuật để gọi registerSynchronization

Ví dụ infrastructure/service integration:

```java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                // Dọn tài nguyên/ghi metric theo kết thúc scope.
            }
        });
}
```

Đây là **mảnh code minh họa**, không phải một ứng dụng đầy đủ. `isSynchronizationActive()` là guard phù hợp để tránh gọi `registerSynchronization(...)` khi synchronization không hoạt động. Nếu false mà vẫn gọi, Spring có thể ném `IllegalStateException`.

Tuy nhiên, callback được đăng ký **cho scope synchronization**, và scope đó có thể là “empty” `SUPPORTS` hoặc `NOT_SUPPORTED` **không có DB transaction thực**. Vì vậy hãy chọn callback phù hợp với semantics của integration.

### 8.2. Điều kiện “đã có transaction DB thật”

Nếu một integration cần đặc biệt tránh đăng ký “after commit” vào empty scope:

```java
boolean synchronizationActive =
    TransactionSynchronizationManager.isSynchronizationActive();
boolean actualTransactionActive =
    TransactionSynchronizationManager.isActualTransactionActive();

if (synchronizationActive && actualTransactionActive) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Ví dụ: tín hiệu để phát công việc sau COMMIT.
                // Tránh làm SQL ghi thêm vào transaction cũ tại đây.
            }
        });
}
```

Đây là **mẫu guard có điều kiện**, không phải bằng chứng tuyệt đối rằng “mọi manager nào cũng bảo đảm một COMMIT DB đang chờ”. Với manager thuộc `AbstractPlatformTransactionManager`, policy `ALWAYS`/`ON_ACTUAL`, có transaction thật theo marker và không có cấu hình lạ, đây là cách phân biệt case `SUPPORTS` empty với transaction thật.

**Không chỉ kiểm tra `actual=true`:** nếu synchronization bị tắt (ví dụ `SYNCHRONIZATION_NEVER`), `registerSynchronization` vẫn không hợp lệ. **Không chỉ kiểm tra `sync=true`:** điều đó có thể là empty scope.

### 8.3. Vì sao afterCommit cũng phải hiểu đúng?

Ở `AbstractPlatformTransactionManager`, transaction synchronization callbacks thuộc logic hoàn tất **transaction scope**. Với `SYNCHRONIZATION_ALWAYS`, một “empty” `SUPPORTS` scope không có backend transaction nhưng vẫn có callback lifecycle; tùy callback/đường completion, `afterCommit`/`afterCompletion` có thể được kích hoạt khi scope đó kết thúc “thành công”, **mà không có một COMMIT JDBC vật lý tương ứng**.

Do đó, đừng lấy việc chạy callback `afterCommit` từ một empty synchronization scope làm bằng chứng rằng dữ liệu đã commit DB. Nếu cần bảo đảm **event đi ra tương ứng với một bản ghi nghiệp vụ đã commit**, đánh giá transactional outbox hoặc cơ chế after-commit được gắn vào actual transaction thật, không chỉ dựa vào tên callback.

### 8.4. afterCompletion cũng không thay thế rollback status của nghiệp vụ

`TransactionSynchronization.afterCompletion(int status)` có thể nhận `STATUS_COMMITTED`, `STATUS_ROLLED_BACK` hoặc `STATUS_UNKNOWN` theo scope transaction manager. Trên empty scope, “completed” không tự mang ý nghĩa có database changes được xác nhận/hủy. Nếu cần trả kết quả nghiệp vụ, dùng kết quả service hoặc transaction status có contract rõ ràng, không suy từ callback ở một scope không có resource transaction.

## 9. Có connection được bind chưa chắc có backend transaction

Spring JDBC dùng `DataSourceUtils` cùng `TransactionSynchronizationManager` để lấy và giải phóng connection phù hợp với thread.

Ví dụ một lời gọi:

```java
jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM orders",
    Long.class
);
```

Khi có transaction thật, `JdbcTemplate` có thể dùng connection đã bind với transaction; SQL nằm trong cùng scope commit/rollback.

Nhưng dưới `PROPAGATION_SUPPORTS` **không có actual transaction** mà `SYNCHRONIZATION_ALWAYS`, Spring cũng có thể giữ/bind connection tạm trong synchronization scope để tái sử dụng và cleanup. Khi connection vẫn có `autoCommit=true` (chẳng hạn H2 mặc định trong demo), lệnh ghi **được commit theo từng statement** chứ không chờ một transaction vật lý từ template.

Đó là lý do:

- `hasResource(dataSource)` có thể là `true` mà `isActualTransactionActive()` vẫn `false`;
- `isSynchronizationActive()` không đồng nghĩa connection có `autoCommit=false`;
- kiểm tra một connection đã bind hoặc nhận callback completion **không chứng minh** transaction DB đã commit/rollback cùng service.

### 9.1. Đừng dùng hasResource làm “in transaction?”

`hasResource(dataSource)` chỉ cho biết Spring đã bind một resource dưới key `dataSource` trên thread. Việc resource có transaction thật hay chỉ đang được quản lý theo synchronization scope phụ thuộc manager và đường thực thi. Nếu cần xác minh DB commit/rollback, kiểm thử **trạng thái dữ liệu sau khi scope hoàn tất**.

### 9.2. Cần một transaction để nhiều lệnh SQL atomic?

Chọn propagation `REQUIRED`/transaction thật và cùng manager/resource:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void placeOrder() {
    // INSERT order
    // UPDATE inventory
    // INSERT ledger
}
```

Hoặc dùng `TransactionTemplate` với `PROPAGATION_REQUIRED`. `SUPPORTS` không có outer transaction **không bảo đảm atomicity nhiều lệnh**; một SQL có thể đã autocommit trước khi exception xảy ra ở SQL tiếp theo.

## 10. Project Java 17 chạy được: nhìn cờ và kiểm chứng commit/rollback

Dự án dưới đây dùng **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2**. Spring Boot 3.3.x quản lý dòng Spring Framework 6.1.x, phù hợp ví dụ hạ tầng imperative. Mục tiêu là quan sát flags **từ bên trong** `TransactionTemplate`, không cần AOP proxy để demo.

Ba ý cần chứng minh:

1. `SUPPORTS` không có outer: synchronization active, actual transaction inactive.
2. `REQUIRED` có actual transaction; `NOT_SUPPORTED` tạm ngưng nó và thường vẫn có empty synchronization.
3. Một INSERT trong empty `SUPPORTS` (H2 connection auto-commit) **không được rollback bởi exception của empty scope**, trong khi INSERT của `REQUIRED` bị rollback khi callback ném exception.

Các version cố định để tái lập, **không tuyên bố đây là phiên bản mới nhất**.

### 10.1. Cấu trúc file

```text
transaction-flags-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/
    ├── java/demo/flags/
    │   ├── FlagsApplication.java
    │   └── TxManagerConfig.java
    └── resources/
        └── application.yml
```

Bạn có thể tạo Gradle Wrapper bằng Spring Initializr. Mã dưới đây là một **project nhiều file**, không phải chương trình một file chỉ chạy bằng `javac` thiếu dependencies.

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-flags-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:flagsdemo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
```

H2 in-memory tồn tại trong JVM đang chạy; mỗi lần khởi động một process mới, database rỗng. `DB_CLOSE_DELAY=-1` chỉ giúp database sống tới lúc JVM kết thúc. Demo chủ động tạo bảng lúc runner bắt đầu, không dùng `schema.sql`.

### 10.2. Cấu hình manager với SYNCHRONIZATION_ALWAYS

**`src/main/java/demo/flags/TxManagerConfig.java`**

```java
package demo.flags;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;

@Configuration
public class TxManagerConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        manager.setTransactionSynchronization(
            AbstractPlatformTransactionManager
                .SYNCHRONIZATION_ALWAYS);

        return manager;
    }
}
```

Giải thích:

- `JdbcTransactionManager` quản lý transaction JDBC cho đúng `DataSource` mà `JdbcTemplate` sử dụng.
- `SYNCHRONIZATION_ALWAYS` là mặc định trong lớp nền; khai rõ để người học **không phụ thuộc vào assumption**.
- Spring Boot thường sẽ không tự tạo một manager JDBC khác khi đã có bean transaction manager do ứng dụng cung cấp.
- Demo chỉ dùng một manager và một DataSource; tránh nhập nhằng trong dự án đa resource.
- Không dùng setter `setActualTransactionActive(true)` để “bật” transaction: đây phải là việc của transaction manager.

### 10.3. Runner: outside, SUPPORTS, REQUIRED, NOT_SUPPORTED và join

**`src/main/java/demo/flags/FlagsApplication.java`**

```java
package demo.flags;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class FlagsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlagsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {

        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_flags_lab (" +
                "id INTEGER PRIMARY KEY, " +
                "note VARCHAR(30) NOT NULL)"
            );

            TransactionTemplate required =
                new TransactionTemplate(manager);

            TransactionTemplate supports =
                new TransactionTemplate(manager);
            supports.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_SUPPORTS);

            TransactionTemplate notSupported =
                new TransactionTemplate(manager);
            notSupported.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_NOT_SUPPORTED);

            System.out.println("outside: " + flags());

            try {
                supports.executeWithoutResult(status -> {
                    System.out.println(
                        "SUPPORTS no outer: " + flags());

                    // H2 connection autoCommit=true, không có backend tx.
                    jdbc.update(
                        "INSERT INTO tx_flags_lab(id, note) " +
                        "VALUES (1, 'auto-committed')");

                    throw new IllegalStateException(
                        "empty scope failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caught SUPPORTS failure: " + ex.getMessage());
            }

            System.out.println(
                "rows after SUPPORTS error: " + count(jdbc));

            try {
                required.executeWithoutResult(status -> {
                    System.out.println(
                        "REQUIRED outer: " + flags());

                    jdbc.update(
                        "INSERT INTO tx_flags_lab(id, note) " +
                        "VALUES (2, 'rollback-me')");

                    notSupported.executeWithoutResult(inner -> {
                        System.out.println(
                            "NOT_SUPPORTED suspended: " + flags());
                    });

                    System.out.println(
                        "REQUIRED resumed: " + flags());

                    throw new IllegalStateException(
                        "outer transaction failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println(
                    "caught REQUIRED failure: " + ex.getMessage());
            }

            System.out.println(
                "rows after REQUIRED error: " + count(jdbc));

            required.executeWithoutResult(status -> {
                supports.executeWithoutResult(inner -> {
                    System.out.println(
                        "SUPPORTS joined outer: " + flags());
                });
            });

            System.out.println("after all: " + flags());
        };
    }

    private static String flags() {
        return "sync=" +
            TransactionSynchronizationManager.isSynchronizationActive()
            + ", actual=" +
            TransactionSynchronizationManager.isActualTransactionActive();
    }

    private static Long count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_flags_lab",
            Long.class);
    }
}
```

Đây là Java 17 có thể biên dịch khi ghép đúng project/dependencies. Vì các callback được truyền trực tiếp vào `TransactionTemplate`, chúng không dựa vào việc method `demo(...)` có proxy `@Transactional`. Dù vậy, `JdbcTemplate` vẫn phải dùng cùng DataSource với manager.

### 10.4. Chạy và stdout dự kiến

Ở thư mục chứa Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ngoài các log của Gradle/Spring Boot, chương trình in **chính xác theo thứ tự**:

```text
outside: sync=false, actual=false
SUPPORTS no outer: sync=true, actual=false
caught SUPPORTS failure: empty scope failed
rows after SUPPORTS error: 1
REQUIRED outer: sync=true, actual=true
NOT_SUPPORTED suspended: sync=true, actual=false
REQUIRED resumed: sync=true, actual=true
caught REQUIRED failure: outer transaction failed
rows after REQUIRED error: 1
SUPPORTS joined outer: sync=true, actual=true
after all: sync=false, actual=false
```

**Giải thích từng giai đoạn:**

1. Runner chạy bên ngoài transaction Spring → `false/false`.
2. `SUPPORTS` khi chưa có outer tạo empty synchronization scope theo `ALWAYS` → `true/false`. Lệnh INSERT ID 1 được H2 JDBC connection auto-commit; exception ở callback **không có physical transaction nào để rollback**, nên sau khi catch vẫn có một hàng.
3. `REQUIRED` mở actual transaction → `true/true`. INSERT ID 2 vẫn đang thuộc transaction đó.
4. `NOT_SUPPORTED` tạm ngưng transaction ngoài, mở scope không có backend transaction nhưng có synchronization theo `ALWAYS` → `true/false`.
5. Khi NOT_SUPPORTED kết thúc, Spring phục hồi outer transaction → `true/true`.
6. Outer cố ý ném unchecked exception. `TransactionTemplate` rollback transaction JDBC của nó; ID 2 mất, ID 1 đã commit từ trước nên count vẫn bằng 1.
7. `SUPPORTS` được gọi **trong** một `REQUIRED` thật nên tham gia actual transaction ngoài → `true/true`.
8. Sau khi các scopes kết thúc, manager dọn thread-bound synchronization/metadata → `false/false`.

**Giới hạn của output:** giả định manager `SYNCHRONIZATION_ALWAYS`, H2 mặc định connection auto-commit ngoài actual transaction, không có transaction test/actor khác đang bao runner, connection pool hoạt động bình thường và tất cả file giữ nguyên. Nếu bạn thay policy manager, propagation hoặc database, phải xét lại output.

### 10.5. Điều khác biệt quan trọng mà phần SQL chứng minh

Bài toán không chỉ là in boolean. Hai phần code đều **ném `IllegalStateException`** nhưng dữ liệu khác nhau:

| Case | Flags trong callback | SQL trước lỗi | Kết quả sau lỗi |
| --- | --- | --- | --- |
| `SUPPORTS` không outer, `ALWAYS` | `true/false` | INSERT ID 1 | **ID 1 vẫn tồn tại** |
| `REQUIRED` mở transaction thật | `true/true` | INSERT ID 2 | **ID 2 bị rollback** |

Vì vậy việc chỉ log `isSynchronizationActive()=true` rồi tuyên bố “rollback bảo vệ dữ liệu” là một lỗi đánh giá transaction nghiêm trọng.

## 11. Thay synchronization policy: kiểm thử lại các flag

Nếu bạn đổi duy nhất trong `TxManagerConfig` thành:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager
        .SYNCHRONIZATION_ON_ACTUAL_TRANSACTION);
```

thì kỳ vọng chính:

- `SUPPORTS` **không** có outer: `sync=false, actual=false` vì không mở synchronization cho empty scope.
- `NOT_SUPPORTED` khi outer bị suspend: `sync=false, actual=false` trong scope không backend transaction.
- `REQUIRED` mở actual transaction: `sync=true, actual=true`.
- `SUPPORTS` tham gia outer có actual transaction: thường `sync=true, actual=true`.

**Hành vi rollback của SQL không tự thay đổi thành transactional trong SUPPORTS** khi tắt synchronization cho empty scope. INSERT ID 1 vẫn có thể auto-commit; flag chỉ giúp nhìn rõ hơn sự khác biệt.

Nếu thay bằng:

```java
manager.setTransactionSynchronization(
    AbstractPlatformTransactionManager.SYNCHRONIZATION_NEVER);
```

synchronization không mở cả ở actual transaction. Đừng lấy output của demo mặc định rồi thay vài chữ để tuyên bố mọi manager có cùng flags: đặc biệt `isActualTransactionActive` là thread-local marker có đường khởi tạo liên quan synchronization, nên có thể trả `false` ngay cả khi manager vẫn quản lý physical transaction ở chính thread đó. Cần **kiểm tra dữ liệu rollback sau lỗi** hoặc `TransactionStatus.hasTransaction()` khi dùng manager/status thích hợp để phân biệt transaction vật lý.

**Không thay đổi synchronization policy trên manager singleton đang phục vụ request thực trong production.** Nếu cần đổi, cấu hình từ lúc startup, đánh giá integrations dựa vào resource binding/callbacks, chạy test trên manager/DB thực tế.

## 12. Dùng TransactionStatus khi chính bạn là người mở scope

Nếu code dùng `TransactionTemplate`, callback nhận `TransactionStatus`. Khi quan tâm “scope hiện tại có backend transaction được manager ghi nhận không?”, API:

```java
TransactionTemplate template = new TransactionTemplate(manager);

template.executeWithoutResult(status -> {
    boolean actualScope = status.hasTransaction();
    boolean newScope = status.isNewTransaction();

    System.out.println("hasTransaction=" + actualScope);
    System.out.println("isNewTransaction=" + newScope);
});
```

`hasTransaction()` (có trong API Spring transaction execution hiện đại, ví dụ Spring 6.1) thể hiện một contract theo **status của manager** có ý nghĩa trực tiếp hơn việc đoán từ synchronization flag ở một thread. `isNewTransaction()` có nghĩa khác: nó nói scope có được xem là transaction mới hay không, **không** phải “có actual transaction” trong mọi implementation. Khi tham gia outer, `hasTransaction()` có thể true còn `isNewTransaction()` false.

Nhưng `TransactionStatus` cũng không phải một chứng thư DB commit: callback còn đang chạy, và một transaction có thể bị rollback-only hoặc commit thất bại. Muốn chứng minh kết quả nghiệp vụ, kiểm tra state sau transaction completion.

**Lưu ý:** ví dụ `SUPPORTS` không owner trong phần 10 có thể cho `status.hasTransaction()=false` dù `isSynchronizationActive()=true`. Đây là một cách khẳng định đúng sự khác nhau giữa **scope đồng bộ hóa** và **resource transaction**.

## 13. Dùng @Transactional với hai service để quan sát propagation

`TransactionTemplate` hữu ích để demo các flag, nhưng annotation cũng dùng cùng hạ tầng. Ví dụ thiết kế hai bean:

```java
@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void outer() {
        inner.supports();
        inner.noTransaction();
    }
}

@Service
public class InnerService {

    @Transactional(propagation = Propagation.SUPPORTS)
    public void supports() {
        // Khi do outer gọi: thường sync=true, actual=true.
        // Khi caller không có tx: có thể sync=true, actual=false.
    }

    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public void noTransaction() {
        // Với ALWAYS, sync=true, actual=false nếu outer bị suspend.
    }
}
```

Đây là **mã minh họa**, cần imports `@Service`, `@Transactional`, `Propagation`, cấu hình manager và lời gọi qua Spring bean/proxy. Cần thêm log flags vào thân method nếu muốn chạy kiểm chứng. Đừng đưa hai classes minh họa này vào project demo phần 10 rồi giả định runner sẽ tự gọi chúng.

Nếu `outer()` bị gọi qua `this.outer()` từ cùng bean không qua proxy, transaction advice có thể không được thực hiện. Khi đó log flags không phản ánh propagation mà bạn tưởng đang chạy.

## 14. Vì sao không dùng hai boolean để quyết định nghiệp vụ?

### 14.1. “Nếu sync active thì gửi event afterCommit” chưa đủ

Một logic nguy hiểm:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    registerAfterCommitNotification();
} else {
    sendNotificationNow();
}
```

Trong `SUPPORTS` empty scope theo `ALWAYS`, nhánh đầu sẽ được chọn dù **không có actual transaction**. Nếu code mong notification chỉ phát sau khi DB commit, contract đã sai. Ngay cả khi cả hai flag `true`, scope có thể đang tham gia outer và commit xảy ra **sau method hiện tại**.

Ưu tiên thiết kế rõ ràng:

- Ghi một outbox record **trong cùng actual DB transaction** với thay đổi nghiệp vụ.
- Publisher xử lý record sau commit, với retry/idempotency.
- Hoặc dùng transaction-bound event/synchronization được đăng ký đúng vào actual transaction, có chính sách rõ cho trường hợp **không có transaction**.

### 14.2. “Nếu actual=false thì thao tác DB luôn autocommit” cũng không phải luật toàn cục

`isActualTransactionActive=false` là **marker của Spring** trong thread hiện tại. Một connection được tự quản bên ngoài Spring vẫn có thể có transaction đang mở; hoặc một manager dùng `SYNCHRONIZATION_NEVER` khiến marker không phơi bày như trường hợp thông thường. Do đó không viết business logic phân nhánh dựa trên marker để bật/tắt kiểm tra dữ liệu.

### 14.3. “Nếu actual=true thì chắc chắn commit” cũng sai

Actual transaction đang active có thể:

- Bị đánh dấu rollback-only bởi scope bên trong.
- Gặp constraint violation, deadlock, lỗi connection hoặc timeout.
- Bị caller outer quyết định rollback sau khi method con trả về.
- Có kết quả commit chưa biết nếu lỗi kết nối xảy ra lúc completion.

Hai booleans là **trạng thái tại một thời điểm**, không dự báo kết quả cuối cùng của transaction.

### 14.4. “readOnly=true thì có actual transaction” không nhất thiết

`TransactionSynchronizationManager.isCurrentTransactionReadOnly()` là metadata của current scope được Spring phơi bày. Trong empty `SUPPORTS` scope được khai read-only, nó vẫn có thể `true` khi `actual=false`; đồng thời read-only metadata **không bảo đảm** database cấm mọi câu SQL ghi.

Muốn xác nhận resource transaction, đừng thay `isActualTransactionActive` bằng `isCurrentTransactionReadOnly` hoặc `getCurrentTransactionIsolationLevel() != null`.

## 15. Checklist khi debug “transaction không rollback”

Khi thấy SQL vẫn commit dù log `sync=true`:

1. **Đọc cả hai flag**: `sync=?`, `actual=?` tại **bên trong** method/callback đúng scope.
2. **Xác nhận propagation**: có phải `SUPPORTS`/`NOT_SUPPORTED`/`NEVER`? Có outer transaction thật lúc method bắt đầu không?
3. **Xác nhận synchronization policy**: manager đang `ALWAYS`, `ON_ACTUAL` hay `NEVER`?
4. **Xác nhận bean transaction manager**: đúng manager quản lý DataSource/EntityManager mà DAO dùng?
5. **Xác nhận proxy boundary**: method `@Transactional` có được gọi qua Spring proxy, hay là self-invocation/`new Service()`?
6. **Xác nhận thread**: code DB có chạy ở cùng thread imperative transaction không? Có `@Async`/ExecutorService không?
7. **Xác nhận connection**: JDBC có dùng `JdbcTemplate`/`DataSourceUtils` đúng DataSource? Có connection riêng ngoài Spring?
8. **Xác nhận exception**: runtime/checked? Có bị catch và nuốt trong method? Transaction có rollback rule phù hợp không?
9. **Xác nhận transaction owner**: scope đang join outer hay tự mở? Outer có rollback-only không?
10. **Đọc dữ liệu sau completion**: đừng suy từ SQL log hoặc marker đang true trước commit.
11. **Kiểm tra driver/DB**: autoCommit, isolation, pool behavior, constraint và lỗi commit.
12. **Reactive hay imperative?** Nếu reactive, dùng đúng reactive transaction context API.

### Kịch bản test tối thiểu

| Tình huống | Sync / Actual (ALWAYS) | Việc cần kiểm chứng |
| --- | --- | --- |
| Ngoài mọi scope | false/false | Không còn callback/resource thread-local bị rò rỉ |
| SUPPORTS không outer | **true/false** | Ghi JDBC có thể autocommit; exception không rollback DB |
| REQUIRED mở mới | true/true | Runtime exception rollback DB thay đổi trong scope |
| SUPPORTS nằm trong REQUIRED | true/true | Tham gia owner; không commit riêng |
| NOT_SUPPORTED trong REQUIRED | **true/false** | Outer suspend/resume, SQL trong vùng no-tx nằm ngoài rollback của outer |
| REQUIRED sau NOT_SUPPORTED | true/true | Trạng thái outer được restore |
| ON_ACTUAL + SUPPORTS không outer | false/false | Không còn empty synchronization |
| NEVER + REQUIRED | Có thể false/false theo thread marker | DB transaction vẫn có thể hoạt động; kiểm tra `status.hasTransaction()` và commit/rollback thực |

**Không cố “sửa” giá trị boolean để test pass.** Hãy sửa ranh giới transaction, transaction manager, propagation hoặc resource routing, rồi kiểm chứng bằng DB thực.

## 16. Câu hỏi tự kiểm tra

**1. `isSynchronizationActive()=true` có đủ kết luận JDBC INSERT đang được bảo vệ bằng transaction rollback không?**

Không. `SUPPORTS` không outer dưới `SYNCHRONIZATION_ALWAYS` có thể `true/false` và INSERT trên connection auto-commit vẫn được lưu khi code ném lỗi sau đó.

**2. `isActualTransactionActive()=true` nghĩa là method hiện tại sẽ tự commit khi return?**

Không. Method có thể đang tham gia transaction outer, hoặc transaction sẽ rollback/commit thất bại. Marker chỉ cho biết thread được Spring đánh dấu có actual transaction tại thời điểm kiểm tra.

**3. Có thể gọi `registerSynchronization` khi actual=true nhưng synchronization=false không?**

Không. Điều kiện kỹ thuật trực tiếp là synchronization **đang active**. Muốn đăng ký callback cho actual transaction thì kiểm tra cả hai trong mô hình manager thông thường và hiểu scope.

**4. Vì sao `@Transactional(SUPPORTS)` đôi khi cho actual=true, đôi khi false?**

Vì SUPPORTS **tham gia transaction có sẵn nếu có**, còn khi không có outer thì không mở backend transaction.

**5. `NOT_SUPPORTED` trong outer REQUIRED có nhất định cho synchronization=false không?**

Không. Với `SYNCHRONIZATION_ALWAYS`, nó có thể tạo empty synchronization scope nên `sync=true, actual=false` trong khi outer bị suspend.

**6. Thay mode sang `SYNCHRONIZATION_ON_ACTUAL_TRANSACTION` tác động thế nào?**

Nó không kích hoạt synchronization cho empty scopes. SUPPORTS không outer thường thành `false/false`; REQUIRED thật vẫn thường `true/true`.

**7. Nếu manager đặt `SYNCHRONIZATION_NEVER`, có thể dùng `actual=false` để khẳng định không có JDBC transaction không?**

Không. Marker hiện hữu phụ thuộc đường khởi tạo synchronization của manager; backend transaction có thể vẫn active dù hai flag không cho thấy điều đó.

**8. Hai flag có hoạt động như vậy trong một reactive R2DBC transaction không?**

Không dùng hai static flags imperative để suy ra transaction reactive; reactive context phải được đọc bằng API reactive đúng.

**9. Một connection đã bind ở `getResource(dataSource)` có chắc `autoCommit=false` không?**

Không. Spring có thể bind/reuse connection chỉ trong synchronization scope khi không có backend transaction thật.

**10. Nếu muốn tất cả SQL trong service rollback cùng nhau, nên cấu hình gì?**

Dùng actual transaction do đúng `PlatformTransactionManager` quản lý, ví dụ `@Transactional(REQUIRED)` qua proxy hoặc `TransactionTemplate` với `REQUIRED`. Đảm bảo DAO dùng resource chung, exception/rollback rules đúng và kiểm thử sau completion.

## 17. Kết luận

**`isSynchronizationActive()` và `isActualTransactionActive()` không đồng nghĩa.**

- `isSynchronizationActive()`: **cơ chế synchronization/callback của Spring đã mở trên thread chưa?**
- `isActualTransactionActive()`: **Spring đang đánh dấu thread liên kết với actual resource transaction chưa?**

Trong cấu hình thường dùng `SYNCHRONIZATION_ALWAYS`, `SUPPORTS` không owner hoặc `NOT_SUPPORTED` có thể cho **sync=true, actual=false**. Đó là trạng thái hợp lệ. Ngược lại, khi tắt synchronization, các marker có thể không được phơi bày theo cách bạn mong đợi dù underlying transaction manager vẫn quản lý backend transaction.

Để ứng dụng đúng: chọn transaction boundary và propagation rõ ràng, dùng manager đúng DataSource/JPA resource, gọi qua proxy nếu dùng `@Transactional`, tránh suy luận rollback/commit chỉ từ hai booleans, và **kiểm chứng dữ liệu sau khi transaction kết thúc**. Với reactive applications, dùng transaction context của Reactor thay vì ThreadLocal imperative.

## Tài liệu chính thức

- Spring Framework 6.1 — `TransactionSynchronizationManager` Javadoc, `isSynchronizationActive` và `isActualTransactionActive`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework 6.1 — `AbstractPlatformTransactionManager` và các mode `SYNCHRONIZATION_ALWAYS` / `ON_ACTUAL_TRANSACTION` / `NEVER`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework 6.1 — `TransactionStatus`, `hasTransaction`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Programmatic Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — *TransactionSynchronization* lifecycle: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `DataSourceUtils` và thread-bound JDBC connections: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — Reactive `TransactionSynchronizationManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionSynchronizationManager.html
- Spring Framework source — `AbstractPlatformTransactionManager`, các nhánh `prepareSynchronization`, `handleExistingTransaction`: https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java
