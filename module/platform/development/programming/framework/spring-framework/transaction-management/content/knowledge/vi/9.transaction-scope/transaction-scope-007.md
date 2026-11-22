# Trạng thái rollback-only cục bộ và toàn cục trong Spring Transaction Management

> **Spring Framework — Transaction Management → Phạm vi giao dịch.** Tại sao một phương thức bên ngoài không gọi `setRollbackOnly()`, thậm chí đã bắt hết exception của phương thức bên trong, mà cuối cùng vẫn không thể commit? Câu trả lời nằm ở sự khác nhau giữa **rollback-only cục bộ trên `TransactionStatus` của một logical transaction scope** và **rollback-only toàn cục của physical transaction được nhiều scope dùng chung**.

## 1. Tóm tắt cốt lõi

Spring phân biệt hai lớp trạng thái quan trọng:

- **Local rollback-only**: cờ gắn với **một đối tượng `TransactionStatus`** của ranh giới giao dịch hiện tại. Với `AbstractTransactionStatus`, ứng dụng gọi `status.setRollbackOnly()` sẽ làm `status.isLocalRollbackOnly()` trả `true`.
- **Global rollback-only**: trạng thái **giao dịch vật lý/tài nguyên bên dưới** đã được đánh dấu chỉ có thể rollback. `DefaultTransactionStatus` có thể đọc trạng thái này thông qua transaction object, thường là `SmartTransactionObject` và các resource holders/coordinator.
- **Effective rollback-only**: `TransactionStatus.isRollbackOnly()` của `AbstractTransactionStatus` có giá trị `true` nếu **local hoặc global** đang true.

Một công thức ghi nhớ cho triển khai status phổ biến:

```text
effectiveRollbackOnly = localRollbackOnly || globalRollbackOnly
```

**Nhưng đừng đồng nhất ba cờ.** Có thể tồn tại trạng thái:

```text
outer.localRollbackOnly  = false
outer.globalRollbackOnly = true
outer.isRollbackOnly()    = true
```

Nghĩa là **outer chưa chủ động yêu cầu rollback**, nhưng physical transaction mà nó đang điều phối đã được một inner scope, transaction coordinator hoặc tài nguyên đánh dấu rollback-only. Khi outer cố commit, Spring thường phải rollback và báo `UnexpectedRollbackException` cho caller.

> **Phạm vi giải thích:** Các API `isLocalRollbackOnly()` / `isGlobalRollbackOnly()` dưới đây thuộc các lớp thực thi `AbstractTransactionStatus`/`DefaultTransactionStatus`, không phải phương thức bắt buộc có trên mọi triển khai `TransactionStatus`. Phần lớn ví dụ dùng imperative `PlatformTransactionManager` và `PROPAGATION_REQUIRED`; reactive transactions có cơ chế context khác.

## 2. Nền tảng: logical scope không phải physical transaction

Một method `@Transactional` được Spring intercept tạo một **logical transaction scope**. Điều đó không đồng nghĩa luôn có một physical transaction mới. Với `Propagation.REQUIRED` (mặc định), Spring sẽ **tham gia** transaction hiện có nếu tài nguyên/manager cho phép; nếu chưa có thì mới tạo transaction vật lý mới.

```text
Client
  |
  +-- OrderService.outer() @Transactional(REQUIRED)
  |        |
  |        +-- logical scope OUTER: TransactionStatus A
  |        |       local flag A
  |        |
  |        +-- AuditService.inner() @Transactional(REQUIRED)
  |                |
  |                +-- logical scope INNER: TransactionStatus B
  |                        local flag B
  |
  +-------------------------+
                            |
                            v
               MỘT PHYSICAL TRANSACTION T1
                 global rollback-only state
                 JDBC Connection / JPA resource
```

Khi inner là `REQUIRED` và cùng manager/datasource, hai logical scopes A và B có thể cùng hướng tới T1. Mỗi scope có quyền yêu cầu rollback theo quy tắc của riêng mình, nhưng **commit vật lý cho T1 không thể xảy ra nếu T1 đã bị đánh dấu rollback-only**.

Không được hiểu “local” là giao dịch cục bộ một database (đối lập distributed transaction). Trong chủ đề này, **local = cờ trên một `TransactionStatus`/logical scope**, còn **global = cờ ở underlying transaction dùng chung**. Một `JdbcTransactionManager` điều phối một JDBC datasource vẫn có cả khái niệm local và global rollback-only. “Global” ở đây **không nhất thiết** nói đến XA/JTA hay nhiều database.

### Hai loại trạng thái ở những lớp khác nhau

| Câu hỏi | Cờ/đối tượng trả lời | Ý nghĩa |
| --- | --- | --- |
| Scope hiện tại **tự** yêu cầu rollback chưa? | `AbstractTransactionStatus.isLocalRollbackOnly()` | Chỉ cờ local trên `TransactionStatus` hiện tại. |
| Underlying transaction đã bị đánh dấu không thể commit chưa? | `DefaultTransactionStatus.isGlobalRollbackOnly()` | Kiểm tra rollback-only của transaction object tương ứng nếu hỗ trợ. |
| Có dấu hiệu rollback-only **bất kể nguồn** chưa? | `TransactionStatus.isRollbackOnly()` | Trạng thái tổng hợp; thường là local OR global. |
| Scope có bắt đầu physical transaction mới không? | `TransactionStatus.isNewTransaction()` | `true` nếu manager xem transaction của scope là mới. |
| Scope đang giữ savepoint không? | `TransactionStatus.hasSavepoint()` | Có thể liên quan `NESTED`, không phải dấu hiệu global rollback-only. |
| Transaction scope đã hoàn tất chưa? | `TransactionStatus.isCompleted()` | Đã commit hoặc rollback scope, không cho biết kết quả commit của transaction khác. |

`isNewTransaction() == false` **không có nghĩa “không có transaction”**. Nó có thể là một scope `REQUIRED` đang tham gia transaction outer. Có thể dùng `TransactionStatus.hasTransaction()` trên phiên bản Spring hỗ trợ `TransactionExecution` để phân biệt có actual transaction hay không, và so với `TransactionSynchronizationManager.isActualTransactionActive()` khi phù hợp.

## 3. Cách Spring lưu hai cờ

### 3.1. Cờ local thuộc `AbstractTransactionStatus`

`AbstractTransactionStatus` thực thi những thao tác cơ bản:

```java
// Các tên method thật; đoạn này chỉ minh họa cách gọi API.
org.springframework.transaction.TransactionStatus status =
        org.springframework.transaction.interceptor.TransactionAspectSupport
                .currentTransactionStatus();

status.setRollbackOnly();          // Đặt cờ trên scope hiện hành.
boolean effective = status.isRollbackOnly();
```

Fragment trên phải chạy **bên trong method đang được Spring transaction aspect quản lý**; gọi ngoài method đó có thể ném `NoTransactionException`. Trong `AbstractTransactionStatus`, `setRollbackOnly()` đánh dấu local flag. Sau lệnh đó, dù underlying resource còn chưa ghi nhận global flag, `isRollbackOnly()` vẫn true.

Có thể kiểm tra chi tiết trên một implementation tương ứng:

```java
var status =
        org.springframework.transaction.interceptor.TransactionAspectSupport
                .currentTransactionStatus();

if (status instanceof
        org.springframework.transaction.support.AbstractTransactionStatus s) {
    System.out.println("local=" + s.isLocalRollbackOnly());
    System.out.println("global=" + s.isGlobalRollbackOnly());
    System.out.println("effective=" + s.isRollbackOnly());
}
```

Đây là **fragment chẩn đoán**. `instanceof` bảo vệ khỏi việc coi implementation detail là public contract của mọi `TransactionStatus`.

### 3.2. Cờ global thuộc underlying transaction

`DefaultTransactionStatus` kiểm tra global rollback-only bằng transaction object bên dưới nếu object đó hỗ trợ `SmartTransactionObject`. Với JDBC transaction manager, transaction object có thể phản ánh trạng thái của `ConnectionHolder`. Với JTA coordinator, trạng thái marked-for-rollback có thể đến từ transaction manager của hệ thống; với JPA, provider/resource có thể góp phần quyết định transaction còn commit được không.

Điều này có hai hệ quả:

1. Một scope có local flag `false` vẫn có thể thấy global flag `true` nếu **scope khác** đã làm underlying transaction rollback-only.
2. Không phải mọi tài nguyên đều báo global rollback-only cùng một cách/tại cùng một thời điểm. Trường hợp database transaction bị hỏng do lỗi SQL có thể khiến commit thất bại ngay cả khi API chẩn đoán global flag chưa phản ánh đầy đủ tình trạng của database.

Không nên khẳng định `isGlobalRollbackOnly()==false` chắc chắn đảm bảo commit thành công. Constraint violation, deadlock, timeout, network failure hoặc commit failure có thể xảy ra tiếp theo.

### 3.3. Bảng chân trị thường gặp

| Local | Global | `isRollbackOnly()` | Ý nghĩa ở scope hiện tại |
| --- | --- | --- | --- |
| `false` | `false` | `false` | Chưa thấy yêu cầu rollback-only, **không** phải bảo đảm commit chắc chắn. |
| `true` | `false` | `true` | Chính scope này đã tự yêu cầu rollback, nhưng underlying transaction có thể chưa được đánh dấu global tại thời điểm quan sát. |
| `false` | `true` | `true` | Scope hiện tại chưa tự yêu cầu rollback; shared transaction đã bị đánh dấu không thể commit. |
| `true` | `true` | `true` | Cả scope hiện tại và shared transaction đều rollback-only. |

Bảng dựa trên contract của `AbstractTransactionStatus`; luôn kiểm tra manager/provider khi cần chẩn đoán triển khai không thuộc họ này.

## 4. Kịch bản A — Outer tự set local rollback-only

Một method `@Transactional` mở physical transaction mới và gọi `setRollbackOnly()` trên `TransactionStatus` của **chính nó**:

```text
outer @Transactional REQUIRED
  |
  +-- begin physical T1
  +-- INSERT order
  +-- currentTransactionStatus().setRollbackOnly()
  |        outer.local = true
  |        outer.global có thể vẫn false tại thời điểm này
  +-- outer trả về BÌNH THƯỜNG
  |
  +-- TransactionInterceptor gọi manager.commit(outerStatus)
          |
          +-- manager thấy local rollback-only
          +-- xử lý rollback T1
          +-- thường KHÔNG ném UnexpectedRollbackException
              chỉ vì outer đã tự đánh dấu local
```

`commit(...)` trong API manager là đường hoàn tất thông thường sau khi method trả về; manager vẫn kiểm tra trạng thái để chuyển thành rollback. Đây **không phải** “commit dữ liệu rồi rollback lại”, mà là manager chọn hoàn tất bằng rollback do biết trước local flag.

Với `AbstractPlatformTransactionManager`, khi **scope khởi tạo transaction tự đánh dấu rollback-only**, rollback là kết quả đã được scope đó chủ động yêu cầu. Caller của method có thể nhận giá trị trả về bình thường trừ khi chính thao tác rollback hoặc các bước khác gặp lỗi. Vì vậy:

**Method trả về bình thường chưa chứng minh transaction đã commit.**

Ví dụ fragment:

```java
@Transactional
public boolean reserve() {
    jdbcTemplate.update(
        "INSERT INTO reservations(id) VALUES (1)");
    TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
    return false;
}
```

Có thể trả về `false` bình thường trong khi insert bị rollback. Trong thiết kế production, nên có cách báo nghiệp vụ rõ ràng cho caller thay vì khiến caller vô tình tưởng dữ liệu đã được ghi.

## 5. Kịch bản B — Inner `REQUIRED` tự set local, outer thấy global

Đây là ví dụ quan trọng nhất về **local và global khác nhau**.

Giả sử có hai Spring beans, các method được gọi qua Spring proxy, cùng `JdbcTransactionManager` và datasource:

```java
@Service
class InnerService {
    @Transactional // REQUIRED mặc định
    public void validateAndWrite() {
        // Ghi một số dữ liệu.
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void placeOrder() {
        // Ghi dữ liệu khác.
        inner.validateAndWrite();
        // Method có thể vẫn chạy tiếp, không thấy exception tại đây.
    }
}
```

Đây là **fragment**: cần imports, logic lưu dữ liệu và Spring context thực tế. Luồng chính:

1. Outer bắt đầu physical transaction T1, có `TransactionStatus OUTER` và local flag false.
2. Inner `REQUIRED` được intercept, tham gia T1, có **`TransactionStatus INNER` riêng**, local flag false ban đầu.
3. Inner gọi `currentTransactionStatus().setRollbackOnly()`. Tại thời điểm đó, **inner.local=true**, dù outer.local vẫn false.
4. Inner trả về bình thường; interceptor hoàn tất logical scope inner. Đối với một *participating* `REQUIRED` scope, yêu cầu rollback-only của inner được lan đến underlying transaction bằng cách đánh dấu **global rollback-only trên T1**.
5. Outer chạy tiếp: **outer.local=false nhưng outer.global=true**, nên `outer.isRollbackOnly()==true`.
6. Outer trả về bình thường; interceptor/manager của outer cố hoàn tất transaction. T1 không thể commit. Với chính sách thông thường, Spring rollback T1 rồi báo `UnexpectedRollbackException` cho caller của outer.

Dòng thời gian:

```text
Thời điểm        OUTER local    INNER local    T1 global      Kết quả
-----------      -----------    -----------    ---------      ------------------
T1 mới           false          (chưa có)      false          Có thể commit
Vào inner        false          false          false          Cùng T1
Inner set flag   false          true           false (*)      Inner effective=true
Inner kết thúc   false          (xong)         true           T1 chỉ được rollback
Outer tiếp tục   false          (xong)         true           Outer effective=true
Outer commit     false          (xong)         true           Rollback + UE
```

(*) Trạng thái ở ngay sau lời gọi `setRollbackOnly()` của inner là một mô hình thông thường với `DefaultTransactionStatus` và `JdbcTransactionManager`. Tùy manager/provider, underlying transaction có thể được đánh dấu ở thời điểm khác; không lấy thời điểm cập nhật internal flag làm API contract chung.

**Điểm tinh tế:** hành vi này xảy ra ngay cả khi inner **không ném exception**. Chỉ riêng `setRollbackOnly()` cũng đủ để ngăn outer commit sau khi inner scope đã hoàn tất tham gia transaction.

### Vì sao outer nhận `UnexpectedRollbackException`?

Theo Spring, outer **chưa chủ động** quyết định rollback ở scope của chính mình; nó đi tới ranh giới commit với kỳ vọng có thể commit. Nhưng physical transaction đã bị scope khác đánh dấu rollback-only. Nếu Spring lặng lẽ trả về như thể commit thành công, caller dễ hiểu sai kết quả. `UnexpectedRollbackException` báo rõ điều kiện “transaction bị rollback khi caller yêu cầu commit”.

Thông thường exception đó xuất hiện ở **outermost transaction boundary**, sau khi thân `placeOrder()` đã đi hết. Vì vậy một `try/catch` *bên trong chính thân outer method* không thể bắt một `UnexpectedRollbackException` chỉ được tạo **sau khi method return** tại outer interceptor. Muốn xử lý kết quả này, caller bên ngoài proxy của outer mới là vị trí nhận exception phù hợp.

## 6. Kịch bản C — Inner ném exception và outer bắt lại

Không chỉ lời gọi `setRollbackOnly()` thủ công; rollback rules của `@Transactional` cũng có thể khiến **inner interceptor đánh dấu shared transaction rollback-only**.

```java
@Service
class InnerService {
    @Transactional // REQUIRED
    public void charge() {
        throw new IllegalStateException("charge failed");
    }
}

@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional // REQUIRED
    public void submit() {
        try {
            inner.charge();
        } catch (IllegalStateException ex) {
            // Bắt exception của inner.
        }
        // Outer trả về bình thường, nhưng T1 có thể đã global rollback-only.
    }
}
```

Các class trên chỉ minh họa, chưa phải chương trình độc lập. Trong trường hợp manager dựa trên `AbstractPlatformTransactionManager` với mặc định `globalRollbackOnParticipationFailure=true`, một inner `REQUIRED` scope thất bại và được yêu cầu rollback do unchecked exception sẽ khiến T1 được **đánh dấu global rollback-only**. Outer bắt exception **không xóa** được trạng thái đó.

Dòng thời gian:

```text
outer T1: INSERT A
   |
   +-- inner REQUIRED: INSERT B
   |       |
   |       +-- throw RuntimeException
   |       +-- TransactionInterceptor áp dụng rollback rule
   |       +-- participating rollback => mark T1 global rollback-only
   |
   +-- outer catch RuntimeException
   +-- outer tiếp tục hoặc return
   |
   +-- manager cố commit T1
           |
           +-- rollback T1 (A và B)
           +-- UnexpectedRollbackException tại outer boundary
```

Một thay đổi cờ `globalRollbackOnParticipationFailure=false` có thể thay đổi **cách manager xử lý participating rollback do exception**, nhưng không làm hệ thống tự động an toàn: provider/DB có thể không thể tiếp tục sau data-access failure. Đặc biệt, nó **không** làm mất hiệu lực yêu cầu `setRollbackOnly()` thủ công của inner; xem mục 9.

### Khi exception bị bắt trước khi thoát khỏi inner

Giả sử inner tự bắt một `RuntimeException` rồi trả về bình thường và **không** gọi `setRollbackOnly()`. Khi đó transaction interceptor của inner không thấy exception thoát ra, nên nó không thể áp dụng rollback rule dựa trên exception đã bị nuốt. Nếu resource chưa tự chuyển rollback-only, transaction có thể commit.

Do đó câu hỏi không phải chỉ “có exception xảy ra ở đâu đó không?” mà là:

- Exception có **thoát khỏi scope được intercept** không?
- Rollback rules của scope đó yêu cầu gì?
- Code có gọi `setRollbackOnly()` không?
- Underlying resource đã tự đánh dấu rollback-only chưa?

## 7. `TransactionStatus`, `TransactionAspectSupport` và các API chẩn đoán

### 7.1. Đọc status của scope hiện tại

Trong imperative `@Transactional` method đi qua Spring transaction advice:

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

status.setRollbackOnly();
System.out.println(status.isRollbackOnly());
```

Fragment này không được đặt ở class body; nó là nội dung bên trong một method. API `currentTransactionStatus()` trả **status của locally declared transaction boundary**, không phải một singleton status cho cả thread. Khi inner method đang chạy, nó thấy status của **inner**; sau khi inner hoàn tất và quay lại outer, lời gọi tương tự thấy status **outer**.

Nếu gọi từ code không có TransactionAspectSupport-managed scope phù hợp, nó có thể ném `NoTransactionException`. Không dùng method này như một API tra cứu trạng thái giao dịch toàn cục từ bất kỳ thread hoặc background task nào.

### 7.2. Đọc riêng local/global nếu implementation hỗ trợ

`TransactionStatus` chuẩn công khai `isRollbackOnly()`, nhưng không bắt buộc công khai hai method `isLocalRollbackOnly()` và `isGlobalRollbackOnly()`. Trong những trường hợp `DefaultTransactionStatus`:

```java
TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

if (status instanceof AbstractTransactionStatus s) {
    boolean local = s.isLocalRollbackOnly();
    boolean global = s.isGlobalRollbackOnly();
    boolean effective = s.isRollbackOnly();

    System.out.printf(
        "local=%s, global=%s, effective=%s%n",
        local, global, effective
    );
}
```

Fragment yêu cầu imports `org.springframework.transaction.TransactionStatus`, `org.springframework.transaction.interceptor.TransactionAspectSupport` và `org.springframework.transaction.support.AbstractTransactionStatus`. Nếu cần code portable qua nhiều transaction managers/implementations, ưu tiên `TransactionStatus.isRollbackOnly()`; coi hai cờ chi tiết là thông tin chẩn đoán.

### 7.3. `TransactionSynchronizationManager` không thay thế `TransactionStatus`

`TransactionSynchronizationManager.isActualTransactionActive()` cho biết Spring đang coi một **actual imperative transaction** là active trên thread hiện tại. Nó **không** trực tiếp nói transaction đó còn commit được hay đã rollback-only.

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

Fragment cần import `org.springframework.transaction.support.TransactionSynchronizationManager`. `readOnly` và `isolation` là đặc tính giao dịch, **không phải** cờ rollback-only. Tình huống `active=true` và `globalRollbackOnly=true` là hoàn toàn có thể xảy ra: transaction vẫn còn active về mặt scope nhưng đã không còn khả năng commit.

### 7.4. Thread-local và reactive context

Các ví dụ nêu `TransactionAspectSupport.currentTransactionStatus()` ở đường **imperative**. Với reactive transactions (`ReactiveTransactionManager`), transaction context gắn với Reactor `Context`/subscription, không nhất thiết cùng mô hình thread-local. Không sao chép các lệnh chẩn đoán thread-bound vào reactive pipeline rồi diễn giải chúng như một trạng thái R2DBC toàn cục. Nếu chuyển sang thread mới hoặc `@Async`, imperative transaction context cũng không tự được chuyển qua.

## 8. Spring quyết định rollback/commit tại boundary ra sao?

Đoạn sau mô tả **logic khái niệm** của một `AbstractPlatformTransactionManager`; không phải source Spring đầy đủ:

```text
complete(status):

  nếu status có localRollbackOnly:
      xử lý rollback theo scope này
      (nếu là new transaction => rollback physical transaction)
      (nếu là participating REQUIRED => đánh dấu global rollback-only)
      (nếu là NESTED/savepoint => có thể rollback về savepoint)

  ngược lại nếu underlying transaction đã globalRollbackOnly:
      không thể xác nhận commit vật lý theo cách bình thường
      rollback / báo tình huống unexpected theo manager semantics

  ngược lại:
      thực hiện đường commit/hoàn tất thích hợp

  cleanup status, resource, synchronization
```

Cách diễn đạt “local=true => rollback” không có nghĩa tất cả trường hợp đều ném exception. Với **outer scope tự gọi `setRollbackOnly()`**, việc rollback là quyết định đã được scope đó yêu cầu. Với **outer local=false nhưng global=true**, việc rollback khi outer yêu cầu commit là bất ngờ và thường tạo `UnexpectedRollbackException`.

**Ngoại lệ về triển khai:** `JtaTransactionManager` và một số manager có semantics phối hợp riêng, gồm tình huống coordinator xử lý commit request khi global rollback-only. Không biến pseudocode thành thuật toán áp dụng chính xác cho mọi manager.

### Vì sao gọi `manager.commit(status)` vẫn có thể rollback?

Tên API `commit(TransactionStatus)` mô tả lời yêu cầu **hoàn tất transaction theo đường commit nếu được phép**. Manager kiểm tra rollback-only và có thể chuyển thành rollback. Kể cả không có rollback-only, commit vẫn có thể thất bại vì lỗi database. Vì vậy đừng ghi log “committed” ngay trước khi lời gọi commit thực sự hoàn thành thành công.

### Phân biệt `isCompleted()` với rollback-only

`status.isCompleted()` chỉ báo scope đã hoàn tất. Một scope hoàn tất bằng rollback và một scope hoàn tất bằng commit đều có thể có completed=true. Ngược lại, một outer scope vẫn chưa completed nhưng global rollback-only đã true; code trong outer vẫn có thể tiếp tục chạy cho đến khi gọi commit/rollback ở boundary.

## 9. Hai cờ cấu hình manager rất dễ hiểu sai

Trong những manager kế thừa `AbstractPlatformTransactionManager` có hai option liên quan trực tiếp. Mỗi option không phải attribute của `@Transactional`; đây là **cấu hình transaction manager**.

### 9.1. `globalRollbackOnParticipationFailure`

Mặc định của `AbstractPlatformTransactionManager` là **`true`**.

- Khi một scope **tham gia** transaction ngoài (`REQUIRED`) thất bại và Spring gọi `rollback(participatingStatus)` theo rollback rule, manager thường đánh dấu physical transaction **global rollback-only**.
- Nếu đặt `false`, manager có thể cho scope khởi tạo transaction ngoài tự quyết định rollback/commit sau khi bắt exception của inner.
- Tuy nhiên, resource đã gặp lỗi có thể không còn thực sự có khả năng commit; Hibernate/JPA session hoặc database connection có thể đã bị provider/driver coi là lỗi.
- **Quan trọng nhất:** option này chỉ nói đến *participating rollback do manager xử lý sau thất bại*. Việc một scope **trực tiếp gọi `TransactionStatus.setRollbackOnly()`** vẫn phải dẫn đến kết quả rollback toàn cục thích hợp khi scope ấy hoàn tất; không dùng flag để “hủy” yêu cầu explicit đó.

Ví dụ cấu hình (fragment trong `@Configuration`):

```java
@Bean
JdbcTransactionManager transactionManager(DataSource ds) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(ds);
    manager.setGlobalRollbackOnParticipationFailure(true);
    return manager;
}
```

Mặc định đã true; đoạn này chủ yếu làm rõ cách đặt option, không cần thêm khi không có yêu cầu đặc biệt.

**Không khuyên tắt flag chỉ để làm `UnexpectedRollbackException` biến mất.** Khi dữ liệu cần atomicity, xử lý lỗi ở đúng ranh giới giao dịch và để transaction rollback là cách an toàn hơn.

### 9.2. `failEarlyOnGlobalRollbackOnly`

Mặc định là **`false`**.

- Nếu một transaction đã bị global rollback-only, Spring thường chỉ báo `UnexpectedRollbackException` ở **ranh giới transaction ngoài cùng** khi caller vẫn cố commit.
- Khi bật `true`, manager có thể **báo sớm hơn** ở một ranh giới nội bộ khi phát hiện global rollback-only.
- Flag thay đổi **thời điểm thông báo**, không làm transaction đã rollback-only trở thành committable.

```java
@Bean
JdbcTransactionManager transactionManager(DataSource ds) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(ds);
    manager.setFailEarlyOnGlobalRollbackOnly(true);
    return manager;
}
```

Đây là **cấu hình minh họa**, không nên bật chỉ để “fix rollback”. Vị trí exception sớm/muộn tùy flow và manager, cần integration test nếu code bắt lỗi theo tầng.

### 9.3. Bảng so sánh

| Cấu hình | Mặc định | Tác động chủ yếu | Không làm được |
| --- | --- | --- | --- |
| `globalRollbackOnParticipationFailure` | `true` | Participating rollback sau lỗi có đánh dấu shared transaction rollback-only hay không | Không xóa explicit `setRollbackOnly()` hoặc sửa tài nguyên DB đã hỏng. |
| `failEarlyOnGlobalRollbackOnly` | `false` | Quyết định thông báo unexpected rollback ở ranh giới ngoài cùng hay có thể sớm hơn | Không cho phép commit transaction global rollback-only. |
| `validateExistingTransaction` | `false` thường gặp | Kiểm tra isolation/read-only mismatch khi tham gia transaction | Không có chức năng gỡ rollback-only. |

## 10. So sánh propagation: khi nào rollback-only của inner ảnh hưởng outer?

| Propagation tại inner | Quan hệ với outer | Nếu inner rollback hoặc set rollback-only | Khả năng outer tiếp tục commit |
| --- | --- | --- | --- |
| `REQUIRED` | Thường **cùng physical transaction** | Participating scope có thể làm shared transaction global rollback-only | Thường **không thể** commit nếu đã global rollback-only. |
| `REQUIRES_NEW` | Physical transaction **độc lập**, outer bị tạm treo | Inner transaction riêng rollback | Outer **có thể** commit nếu ngoại lệ inner được xử lý phù hợp và outer không bị đánh dấu rollback-only. |
| `NESTED` với savepoint | **Một physical transaction**, inner có savepoint | Có thể rollback các thao tác sau savepoint mà không poison toàn transaction | Outer có thể tiếp tục, nếu resource/manager hỗ trợ và transaction không bị global rollback-only vì nguyên nhân khác. |
| `SUPPORTS` | Tham gia nếu có; nếu không có có thể không có actual transaction | Tùy transaction hiện hành và trạng thái manager | Không suy ra có physical transaction chỉ từ annotation. |
| `NOT_SUPPORTED` | Tạm treo transaction ngoài | Các thao tác không tự thuộc outer transaction | Không có một inner transaction local để rollback theo cách như `REQUIRED`. |

**`REQUIRES_NEW` không phải nested savepoint.** Nó cần transaction/connection riêng, và inner commit có thể tồn tại ngay cả khi outer rollback. `NESTED` thường dựa trên JDBC savepoints: rollback phần inner có thể giữ outer, nhưng không đảm bảo mọi JPA provider hoặc transaction manager hỗ trợ.

### `NESTED` và câu “explicit setRollbackOnly luôn đánh dấu global”

Cần diễn đạt chính xác: với **participating `REQUIRED`**, explicit `setRollbackOnly()` ở inner sẽ dẫn đến shared transaction không thể commit khi inner scope hoàn tất. Với **`NESTED` thực sự được thực thi bằng savepoint**, manager có thể rollback inner đến savepoint thay vì đánh dấu cả physical transaction global rollback-only. Đừng đánh đồng hai propagation modes.

### Khi không có actual transaction

Với `SUPPORTS` không gặp transaction đang hoạt động, một transaction interceptor có thể vẫn tạo scope/synchronization tùy cấu hình, nhưng không có physical transaction cho database để rollback. Đừng gọi `status.setRollbackOnly()` trong một flow không có actual transaction rồi tuyên bố các thao tác autocommit SQL trước đó đã được hoàn tác.

## 11. Ví dụ Java 17+ chạy độc lập: đo local, global và effective flag

Ví dụ dùng Spring Framework **6.2.8**, Spring JDBC, H2 in-memory, Maven và JDK 17+. Có ba kịch bản được chạy lần lượt, trên cùng datasource nhưng **mỗi lượt gọi bắt đầu một transaction mới**:

1. **Outer tự set local flag:** local=true, global có thể vẫn false trong method; khi method trả về, transaction rollback **mà không cần unexpected rollback exception**.
2. **Inner `REQUIRED` tự set local flag:** inner.local=true; khi inner kết thúc, outer.local=false nhưng outer.global=true; outer cố commit thì nhận `UnexpectedRollbackException`.
3. **Inner `REQUIRED` ném runtime exception, outer bắt lại:** inner interceptor xử lý participating rollback, làm shared transaction global rollback-only; outer vẫn nhận `UnexpectedRollbackException` khi cố commit.

Cả ba tình huống đều ghi vào bảng H2 rồi rollback; sau mỗi lượt, số hàng còn lại là 0.

### 11.1. Cấu trúc dự án

```text
rollback-only-flags-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RollbackOnlyFlagsDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>rollback-only-flags-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RollbackOnlyFlagsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 11.2. Mã `src/main/java/dev/learning/RollbackOnlyFlagsDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.AbstractTransactionStatus;

public final class RollbackOnlyFlagsDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:rollback_flags;DB_CLOSE_DELAY=-1");
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
        InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        OuterService outerService(JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }
    }

    // Chỉ dùng ở demo JDBC với DefaultTransactionStatus;
    // code ứng dụng chung nên ưu tiên status.isRollbackOnly().
    private static void show(String label) {
        TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();

        if (!(status instanceof AbstractTransactionStatus details)) {
            throw new IllegalStateException(
                    "Expected AbstractTransactionStatus");
        }

        System.out.println(
                label
                + " local=" + details.isLocalRollbackOnly()
                + " global=" + details.isGlobalRollbackOnly()
                + " effective=" + details.isRollbackOnly()
                + " new=" + status.isNewTransaction());
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void markRollbackOnly() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    3, "inner marked");

            show("case2.inner.before");
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            show("case2.inner.after");
        }

        @Transactional
        public void failWithException() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    5, "inner threw");

            throw new IllegalStateException("inner failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional
        public void markOwnRollbackOnly() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    1, "outer local");

            show("case1.before");
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            show("case1.after");
        }

        @Transactional
        public void outerCallsInnerMark() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    2, "outer calling inner");

            show("case2.outer.before");
            inner.markRollbackOnly();
            show("case2.outer.after");
        }

        @Transactional
        public void outerCatchesInnerException() {
            jdbc.update(
                    "INSERT INTO events (id, label) VALUES (?, ?)",
                    4, "outer catches");

            try {
                inner.failWithException();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "case3.innerCaught=" + expected.getMessage());
            }

            show("case3.outer.afterCatch");
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM events", Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE events (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            // Lấy Spring bean proxy, không tự new OuterService.
            OuterService outer = context.getBean(OuterService.class);

            // Case 1: root scope tự mark => rollback chủ động.
            outer.markOwnRollbackOnly();
            System.out.println("case1.rows=" + count(jdbc));

            // Case 2: participating inner mark => global rollback-only.
            try {
                outer.outerCallsInnerMark();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "case2.exception="
                        + ex.getClass().getSimpleName());
            }
            System.out.println("case2.rows=" + count(jdbc));

            // Case 3: inner unchecked exception, outer bắt lại.
            try {
                outer.outerCatchesInnerException();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "case3.exception="
                        + ex.getClass().getSimpleName());
            }
            System.out.println("case3.rows=" + count(jdbc));
        }
    }
}
```

### 11.3. Biên dịch và chạy

Cần JDK 17+ và Maven. Trong thư mục `rollback-only-flags-demo`:

```bash
mvn -q clean compile exec:java
```

Lần chạy đầu cần Internet để tải thư viện. Các dòng **chính chương trình in ra**, không tính thông báo Maven hoặc log từ môi trường:

```text
case1.before local=false global=false effective=false new=true
case1.after local=true global=false effective=true new=true
case1.rows=0
case2.outer.before local=false global=false effective=false new=true
case2.inner.before local=false global=false effective=false new=false
case2.inner.after local=true global=false effective=true new=false
case2.outer.after local=false global=true effective=true new=true
case2.exception=UnexpectedRollbackException
case2.rows=0
case3.innerCaught=inner failed
case3.outer.afterCatch local=false global=true effective=true new=true
case3.exception=UnexpectedRollbackException
case3.rows=0
```

**Vì sao kết quả như trên?**

- **Case 1:** Outer tạo transaction mới (`new=true`), tự đặt cờ local. Trước khi method kết thúc, global flag từ resource vẫn có thể false. Khi method trả về, transaction manager thấy local flag và rollback; caller không nhận unexpected rollback chỉ từ quyết định tự rollback này.
- **Case 2:** Inner method `REQUIRED` thấy transaction ngoài đang hoạt động, vì vậy `new=false`. Khi inner trực tiếp `setRollbackOnly()`, cờ local của **inner status** chuyển true. Sau khi inner scope kết thúc, transaction manager đánh dấu shared JDBC transaction rollback-only; outer status **không tự chuyển local=true** nhưng global=true. Outer commit bất khả thi và caller nhận `UnexpectedRollbackException`.
- **Case 3:** Inner ném unchecked exception. Interceptor của inner gọi participating rollback theo rollback rule mặc định; manager đặt global flag trên shared transaction. Outer catch exception không khôi phục khả năng commit. Khi outer method kết thúc, outer interceptor phát hiện global rollback-only và báo `UnexpectedRollbackException`.
- Cả ba lượt đã ghi dữ liệu trước khi rollback, nhưng `SELECT COUNT(*)` từ sau khi transaction kết thúc đều trả 0. Các ID cố tình khác nhau để dễ phân biệt dòng nếu thử sửa code.

**Lưu ý kiểm chứng:** Đây là kết quả kỳ vọng với các phiên bản dependency và cấu hình JDBC nêu trên, được suy ra từ semantics Spring. Việc log nội bộ của Spring/driver có thể thêm dòng tùy cấu hình. Cần chạy trong môi trường có JDK/Maven để kiểm tra thực nghiệm.

### 11.4. Những thay đổi nhỏ để tự thí nghiệm

**Thử A — Bỏ `setRollbackOnly()` trong case 1.** Khi method kết thúc bình thường và không có lỗi khác, hàng ID=1 được commit; `case1.rows` thành 1. Điều này xác nhận rollback ở case 1 là do chính local flag.

**Thử B — Bỏ `setRollbackOnly()` của inner trong case 2.** Hai inserts của case 2 hoàn tất bình thường và commit cùng transaction của outer. Cả hai cùng tồn tại vì `REQUIRED` dùng chung physical transaction.

**Thử C — Đổi inner sang `REQUIRES_NEW`.** Inner sẽ có physical transaction riêng; nếu inner tự đánh dấu rollback-only, chỉ transaction đó rollback. Outer có thể commit nếu mọi điều kiện khác cho phép. Cần bảo đảm connection pool có connection bổ sung khi chạy đồng thời; với H2 datasource tối giản, đây chỉ là mô hình học tập.

**Thử D — Bật `failEarlyOnGlobalRollbackOnly=true`.** Thêm một participating boundary sau thời điểm global flag đã được đánh dấu và quan sát vị trí exception có thể đến sớm hơn. Chỉ đổi flag không bảo đảm exception chắc chắn chuyển đến một vị trí cụ thể nếu flow không có boundary phụ để phát hiện.

**Thử E — Đổi `globalRollbackOnParticipationFailure=false` rồi chạy case 3.** Khi resource còn khỏe và không có nguyên nhân rollback-only khác, participating exception rollback có thể không poison toàn transaction. Tuy vậy case 2 dùng explicit `setRollbackOnly()` sẽ không được “cứu” bởi flag này. **Không áp dụng thử nghiệm làm cấu hình production chỉ nhằm nuốt lỗi giao dịch.**

## 12. Những lỗi nhầm lẫn thường gặp

### 12.1. “Outer không gọi `setRollbackOnly()` nên vẫn có thể commit”

Sai. `outer.local=false` không đồng nghĩa `outer.global=false`. Nếu inner đã làm shared transaction rollback-only hoặc tài nguyên đã tự đánh dấu rollback-only, outer không thể commit vật lý bằng cách giữ local flag false.

### 12.2. “Catch exception ở outer sẽ xóa global rollback-only”

Sai. Catch chỉ điều khiển luồng Java. Nó không tự gọi một API khôi phục transaction. Một physical transaction đã rollback-only không có cơ chế “undo setRollbackOnly” chung trong Spring.

### 12.3. “`isActualTransactionActive()==true` có nghĩa transaction vẫn tốt”

Sai. Một transaction có thể **vẫn active** về mặt scope và resource binding, nhưng đã global rollback-only. Kiểm tra active không phải là kiểm tra committable.

### 12.4. “`TransactionStatus.isRollbackOnly()` chỉ trả cờ do chính method đặt”

Sai với `AbstractTransactionStatus`: effective flag kết hợp local và global. Nếu cần biết **nguồn** của flag trong một manager hỗ trợ, kiểm tra hai cờ chi tiết ở implementation phù hợp.

### 12.5. “Global rollback-only nghĩa là có distributed transaction trên nhiều DB”

Sai trong ngữ cảnh này. Ngay cả một JDBC connection local có nhiều logical scopes `REQUIRED` vẫn có global rollback-only của physical transaction dùng chung.

### 12.6. “Inner đã return bình thường nên outer không bao giờ gặp exception”

Sai. Inner có thể return bình thường sau `setRollbackOnly()`; outer vẫn bị báo `UnexpectedRollbackException` ở lúc interceptor hoàn tất transaction. Lỗi này có thể xuất hiện **sau** dòng `return` trong business method của outer.

### 12.7. “`globalRollbackOnParticipationFailure=false` sẽ cho phép commit mọi giao dịch”

Sai. Flag chỉ thay đổi cơ chế đánh dấu global trong một loại participating rollback; explicit local setRollbackOnly, database timeout, transaction coordinator và resource failure vẫn có thể ngăn commit.

### 12.8. “`NESTED` giống `REQUIRES_NEW`”

Sai. `NESTED` thường dùng savepoint trên **cùng physical transaction**; `REQUIRES_NEW` mở transaction vật lý độc lập. Kết quả rollback/commit và chi phí connection khác nhau.

### 12.9. “Gọi trực tiếp `this.inner()` cũng tạo inner logical scope”

Trong Spring proxy mode mặc định, **self-invocation** bỏ qua proxy cho inner method, nên advice/transaction attributes của inner không được áp dụng ở lời gọi đó. Nếu outer có transaction, code trong inner vẫn có thể chạy trên transaction outer; nhưng không tự sinh inner `TransactionStatus` riêng.

### 12.10. “Một exception bất kỳ luôn đánh dấu global rollback-only”

Không đúng. Rollback rules quyết định exception nào yêu cầu rollback; default rollback cho `RuntimeException` và `Error`, checked exceptions thường không tự rollback. Một exception bị bắt **bên trong** method trước khi ra proxy có thể không kích hoạt rule. Mặt khác database/provider có thể tự đánh dấu transaction không thể commit sau lỗi tài nguyên. Phải phân biệt các nguyên nhân này.

## 13. Kiểm thử một cách đáng tin cậy

Một unit test chỉ quan sát `setRollbackOnly()` được gọi chưa chứng minh dữ liệu rollback thật. Nên có integration tests trên transaction manager và datasource:

| Test | Cần quan sát |
| --- | --- |
| Outer root tự set local | Method có thể return bình thường, nhưng các writes bị rollback. |
| Inner `REQUIRED` explicit setRollbackOnly | Inner local chuyển true; sau khi inner kết thúc outer thấy global true và commit outer bị từ chối. |
| Inner `REQUIRED` ném unchecked, outer catch | Shared transaction không được commit; có thể nhận `UnexpectedRollbackException` ở outer boundary. |
| Inner `REQUIRES_NEW` rollback | Outer có thể commit độc lập nếu không bị đánh dấu rollback-only và xử lý lỗi hợp lý. |
| Inner `NESTED` rollback-to-savepoint | Nếu manager và driver hỗ trợ, rollback phần inner mà giữ phần outer. |
| Inner checked exception không có `rollbackFor` | Xác nhận rule thực tế và trạng thái resource; không giả định luôn global rollback-only. |
| Self-invocation `this.inner()` | Annotation của inner không tạo scope được intercept như cross-bean call. |
| Database constraint / timeout | Quan sát exception/physical rollback thực tế; không chỉ tin cờ status ngay trước commit. |

### Lưu ý với Spring TestContext

Một test method có `@Transactional` có thể được Spring TestContext rollback vào cuối test. Điều này có thể **che mất** sự khác biệt giữa “service tự rollback” và “test framework rollback sau test”. Với những test khẳng định commit/rollback của service, hãy chủ động thiết kế transaction boundary và thời điểm truy vấn dữ liệu phù hợp, hoặc dùng `TestTransaction` để kiểm soát test-managed transaction.

### Log hỗ trợ chẩn đoán

Trong ứng dụng Spring Boot, có thể bật các mức log trong `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Tùy Spring version, implementation và logging backend, nội dung log khác nhau. Không viết integration test phụ thuộc vào một câu log cố định. Khi debug, kết hợp log với trạng thái local/global và phép đọc dữ liệu độc lập sau transaction.

## 14. Checklist rà soát lỗi rollback-only

1. **Xác định outermost boundary**: method nào thực sự mở physical transaction? Caller có đi qua Spring proxy không?
2. **Xác định inner scopes**: các method `REQUIRED` có đang tham gia cùng transaction manager và datasource không?
3. **Kiểm tra rollback rules**: runtime/checked exception nào thực sự thoát khỏi interceptor? Có `rollbackFor` / `noRollbackFor` không?
4. **Tìm explicit `setRollbackOnly()`**: được gọi ở outer hay inner status? Có bị đặt sau một nhánh lỗi đã được bắt không?
5. **Phân biệt hai cờ**: nơi chẩn đoán phù hợp, log `isLocalRollbackOnly`, `isGlobalRollbackOnly` và `isRollbackOnly`.
6. **Kiểm tra resource failure**: database đã tự chuyển trạng thái không thể commit, độc lập với Spring status flags, hay chưa?
7. **Xem cấu hình manager**: `globalRollbackOnParticipationFailure` và `failEarlyOnGlobalRollbackOnly` đang dùng giá trị nào?
8. **Tính đến propagation**: có `REQUIRES_NEW`/`NESTED` thật sự hay chỉ một shared transaction `REQUIRED`?
9. **Không che exception**: bắt lỗi để phản hồi nghiệp vụ rõ ràng, nhưng không giả vờ transaction đã commit.
10. **Kiểm thử sau boundary**: đọc dữ liệu sau khi transaction kết thúc và xác nhận commit/rollback thực tế.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao outer.local=false nhưng outer.isRollbackOnly()=true?

*Đáp án:* Vì underlying transaction đã global rollback-only; trong `AbstractTransactionStatus`, effective rollback-only là local OR global.

**Câu 2.** Gọi `setRollbackOnly()` trong inner `REQUIRED` có giống gọi trong outer scope không?

*Đáp án:* Cả hai có thể khiến physical transaction rollback, nhưng **status nào có local flag true** và **cách caller nhận `UnexpectedRollbackException`** khác nhau. Inner đánh dấu local trên scope riêng; khi scope tham gia hoàn tất, manager có thể lan trạng thái đó sang global. Outer đang cố commit không chủ động chọn rollback nên thường thấy unexpected rollback.

**Câu 3.** Nếu outer catch unchecked exception từ inner thì có thể tiếp tục commit không?

*Đáp án:* Thường không với `AbstractPlatformTransactionManager` mặc định và inner `REQUIRED` đã trigger participating rollback: global flag của shared transaction thường true. Catch exception không làm cờ biến mất. Trường hợp khác cần kiểm tra manager flags và tài nguyên.

**Câu 4.** `globalRollbackOnParticipationFailure=false` có vô hiệu hóa explicit `setRollbackOnly()` của inner không?

*Đáp án:* Không. Flag này điều khiển participating rollback sau failure; explicit `setRollbackOnly()` vẫn dẫn tới kết quả rollback phù hợp khi scope hoàn tất.

**Câu 5.** Nếu inner cần rollback riêng nhưng outer vẫn muốn commit, nên xem giải pháp nào?

*Đáp án:* Xem `REQUIRES_NEW` để dùng physical transaction độc lập hoặc `NESTED`/savepoint nếu manager và resource hỗ trợ. Hai lựa chọn có semantics khác nhau; phải xem nghiệp vụ và chi phí connection/locking.

**Câu 6.** Có thể chắc chắn commit được khi local=false, global=false không?

*Đáp án:* Không. Đây chỉ là trạng thái rollback-only quan sát được; commit vẫn có thể thất bại vì database constraint, concurrent updates, timeout, network hoặc driver.

**Câu 7.** Vì sao `UnexpectedRollbackException` thường xuất hiện sau khi thân outer method return?

*Đáp án:* `TransactionInterceptor` hoàn tất transaction **sau** lời gọi business method. Nếu outer return bình thường nhưng physical transaction global rollback-only, manager có thể rollback rồi ném exception ở boundary ngoài proxy.

## 16. Kết luận

- **Local rollback-only** phản ánh yêu cầu rollback của *một logical transaction scope* qua `TransactionStatus`.
- **Global rollback-only** phản ánh shared underlying transaction đã bị đánh dấu không thể commit. Không nhầm với distributed/XA transaction.
- **Effective `isRollbackOnly()`** trong `AbstractTransactionStatus` cho biết local hoặc global đã true.
- **`REQUIRED` tham gia transaction** giải thích vì sao inner local rollback-only có thể làm outer global rollback-only dù outer không gọi `setRollbackOnly()`.
- **`UnexpectedRollbackException`** bảo vệ caller khỏi kết luận nhầm rằng outer đã commit khi inner âm thầm làm shared transaction rollback-only.
- **`REQUIRES_NEW` và `NESTED`** thay đổi ranh giới rollback nhưng khác semantics; các manager flags chỉ đổi cách xử lý/thời điểm báo lỗi, không sửa transaction hỏng.
- **Kiểm chứng đúng** cần phân biệt trạng thái status, luồng interceptor/manager, và dữ liệu thực sự còn lại sau commit/rollback.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical scopes, physical transaction, rollback-only ở `REQUIRED`, `REQUIRES_NEW` và `NESTED`.
2. [Spring Framework 6.2 — `AbstractTransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractTransactionStatus.html): `setRollbackOnly`, `isLocalRollbackOnly`, `isGlobalRollbackOnly` và `isRollbackOnly`.
3. [Spring Framework 6.2 — `DefaultTransactionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionStatus.html): cách đọc global rollback-only từ transaction object.
4. [Spring Framework 6.2 — `SmartTransactionObject` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/SmartTransactionObject.html): resource/coordinator cung cấp internal rollback-only marker.
5. [Spring Framework 6.2 — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `globalRollbackOnParticipationFailure`, `failEarlyOnGlobalRollbackOnly` và handling của participating transactions.
6. [Spring Framework 6.2 — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html): `currentTransactionStatus()` và status của locally declared boundary.
7. [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules và đặt rollback-only bằng code.
8. [Spring Framework — Understanding the Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): `TransactionStatus` và `PlatformTransactionManager`.
