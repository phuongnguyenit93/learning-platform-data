# Commit, rollback và thuộc tính riêng của giao dịch mới với REQUIRES_NEW

> **Module:** Spring Framework — Transaction Management. **Mục:** REQUIRES_NEW. Bài học tập trung vào việc transaction mới **commit/rollback độc lập** với transaction bên ngoài và sở hữu **isolation, timeout, read-only, rollback rules** riêng. Các ví dụ giả định Spring transaction management theo **proxy mode**, một JDBC DataSource và transaction manager tương ứng; phần thực hành có một dự án Spring Boot 3.5.7 / Java 17 / H2 / Maven đầy đủ để tự kiểm chứng.

## 1. Ý nghĩa của REQUIRES_NEW

`@Transactional(propagation = Propagation.REQUIRES_NEW)` yêu cầu Spring **bắt đầu một physical transaction mới** cho lời gọi mà transaction interceptor thực sự xử lý.

Khi một transaction ngoài `T1` đã hoạt động trên cùng thread/transaction manager:

1. Spring **tạm ngưng (suspend)** ngữ cảnh giao dịch `T1`.
2. Spring bắt đầu một physical transaction riêng `T2`, thường sử dụng **connection khác** nếu là giao dịch JDBC trên cùng DataSource.
3. Method inner làm việc trong `T2`. `T2` tự quyết định commit hoặc rollback theo kết quả và rollback rules của nó.
4. Khi `T2` hoàn tất, Spring dọn ngữ cảnh của `T2` và **khôi phục (resume) `T1`**.
5. Outer tiếp tục trong `T1`; cuối cùng `T1` commit hoặc rollback theo kết quả riêng.

```text
Caller
  |
  v
OuterService.outer()          @Transactional(REQUIRED)
  |                             bắt đầu physical transaction T1
  |------ INSERT outer -------->
  |
  | gọi qua Spring proxy
  v
InnerService.inner()          @Transactional(REQUIRES_NEW)
  |                             suspend T1
  |                             bắt đầu physical transaction T2
  |------ INSERT inner -------->
  |                             commit hoặc rollback T2
  v                             resume T1
OuterService tiếp tục
  |------ INSERT outer2 ------->
  v
commit hoặc rollback T1

T2 hoàn tất trước khi T1 kết thúc; T2 không phải savepoint của T1.
```

**Kết luận then chốt:** `REQUIRES_NEW` không tham gia physical transaction hiện có. Sau khi `T2` commit thành công, một rollback của `T1` **không tự hoàn tác** dữ liệu của `T2`. Ngược lại, `T2` rollback không tự đặt `T1` thành rollback-only, **nhưng exception từ `T2` nếu lan ra outer vẫn có thể khiến `T1` rollback**.

Khi **chưa có transaction nào**, `REQUIRES_NEW` bắt đầu một transaction mới như yêu cầu; lúc đó chỉ có một physical transaction, không có outer để suspend.

## 2. Physical transaction, logical scope và ranh giới commit

Để hiểu độc lập phải phân biệt hai khái niệm:

- **Physical transaction:** giao dịch thật của database/resource. Với JDBC, một connection trong một transaction; với JPA, một transaction theo entity manager/transaction manager. Đây là thứ thật sự commit hoặc rollback.
- **Logical transaction scope:** phần transaction metadata/interception tương ứng một lời gọi method transactional. Scope có thể dùng chung physical transaction với scope khác hoặc bắt đầu physical transaction riêng tùy propagation.

Với `Propagation.REQUIRED` (mặc định), một inner logical scope thường **tham gia** physical transaction `T1` của outer. Với `Propagation.REQUIRES_NEW`, inner logical scope dùng **`T2` riêng biệt**.

| Câu hỏi | Inner `REQUIRED` khi outer T1 đã mở | Inner `REQUIRES_NEW` khi outer T1 đã mở |
| --- | --- | --- |
| Physical transaction của inner | Dùng lại `T1` | Tạo `T2` riêng |
| Commit độc lập trước outer? | Không | Có |
| Inner rollback-only có tác động trực tiếp lên T1? | Có thể đánh dấu T1 rollback-only | Không trực tiếp, vì T2 riêng |
| Outer rollback sau inner thành công | Hoàn tác dữ liệu inner cùng T1 | Không hoàn tác dữ liệu T2 đã commit |
| Isolation/timeout/readOnly riêng của inner | Thường không áp dụng lại cho T1 | Có thể thiết lập cho T2 khi được hỗ trợ |
| JDBC connection | Thường cùng connection của T1 | T1 giữ connection; T2 thường cần connection khác |
| Tác động tài nguyên | Ít overhead hơn | Có thêm transaction/connection/lock, nguy cơ cạn pool |

“Không tác động trực tiếp” **không phải** “không thể ảnh hưởng”. Một exception ném từ `T2` và **không được outer xử lý** sẽ đi ra khỏi outer method; interceptor của outer có thể rollback `T1` theo rule của **outer**. Đây là cơ chế exception propagation, **không phải** T1 bị rollback vì T2 chia sẻ physical transaction.

## 3. Ma trận commit và rollback: bốn kết quả nền tảng

Giả sử outer ghi bản ghi `O` trong T1, inner ghi bản ghi `I` trong T2. Các bản ghi dùng **khóa/hàng khác nhau** để tránh lock không cần thiết; cả hai method được gọi đúng qua Spring proxy. Bảng mô tả kết quả đã kết thúc cả T1 và T2.

| Kết quả T2 | Kết quả T1 | Bản ghi `I` của inner | Bản ghi `O` của outer |
| --- | --- | --- | --- |
| **Commit** | **Commit** | Còn | Còn |
| **Commit** | **Rollback** | **Còn** | Không còn |
| **Rollback** | **Commit** | Không còn | **Còn** |
| **Rollback** | **Rollback** | Không còn | Không còn |

Đây là tính **độc lập về quyết định commit/rollback** của hai physical transactions. Không có “điều kiện phải cùng commit” do Spring tự thêm. Nếu nghiệp vụ bắt buộc cả hai hoặc không bên nào thành công, `REQUIRES_NEW` **thường không phải** propagation đúng; `REQUIRED` trên cùng resource có thể phù hợp hơn.

### 3.1. Inner commit, outer rollback

```java
@Transactional
public void processOrder() {
    orderRepository.insert(...);   // T1, ví dụ minh họa.
    auditService.writeAudit();      // T2, REQUIRES_NEW, đã commit.
    throw new IllegalStateException("Order failed");
}
```

Đoạn này là **trích đoạn nghiệp vụ**, không phải class runnable. Khi inner là bean khác và gọi qua proxy, audit `T2` có thể **vẫn còn** sau khi outer `T1` rollback. Chỉ dùng nếu bản ghi audit độc lập ấy hợp lệ ngay cả khi order chưa được commit.

### 3.2. Inner rollback, outer commit

```java
@Transactional
public void processOrder() {
    orderRepository.insert(...);   // T1.
    try {
        auditService.writeAndFail(); // T2 rollback.
    } catch (IllegalStateException ex) {
        // Chấp nhận audit thất bại; tiếp tục nghiệp vụ outer.
    }
    orderRepository.markReady(...); // T1 vẫn có thể commit.
}
```

**Điều kiện:** exception từ T2 phải được outer xử lý hợp lệ, không có lỗi tài nguyên nào khác làm T1 rollback-only, và database state vẫn nhất quán. Nếu outer **không bắt** exception unchecked thì outer interceptor cũng có thể rollback T1 theo mặc định.

### 3.3. Inner và outer đều commit

T2 commit trước, sau đó T1 commit. Đây là một kết quả có thể xảy ra, nhưng **không tạo atomic transaction chung**: giữa hai thời điểm commit, transaction khác có thể đã thấy dữ liệu T2 trong khi dữ liệu chưa commit của T1 chưa hiển thị.

### 3.4. Inner và outer đều rollback

T2 gặp lỗi và rollback. Nếu exception vẫn thoát khỏi outer và khớp rollback rule mặc định của `@Transactional`, T1 cũng rollback. Chúng vẫn là **hai quyết định rollback riêng**. Không nên mô tả tình huống này là bằng chứng inner đã tham gia T1.

## 4. Ví dụ gọi hai bean: điều kiện để REQUIRES_NEW thật sự hoạt động

```java
@Service
public class PaymentService {
    private final ReceiptService receipts;

    public PaymentService(ReceiptService receipts) {
        this.receipts = receipts;
    }

    @Transactional
    public void pay() {
        // Giao dịch T1.
        receipts.recordReceipt(); // Gọi proxy của bean khác.
        // Tiếp tục giao dịch T1.
    }
}

@Service
public class ReceiptService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordReceipt() {
        // Giao dịch T2.
    }
}
```

Đây là **trích đoạn minh họa**, mỗi public class thuộc file riêng. Cần import `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional` và `org.springframework.transaction.annotation.Propagation`. Cấu hình phải có transaction infrastructure/transaction manager đúng và Spring thực sự inject proxy của `ReceiptService`.

**Không đủ** nếu chỉ thêm annotation vào method trong cùng class:

```java
@Service
class IncorrectSelfInvocation {
    @Transactional
    public void outer() {
        inner(); // this.inner(): bypass Spring proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Annotation inner không được áp dụng riêng qua self-call.
    }
}
```

Ở **Spring AOP proxy mode**, lời gọi `this.inner()` chạy trực tiếp trên target, không quay lại interceptor. Nếu `outer()` đã mở T1, code trong `inner()` có thể dùng connection/transaction T1; **không có T2**. Nếu `outer()` rollback, phần ghi ở inner cũng có thể rollback theo.

Với JDK interface proxy, method cần là public method trên interface được proxy; với class-based proxy, method phải có thể intercept/override; `private` và `final` method là vấn đề. Bean tạo bằng `new` không đi qua Spring proxy. `AspectJ` weaving có cơ chế khác, nhưng không nên dựa vào nó khi đang dùng proxy mode mặc định.

## 5. Isolation, timeout và readOnly là thuộc tính riêng của T2

Một trong các lợi ích của `REQUIRES_NEW` là inner transaction **không kế thừa máy móc các đặc tính** của physical transaction T1. Khi bắt đầu T2, Spring có thể yêu cầu manager/tài nguyên áp dụng isolation, timeout và read-only riêng.

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE,
    timeout = 5,
    readOnly = true
)
public void queryImportantSnapshot() {
    // Đọc dữ liệu trong T2 với transaction attributes riêng.
}
```

Đây là **trích đoạn**, import `Propagation`, `Isolation` và `Transactional` từ `org.springframework.transaction.annotation`.

- **`propagation = REQUIRES_NEW`:** tạm ngưng T1 (nếu có), bắt đầu một transaction T2.
- **`isolation = SERIALIZABLE`:** yêu cầu mức isolation cho T2, nếu transaction manager/driver/database hỗ trợ. Điều đó không làm isolation của T1 thay đổi.
- **`timeout = 5`:** cấu hình giới hạn transaction **5 giây** cho T2 mới. Không phải timer tự ngắt mọi Java method, HTTP call hay `Thread.sleep` đúng ở giây thứ 5. Mức enforcement phụ thuộc manager/driver/database/statement.
- **`readOnly = true`:** metadata/hint cho T2, có thể giúp tối ưu và driver/database áp dụng hành vi read-only. **Không phải cơ chế phân quyền database và không bảo đảm tất cả DB chặn `INSERT`/`UPDATE`.**
- Khi T2 kết thúc, Spring khôi phục ngữ cảnh T1. Isolation và readOnly của T1 không bị “nhiễm” bởi cấu hình riêng của T2 nếu manager hỗ trợ suspend/resume đúng.

### 5.1. Một ngoại lệ: join REQUIRED không tạo lại đặc tính

```java
@Service
class InnerReportService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE,
        timeout = 5,
        readOnly = true
    )
    public void readReport() {
    }
}
```

Nếu method này **tham gia** T1 đã có, Spring mặc định dùng đặc tính của **physical transaction ngoài**, không tự đổi T1 thành serializable, không reset timeout, không chuyển toàn bộ T1 thành read-only. Có thể yêu cầu manager kiểm tra mismatch bằng `setValidateExistingTransaction(true)`, nhưng validation là **từ chối cấu hình không tương thích**, không phải tạo T2.

### 5.2. Mặc định riêng khi không khai báo thuộc tính

Inner `@Transactional(propagation = REQUIRES_NEW)` mà không khai báo thêm:

- `isolation` mặc định là `Isolation.DEFAULT` → mức isolation mặc định của underlying transaction resource.
- `timeout` mặc định lấy từ transaction manager/system, có thể không giới hạn nếu hạ tầng không hỗ trợ.
- `readOnly` mặc định `false`.
- Rollback mặc định khi `RuntimeException` hoặc `Error` thoát qua interceptor; checked exception thường **không** kích hoạt rollback theo mặc định.
- `REQUIRES_NEW` **không sao chép** isolation/readOnly/timeout của T1; T2 được cấu hình theo annotation, manager default và underlying resource.

Do đó, không nên hiểu “T2 có thuộc tính riêng” là **T2 tự động kế thừa toàn bộ T1 rồi chỉnh vài thuộc tính**. Nó là transaction mới với định nghĩa riêng; ví dụ outer đang `SERIALIZABLE` mà inner `DEFAULT` có thể dùng isolation mặc định của database.

### 5.3. `timeoutString` và placeholder

Khi muốn cấu hình số giây qua property, dùng:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeoutString = "${app.tx.inner-timeout-seconds:5}"
)
public void runInnerJob() {
    // Timeout từ property; default 5 giây.
}
```

`timeoutString` nhận **chuỗi số giây** có thể resolve placeholder, không phải `Duration` với đơn vị `ms` hoặc `PT5S`. Không khai báo `timeout` và `timeoutString` cùng lúc trong một annotation. Property có thể nằm trong `application.properties`:

```properties
app.tx.inner-timeout-seconds=8
```

Đây là lựa chọn cấu hình **thay thế** cho `timeout=5` trong ví dụ phần trên, không cần thêm vào project thực hành ở phần 8.

### 5.4. Read-only và quyền ghi

Nhiều hệ thống dùng `REQUIRES_NEW, readOnly=true` để đọc trong transaction snapshot độc lập. Nhưng:

- `readOnly=true` là hint/transaction metadata; DB/driver có thể diễn giải khác nhau.
- Một `SELECT` của T2 **không mặc nhiên thấy** các `INSERT/UPDATE` chưa commit của T1; T2 là physical transaction riêng.
- Nếu outer cần đọc lại dữ liệu inner T2 vừa commit, visibility còn phụ thuộc isolation, snapshot và database. Ở `READ_COMMITTED` có thể thấy ở lần query sau, nhưng với `REPEATABLE_READ` hoặc snapshot đã cố định, không được mặc định là thấy.
- Nếu inner T2 muốn ghi vào những hàng đang bị T1 khóa, T2 có thể chờ chính lock của outer dẫn đến deadlock/timeout. Chọn read-only không tự giải quyết tất cả lock.

## 6. Rollback rules và exception propagation giữa T2 và T1

Spring có hai câu hỏi **độc lập**:

1. T2 có commit hay rollback theo exception/rollback-only của **inner method**?
2. Outer thấy điều gì khi inner trả về hoặc ném exception, và T1 có commit hay rollback theo chính sách **outer method**?

### 6.1. Exception unchecked từ T2 nhưng outer đã catch

```java
@Transactional
public void outer() {
    insertOuter();
    try {
        innerService.writeAndFail(); // REQUIRES_NEW, T2 rollback.
    } catch (IllegalStateException expected) {
        // Đã xử lý lỗi; outer vẫn có thể commit T1.
    }
}
```

Đây là **trích đoạn**; `insertOuter`/`innerService` do ứng dụng cung cấp. Khác `REQUIRED` tham gia T1, `REQUIRES_NEW` rollback T2 **không đánh dấu T1 rollback-only chỉ vì T2 rollback**.

### 6.2. Exception unchecked không được outer catch

```java
@Transactional
public void outer() {
    insertOuter();
    innerService.writeAndFail(); // REQUIRES_NEW rollback T2, ném exception.
    // Không chạy tiếp.
}
```

Exception tiếp tục thoát ra khỏi outer, nên interceptor của outer cũng rollback T1 theo rule mặc định. Kết quả **hai transaction rollback**, dù chúng độc lập về resource.

### 6.3. Cấu hình `rollbackFor` cho checked exception

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = java.io.IOException.class
)
public void importInner() throws java.io.IOException {
    // Nếu IOException thoát qua interceptor, T2 rollback.
}
```

Checked exception không mặc định gây rollback trong các cấu hình Spring thông dụng; `rollbackFor` làm rõ ý định. Cần cân nhắc **cả annotation của outer** nếu exception đó có thể thoát khỏi outer. Ví dụ T2 rollback vì `rollbackFor = IOException.class` nhưng outer không khai báo tương ứng, outer interceptor có thể commit T1 nếu checked `IOException` thoát ra và các rollback rules của outer vẫn mặc định. Không có quy tắc “inner đã rollback nên outer bắt buộc rollback”.

### 6.4. `noRollbackFor` không có nghĩa là exception không xảy ra

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    noRollbackFor = IllegalArgumentException.class
)
public void saveThenThrow() {
    // Viết DB, sau đó ném IllegalArgumentException.
}
```

Đây là trích đoạn. Nếu exception phù hợp `noRollbackFor` thoát qua inner interceptor, inner có thể **commit T2 mặc dù caller nhận exception** (trừ khi resource/transaction đã rollback-only do nguyên nhân khác). Nhưng nếu outer không catch exception unchecked này, outer vẫn có thể rollback T1 theo **rule riêng** của outer. Vì vậy exception được ném ra không đồng nghĩa “mọi transaction đều rollback”, cũng không đồng nghĩa “không có transaction nào commit”.

### 6.5. Đánh dấu rollback-only không cần ném exception

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void cancelInnerOnly() {
    // Sau khi xử lý nếu không muốn commit T2:
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

Đây là trích đoạn, import `org.springframework.transaction.interceptor.TransactionAspectSupport`. Nếu method inner được intercept và đặt rollback-only của **T2**, T2 sẽ rollback ở kết thúc scope. Outer T1 có thể tiếp tục và commit nếu không có lỗi khác. Cần làm rõ trong API/business contract rằng inner không commit; không trả về thành công mơ hồ.

### 6.6. Vì sao `UnexpectedRollbackException` không giống trong REQUIRED?

Khi inner `REQUIRED` tham gia T1 rồi đánh dấu physical transaction rollback-only, outer có thể nhận `UnexpectedRollbackException` khi tưởng mình sẽ commit. Còn inner `REQUIRES_NEW` rollback T2 riêng và outer **đã catch exception** thì T1 không tự bị mark rollback-only chỉ vì T2 thất bại. Vì thế, không nên tự suy ra outer sẽ nhận `UnexpectedRollbackException` trong trường hợp này.

Tuy vậy `UnexpectedRollbackException` vẫn **có thể** xuất hiện từ manager nếu T1 bị đánh dấu rollback-only vì **nguyên nhân khác**, hoặc có lỗi ở commit. Không coi annotation là cơ chế đảm bảo “không bao giờ có exception”.

## 7. Vì sao T2 commit vẫn có thể gây rủi ro tính nhất quán?

`REQUIRES_NEW` phù hợp khi một ghi nhận cần sống sót độc lập; nhưng nó phá tính atomic của nhiều bước nếu dùng sai.

Ví dụ sai mục tiêu:

```java
@Transactional
public void transferMoney() {
    debitSourceAccount();             // T1
    paymentRecordService.credit();   // T2, REQUIRES_NEW
    updateLedger();                  // T1, sau đó ném lỗi
}
```

Đây là **trích đoạn nghiệp vụ minh họa**. Nếu `credit()` đã commit T2 nhưng T1 rollback, hệ thống có thể có bản ghi cộng tiền trong khi phần ghi nợ/ledger thuộc T1 biến mất. Hệ thống **không còn atomic toàn nghiệp vụ**.

Nếu cần “tất cả ghi thành công hoặc tất cả rollback” trên một database, hãy ưu tiên **cùng T1** qua `REQUIRED`, không dùng `REQUIRES_NEW` chỉ để “chắc chắn method được commit”.

Các use case có thể phù hợp, với thiết kế cẩn trọng:

- Ghi **technical audit** độc lập cho cả một thao tác thất bại, nếu audit không phụ thuộc vào dữ liệu chưa commit của outer.
- Ghi bản ghi theo dõi thử xử lý/attempt độc lập để phục vụ vận hành, và chấp nhận outer rollback vẫn để lại lịch sử attempt.
- Một giao dịch nhỏ độc lập, với khóa/tài nguyên và hợp đồng nghiệp vụ rõ ràng.

Các use case **không tự động phù hợp**:

- Ghi nửa còn lại của cùng một giao dịch chuyển tiền.
- Ghi outbox event ở T2 trong khi thay đổi nghiệp vụ tương ứng nằm ở T1: outbox có thể commit, được phát đi, trong khi thay đổi nghiệp vụ T1 rollback.
- Cố che giấu lỗi của transaction lớn bằng cách ép mọi method inner sang `REQUIRES_NEW`.
- Ghi vào hàng đang bị T1 giữ lock rồi chờ T2 hoàn thành.

## 8. Dự án thực hành đầy đủ: commit/rollback độc lập và thuộc tính của T2

**Mục tiêu:** chạy được bằng Java 17, Maven, Spring Boot 3.5.7, JDBC và H2. Bảng `tx_log` dùng ID riêng cho từng trường hợp; mỗi case được gọi khi runner **không có transaction bao bên ngoài**. Điều đó giúp quan sát chính xác ranh giới do service method tạo.

Ta kiểm chứng:

1. **T2 commit, T1 rollback** → chỉ có row inner.
2. **T2 rollback, T1 commit** khi outer catch exception → chỉ có các row outer.
3. **T2 rollback, exception lan ra outer** → cả hai rollback.
4. **Inner dùng REQUIRED thay vì REQUIRES_NEW** → cả hai row cùng T1 và rollback với outer.
5. **Self-invocation** tới method annotated `REQUIRES_NEW` trong cùng bean → inner annotation không tạo T2 qua proxy mode.
6. **Thuộc tính mới của T2:** outer có read-only false/isolation READ_COMMITTED; inner có read-only true/isolation SERIALIZABLE; sau inner, các flag của outer được khôi phục. Timeout của T2 được khai báo, nhưng **không ép demo chạy query chậm để suy đoán timeout chính xác**.

### 8.1. Cấu trúc thư mục

```text
requires-new-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/requiresnew/
        │       ├── RequiresNewApplication.java
        │       ├── OuterService.java
        │       └── InnerService.java
        └── resources/
            └── application.properties
```

### 8.2. `pom.xml`

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
    <artifactId>requires-new-demo</artifactId>
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

Starter JDBC mang `JdbcTemplate`, transaction management và HikariCP trong cách cấu hình phổ biến; `h2` là JDBC driver/database in-memory.

### 8.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:requires_new_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Demo tuần tự T1 + T2: pool có dư connection.
spring.datasource.hikari.maximum-pool-size=5
```

Đặt đủ connection là quan trọng: khi outer T1 đang giữ connection và inner T2 cần connection khác, pool chỉ có một connection có thể khiến T2 phải chờ cho đến khi connection-acquisition timeout, hoặc gây deadlock ở mức pool khi nhiều thread cùng chờ.

### 8.4. `src/main/java/vn/example/requiresnew/InnerService.java`

```java
package vn.example.requiresnew;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {

    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void commitNew(int id) {
        insert(id, "inner-committed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void rollbackNew(int id) {
        insert(id, "inner-rolled-back");
        throw new IllegalStateException("Inner T2 failed");
    }

    @Transactional
    public void joinRequired(int id) {
        insert(id, "inner-required");
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE,
        timeout = 5,
        readOnly = true
    )
    public String ownAttributes() {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();
        boolean readOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        Integer isolation =
            TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

        boolean serializable = Objects.equals(
            isolation, Connection.TRANSACTION_SERIALIZABLE
        );

        // Không ghi dữ liệu trong read-only transaction.
        jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_log", Integer.class
        );

        return "inner-active=" + active
            + ",inner-readOnly=" + readOnly
            + ",inner-serializable=" + serializable;
    }

    private void insert(int id, String tag) {
        jdbc.update(
            "INSERT INTO tx_log(id, tag) VALUES (?, ?)",
            id, tag
        );
    }
}
```

Ý nghĩa:

- `commitNew` và `rollbackNew` có thể tự commit/rollback T2 vì chúng được caller gọi qua proxy của **bean riêng**.
- `joinRequired` là đối chứng: không mở T2 khi outer T1 đã tồn tại.
- `ownAttributes` tạo T2 **mới** với `readOnly=true`, `isolation=SERIALIZABLE`, `timeout=5`. Nó kiểm tra transaction active và các flag của Spring, dùng một `SELECT` vô hại; không có DML trong read-only transaction.
- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` là thông tin Spring quản lý, **không phải phép chứng minh database cấm ghi**.
- `Objects.equals(isolation, Connection.TRANSACTION_SERIALIZABLE)` so sánh mã isolation của Spring/JDBC tương ứng. Trong demo này manager có khả năng thiết lập isolation đã yêu cầu; đừng suy ra mọi database hỗ trợ tất cả levels giống nhau.

### 8.5. `src/main/java/vn/example/requiresnew/OuterService.java`

```java
package vn.example.requiresnew;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OuterService {

    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void outerRollbackInnerCommit() {
        insert(101, "outer-rollback");
        inner.commitNew(102); // T2 commit hoàn tất.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional
    public void outerCommitInnerRollback() {
        insert(201, "outer-before");
        try {
            inner.rollbackNew(202); // T2 rollback rồi ném lỗi.
        } catch (IllegalStateException expected) {
            // Lỗi T2 đã được outer xử lý.
        }
        insert(203, "outer-after");
        // T1 kết thúc bình thường, có thể commit.
    }

    @Transactional
    public void outerRollbackWhenInnerExceptionEscapes() {
        insert(301, "outer-uncaught");
        inner.rollbackNew(302); // T2 rollback; exception tiếp tục ra outer.
    }

    @Transactional
    public void outerRollbackWithRequired() {
        insert(401, "outer-required");
        inner.joinRequired(402); // Tham gia chính T1.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional
    public void outerRollbackWithSelfInvocation() {
        insert(501, "outer-self");
        selfRequiresNew(502); // this.method(): không qua proxy.
        throw new IllegalStateException("Outer T1 failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void selfRequiresNew(int id) {
        insert(id, "inner-self");
    }

    @Transactional(isolation = Isolation.READ_COMMITTED, timeout = 20)
    public String inspectAttributes() {
        boolean outerBeforeReadOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();

        String inside = inner.ownAttributes(); // T2 độc lập.

        boolean outerAfterReadOnly =
            TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        boolean outerReadCommitted = Objects.equals(
            TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel(),
            Connection.TRANSACTION_READ_COMMITTED
        );

        return "outer-before-readOnly=" + outerBeforeReadOnly
            + "\n" + inside
            + "\nouter-after-readOnly=" + outerAfterReadOnly
            + "\nouter-read-committed=" + outerReadCommitted;
    }

    private void insert(int id, String tag) {
        jdbc.update(
            "INSERT INTO tx_log(id, tag) VALUES (?, ?)",
            id, tag
        );
    }
}
```

Các đặc điểm chính:

- Mỗi case có ID riêng: 101/102, 201/202/203, 301/302, 401/402, 501/502, không bị trùng khóa giữa các lần chạy.
- Các outer method là public và được runner gọi qua **Spring bean proxy**.
- `OuterService` inject `InnerService` qua constructor, nên các lời gọi inner qua bean khác có thể chạy transaction advice.
- `selfRequiresNew` nằm trên **cùng target** với caller; lời gọi `selfRequiresNew(502)` không tạo giao dịch T2 mặc dù method có annotation.
- `inspectAttributes` cố ý chưa ghi DML, giúp inner có thể dùng SERIALIZABLE/read-only riêng mà không gặp tranh chấp khóa từ T1. Nó chỉ kiểm tra flag isolation/readOnly và không chạy truy vấn chậm để kiểm tra timeout.

### 8.6. `src/main/java/vn/example/requiresnew/RequiresNewApplication.java`

```java
package vn.example.requiresnew;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class RequiresNewApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequiresNewApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE tx_log (" +
                "id INT PRIMARY KEY, tag VARCHAR(40) NOT NULL)"
            );

            expectOuterFailure(outer::outerRollbackInnerCommit);
            System.out.printf("innerCommit_outerRollback=%d,%d%n",
                count(jdbc, 101), count(jdbc, 102));

            outer.outerCommitInnerRollback();
            System.out.printf("innerRollback_outerCommit=%d,%d,%d%n",
                count(jdbc, 201), count(jdbc, 202), count(jdbc, 203));

            expectOuterFailure(
                outer::outerRollbackWhenInnerExceptionEscapes
            );
            System.out.printf("uncaughtException=%d,%d%n",
                count(jdbc, 301), count(jdbc, 302));

            expectOuterFailure(outer::outerRollbackWithRequired);
            System.out.printf("requiredSameTx=%d,%d%n",
                count(jdbc, 401), count(jdbc, 402));

            expectOuterFailure(outer::outerRollbackWithSelfInvocation);
            System.out.printf("selfInvocation=%d,%d%n",
                count(jdbc, 501), count(jdbc, 502));

            System.out.println(outer.inspectAttributes());
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_log WHERE id = ?",
            Integer.class, id
        );
    }

    private static void expectOuterFailure(Runnable call) {
        try {
            call.run();
        } catch (IllegalStateException expected) {
            return;
        }
        throw new AssertionError("Expected simulated failure");
    }
}
```

Chọn `JdbcTransactionManager` tường minh cho cùng `DataSource` mà `JdbcTemplate` dùng. `@EnableTransactionManagement(proxyTargetClass = true)` giúp kết quả không phụ thuộc lựa chọn loại proxy ngầm của môi trường. Runner là caller bên ngoài đã được Spring tạo sau context initialization, không tự mở transaction cho toàn runner; bởi vậy mỗi lời gọi outer tự bắt đầu T1. Việc tạo bảng chạy trước các ca thử nghiệm.

### 8.7. Chạy và xác nhận stdout

Từ thư mục `requires-new-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/requires-new-demo-1.0.0.jar
```

Những dòng **do chính code demo in ra**, theo thứ tự, với cấu hình trên là:

```text
innerCommit_outerRollback=0,1
innerRollback_outerCommit=1,0,1
uncaughtException=0,0
requiredSameTx=0,0
selfInvocation=0,0
outer-before-readOnly=false
inner-active=true,inner-readOnly=true,inner-serializable=true
outer-after-readOnly=false
outer-read-committed=true
```

Có thể có log khởi động Spring Boot ở các dòng khác. Kết quả **không gồm** các log đó. Phép thử dựa trên transactional JDBC/H2 và `@Transactional` được Spring proxy intercept. Nếu đổi database, transaction manager, isolation support hoặc test lifecycle, cần đối chiếu lại trước khi kỳ vọng output giống hoàn toàn.

### 8.8. Giải thích kết quả và thời điểm commit

| Case | Row tồn tại | Vì sao |
| --- | --- | --- |
| `innerCommit_outerRollback=0,1` | 101 không; 102 có | T2 ghi 102 đã commit, sau đó T1 ném lỗi và rollback 101. |
| `innerRollback_outerCommit=1,0,1` | 201,203 có; 202 không | T2 rollback 202; outer bắt lỗi, T1 vẫn commit hai insert của nó. |
| `uncaughtException=0,0` | 301,302 đều không | T2 rollback vì lỗi; lỗi lan ra outer nên T1 cũng rollback theo rule của outer. |
| `requiredSameTx=0,0` | 401,402 đều không | Inner `REQUIRED` tham gia T1, không có T2; outer rollback cả hai. |
| `selfInvocation=0,0` | 501,502 đều không | Lời gọi nội bộ bypass proxy của inner method, phần ghi 502 vẫn ở T1. |
| `outer-before-readOnly=false` | Flag outer false | T1 được tạo với readOnly mặc định false. |
| `inner-readOnly=true,inner-serializable=true` | Flag T2 riêng | Inner được intercept với `REQUIRES_NEW` và các attrs tường minh. |
| `outer-after-readOnly=false` | Flag T1 được khôi phục | Sau T2, thread/transaction context quay về T1. |
| `outer-read-committed=true` | Isolation outer đúng | T1 dùng `READ_COMMITTED`, không bị thay bằng `SERIALIZABLE` của T2. |

**Đặc biệt:** `inner-active=true` chỉ xác nhận T2 có transaction đang hoạt động ở thread lúc chạy method. Dấu hiệu quan trọng nhất của **commit độc lập** là trạng thái row **102 còn sau khi outer 101 rollback**, không chỉ một flag active.

### 8.9. Vì sao demo không dùng `Thread.sleep` để thử timeout?

`@Transactional(timeout = 5)` là transaction deadline áp dụng qua transaction manager/tài nguyên, **không phải một Java thread interrupt timer**. `Thread.sleep(7000)` trong method không chứng minh DB thực sự đã hủy giao dịch tại giây thứ 5. Với JDBC, Spring có thể áp dụng remaining transaction timeout cho các `Statement` qua `JdbcTemplate`; database/driver quyết định cách timeout/interrupt query. Để kiểm chứng timeout thật, hãy dùng integration test có truy vấn chậm/chờ lock có kiểm soát trên database/driver mục tiêu, và xác minh rollback + exception + giải phóng tài nguyên.

### 8.10. Nếu đổi cấu hình khi chạy thật

Trong code app thực, transaction boundary phải được kiểm tra theo Spring version, manager và cấu hình. Ví dụ thay `JdbcTransactionManager` bằng `JpaTransactionManager` sẽ đưa resource/flush/isolation semantics của JPA vào bài toán; không mặc định H2/JDBC demo chứng minh mọi behavior trên mọi stack. Ngoài ra, nếu test method đã được Spring TestContext mở transaction trước khi gọi outer, có thể có **transaction bổ sung** từ chính test; hãy tách transaction của test và transaction của service khi đánh giá.

## 9. Tài nguyên bị suspend và nguy cơ connection pool

`REQUIRES_NEW` không “dùng lại T1 nhưng chốt commit sớm”. Với JDBC trên cùng DataSource, thông thường:

- Outer T1 đã lấy connection `C1` và giữ nó trong thời gian T1 còn sống.
- Khi inner cần T2, Spring tạm ngưng tài nguyên của T1, nhưng **C1 vẫn thuộc T1**, chưa được trả về pool như một connection rảnh.
- Inner T2 lấy một connection `C2` riêng, dùng để ghi/đọc và commit/rollback.
- Sau khi T2 hoàn tất, `C2` được trả lại pool, Spring resume T1 với `C1`.

```text
Thread A:
  T1: C1 [đang được giữ -------------------------]
          |
          | suspend T1
          v
  T2:     C2 [begin -> work -> commit/rollback]
          |
          v
  resume T1 với C1 -> T1 commit/rollback
```

Nếu mỗi thread đồng thời giữ C1 rồi cùng đợi C2 nhưng pool hết connection, hệ thống có thể **kẹt vì pool**. Tài liệu Spring khuyến nghị tránh dùng `REQUIRES_NEW` nếu pool không đủ kích thước; một định hướng tối thiểu cho tình huống điển hình là pool **lớn hơn số thread đồng thời ít nhất một connection**. Thực tế phải tính nested depth, connections khác đang sử dụng, HikariCP `maximumPoolSize`/`connectionTimeout`, giao dịch dài và tải peak.

### Lock deadlock với T1

Giả sử T1 đã `UPDATE accounts SET ... WHERE id = 1` nhưng chưa commit; C1 đang giữ lock. Trong cùng call stack, T2 trên C2 muốn update **cùng hàng id=1** rồi phải chờ lock T1. Nhưng T1 lại đang **đợi method T2 trả về** để tiếp tục. Đó là tình huống dễ tạo deadlock/lock timeout dù code chỉ chạy tuần tự trên một thread.

**Khuyến nghị:** với `REQUIRES_NEW`, ưu tiên tài nguyên/bản ghi độc lập không bị T1 khóa. Đừng đặt inner cập nhật cùng một hàng “đang chưa commit của outer” rồi mong T2 luôn chạy nhanh.

### Visibility của dữ liệu chưa commit

T2 là giao dịch riêng; thông thường ở `READ_COMMITTED`, nó **không thấy** các row/uncommitted writes của T1. Vì vậy audit T2 không nên tham chiếu FK tới một row mà T1 **vừa insert nhưng chưa commit**, trừ khi bạn đã kiểm tra database constraints và thiết kế xử lý phù hợp; T2 có thể thất bại, chờ lock hoặc không tìm thấy row đó.

Ngược lại, sau T2 commit, T1 muốn đọc row T2 mới ghi thì còn phụ thuộc isolation/snapshot của T1. Tránh hứa “outer luôn đọc được inner commit ngay” trên mọi database và isolation level.

## 10. Chọn REQUIRES_NEW hay REQUIRED/NESTED?

| Tiêu chí | `REQUIRED` | `REQUIRES_NEW` | `NESTED` |
| --- | --- | --- | --- |
| Khi outer T1 có sẵn | Tham gia T1 | Suspend T1, tạo T2 | Thường tạo savepoint trên T1 |
| Số physical transactions | Một | Hai (T1, T2) | Một |
| Inner có thể commit trước outer? | Không | **Có** | Không — savepoint không phải commit độc lập |
| Outer rollback sau inner “thành công” | Inner data rollback theo T1 | Inner T2 data vẫn còn nếu T2 đã commit | Inner data rollback cùng T1 |
| Inner rollback nhưng outer tiếp tục | Có thể đánh dấu T1 rollback-only | Có thể, nếu outer xử lý lỗi hợp lệ | Có thể rollback về savepoint nếu hỗ trợ |
| Isolation/timeout/readOnly riêng | Không có transaction mới để áp dụng riêng | Có thể áp dụng riêng cho T2 | Chủ yếu dùng tính chất T1 |
| Connection/lock | Thường dùng một connection | Thường cần thêm connection | Thường cùng connection, dùng savepoint |
| Dùng cho | Một nghiệp vụ atomic trong cùng DB | Phần việc **cần commit/rollback độc lập** | Partial rollback cùng physical transaction |

Chú ý: `NESTED` phụ thuộc JDBC savepoint support và transaction manager; không coi mọi JPA/reactive/data store hỗ trợ giống nhau. Nếu không cần commit độc lập, `NESTED` có thể hợp lý hơn `REQUIRES_NEW` cho một bước có thể rollback một phần, nhưng phải kiểm chứng trên stack của mình.

## 11. Lỗi phổ biến khi dùng REQUIRES_NEW

### 11.1. Tưởng cùng bean self-call là T2

```java
@Transactional
public void outer() {
    inner(); // Không đi qua proxy trong Spring AOP proxy mode.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
}
```

Đây là **trích đoạn**. Giải pháp thường rõ nhất là đưa `inner()` sang bean khác và inject nó, hoặc dùng `TransactionTemplate` chủ động khi phù hợp. Không tự khuyên lấy proxy vòng qua `AopContext.currentProxy()` làm giải pháp mặc định vì tăng coupling/hạn chế cấu hình.

### 11.2. Inner rollback nhưng exception vẫn lan ra outer

Nếu T2 rollback và exception unchecked thoát đến outer, T1 vẫn có thể rollback vì **outer interceptor cũng nhìn thấy exception**. Độc lập transaction không đồng nghĩa độc lập luồng điều khiển/exception. Muốn outer tiếp tục, cần bắt và xử lý lỗi có chủ đích trong outer, rồi kiểm tra trạng thái/đảm bảo nghiệp vụ hợp lệ.

### 11.3. Tưởng thuộc tính T2 đổi thuộc tính T1

Inner `REQUIRES_NEW(readOnly=true)` không biến T1 thành read-only. Inner `SERIALIZABLE` không nâng isolation của T1; timeout của T2 không reset hay thu ngắn timeout của T1. T2 kết thúc, Spring khôi phục ngữ cảnh T1.

### 11.4. Tưởng `readOnly` chặn mọi `INSERT`

`@Transactional(readOnly = true)` không thay thế tài khoản database chỉ đọc, rule bảo mật SQL hoặc ACL. Dùng database privileges và validation nghiệp vụ thật sự; không dựa vào hint để thực thi security.

### 11.5. Để pool chỉ có một connection

T1 giữ connection, T2 cần connection khác. Pool kích thước 1 thường dẫn đến chờ connection và hết timeout. Nếu ứng dụng có nhiều requests đồng thời, sizing cần xét concurrency và nested depth, không chỉ test demo tuần tự.

### 11.6. Ghi cùng hàng đang bị T1 khóa

T2 không thể mượn lock của T1 vì chúng là hai physical transactions. Việc T1 chờ T2 trong khi T2 chờ lock T1 có thể làm giao dịch treo đến deadlock/timeout.

### 11.7. “Outbox độc lập” sai ranh giới

Nếu business update nằm ở T1 nhưng outbox row nằm ở T2, outbox có thể commit và message được phát **dù T1 rollback**. Với transactional outbox cho cùng nghiệp vụ, bản ghi outbox cần commit/rollback **cùng transaction** với business state. `REQUIRES_NEW` cho outbox không phải bản sửa lỗi tự động.

### 11.8. Test có `@Transactional` bao ngoài

Spring TestContext có thể mở test-managed transaction trước khi gọi service. Lúc ấy `REQUIRES_NEW` trên service tạo T2 và commit riêng, nhưng test-managed T1 có thể rollback cuối test. Đọc state trong cùng test context/connection dễ gây nhầm. Thiết kế test không có outer test transaction hoặc kiểm soát transaction test rõ để khẳng định independent commit.

### 11.9. Hai datasource không cùng manager

Một method dùng `ordersTransactionManager`, inner dùng `auditTransactionManager` có thể cũng có commit/rollback độc lập, nhưng đó **không nhất thiết** là tình huống suspend/resume T1 trên cùng manager. Muốn mô tả đúng, cần xác định manager, datasource và transaction context của mỗi resource. Hai local managers không tự tạo XA/2PC.

### 11.10. Async và HTTP không tự tham gia T1/T2

`@Async`/thread khác thường không tự mang ThreadLocal transaction context từ caller trong imperative model. Gọi microservice qua HTTP cũng không chia sẻ JDBC physical transaction. `REQUIRES_NEW` chỉ có ý nghĩa trong transaction management của tài nguyên/manager liên quan, không làm phân phối transaction ra mạng.

## 12. Kiểm thử commit, rollback và thuộc tính T2 đúng cách

Một integration test đáng tin nên kiểm tra **database state sau khi cả outer và inner kết thúc**, không chỉ xem có exception.

### Test A — commit T2 sống sót sau rollback T1

1. Bắt đầu từ trạng thái sạch.
2. Gọi outer method qua proxy, outer ghi O và inner `REQUIRES_NEW` ghi I.
3. Outer ném unchecked exception làm T1 rollback.
4. Đọc DB qua connection/transaction mới: O **không có**, I **có**.
5. Nếu chỉ kiểm tra `isActualTransactionActive()` ở inner, chưa đủ chứng minh T2 thật sự độc lập.

### Test B — rollback T2 không làm outer bị rollback-only

1. Outer bắt đầu T1, ghi O1.
2. Inner bắt đầu T2, ghi I rồi ném `RuntimeException`.
3. Inner interceptor rollback T2; outer **catch** exception hợp lệ và ghi O2.
4. Outer kết thúc bình thường; đọc DB: O1/O2 **có**, I **không có**.
5. Nếu ngoài ý muốn có `UnexpectedRollbackException`, điều tra xem T1 đã rollback-only vì nguyên nhân khác hay inner thật sự không đi qua proxy.

### Test C — exception lan ra làm outer cũng rollback

1. Outer ghi O, inner T2 ghi I rồi lỗi.
2. Outer **không bắt** exception.
3. T2 rollback, outer interceptor thấy exception và rollback T1.
4. O/I đều **không có**, nhưng đây là hai rollback độc lập.

### Test D — quyền thiết lập isolation/readOnly/timeout riêng

1. Outer T1 cấu hình `READ_COMMITTED`, `timeout=20`, `readOnly=false`.
2. Inner T2 `REQUIRES_NEW` cấu hình `SERIALIZABLE`, `timeout=5`, `readOnly=true`.
3. Kiểm tra transaction metadata/`TransactionSynchronizationManager` trong mỗi scope và sự khôi phục outer sau inner.
4. Nếu muốn xác minh timeout enforcement thật, dùng query có kiểm soát trên database thật/testcontainer và kiểm tra exception/rollback/resource release, thay vì sleep CPU thread.
5. Không test ghi dữ liệu trong inner read-only để “chứng minh luôn bị cấm”: hành vi này tùy DB/driver.

### Test E — proxy và connection pool

1. Đặt inner ở bean riêng, inject qua container; so sánh với self-invocation.
2. Giám sát active/pending connections của pool khi outer/inner lồng nhau.
3. Mô phỏng concurrency với giới hạn an toàn, tránh tạo tải phá hoại production.
4. Test nếu outer giữ lock và inner muốn truy cập cùng hàng, bảo đảm timeout/retry policy rõ ràng và không deadlock vô hạn.

### Phân biệt tính đúng của output và giới hạn demo

H2 rất tốt để học transaction boundaries; nhưng semantics isolation, lock, read-only và lỗi SQL có thể khác PostgreSQL/MySQL/Oracle. Bởi vậy, integration tests quan trọng cần chạy trên đúng database/driver/version của production. Trong test có `@Transactional` ở method test, nên dùng test không có test-managed transaction hoặc hiểu kỹ `TestTransaction` khi cần quan sát commit độc lập.

## 13. Những câu hỏi thường gặp

**Hỏi:** Inner `REQUIRES_NEW` commit rồi outer rollback; Spring có tự rollback T2 không?

**Đáp:** **Không**. T2 đã commit là physical transaction riêng. Outer rollback T1 không hoàn tác thay đổi T2.

**Hỏi:** Inner `REQUIRES_NEW` rollback; outer có bị rollback-only không?

**Đáp:** **Không trực tiếp do rollback T2**. Nhưng nếu exception unchecked từ inner thoát ra outer, interceptor outer có thể rollback T1 theo rollback rule của nó.

**Hỏi:** `REQUIRES_NEW` có nghĩa là tạo thêm thread mới không?

**Đáp:** **Không**. Thường vẫn trên cùng calling thread; transaction resource được suspend/resume và T2 dùng transaction/connection riêng. Không đồng nghĩa `@Async`.

**Hỏi:** Inner `REQUIRES_NEW` có bắt buộc phải đổi DataSource không?

**Đáp:** **Không**. Có thể cùng DataSource nhưng dùng **connection khác**; transaction manager phải quản lý resource đúng. Cùng JDBC URL không có nghĩa là cùng physical transaction.

**Hỏi:** Nếu outer không có transaction, `REQUIRES_NEW` có tác dụng không?

**Đáp:** Có. Nó yêu cầu bắt đầu một transaction mới, nhưng vì không có T1 nên không có bước suspend.

**Hỏi:** Mức isolation của outer có tự áp dụng vào inner không?

**Đáp:** **Không được kế thừa theo ý nghĩa join T1**. T2 dùng định nghĩa transaction riêng; nếu isolation=DEFAULT, nó dùng default của underlying resource. Nếu isolation=SERIALIZABLE và được hỗ trợ, T2 có mức isolation đó.

**Hỏi:** Inner `readOnly=true` có thể cập nhật dữ liệu không?

**Đáp:** Không thể kết luận chung. Đây là hint/flag mà từng manager/driver/database có thể áp dụng khác nhau; không dùng làm biện pháp phân quyền.

**Hỏi:** Có nên dùng `REQUIRES_NEW` cho mọi method audit không?

**Đáp:** Chỉ khi bản ghi audit được phép tồn tại độc lập, không yêu cầu dữ liệu chưa commit của T1 và không gây lock/pool issue. Audit tuân theo nghiệp vụ hoặc outbox thường nên ở cùng transaction với business state.

**Hỏi:** Inner đã có `REQUIRES_NEW` nhưng row vẫn rollback theo outer, vì sao?

**Đáp:** Kiểm tra self-invocation, proxy type/method visibility, bean tạo ngoài Spring, transaction manager, exception handling và việc test đọc kết quả. Annotation có mặt không chứng minh interceptor đã chạy.

## 14. Checklist khi thiết kế REQUIRES_NEW

- [ ] Đã phân biệt **physical T1/T2** và logical scopes.
- [ ] Inner thực sự cần **commit/rollback độc lập**; không yêu cầu atomicity chung của cùng nghiệp vụ.
- [ ] Phương thức inner được gọi qua **Spring proxy** có transaction advice; không phải `this.method()`.
- [ ] Transaction manager/DataSource được cấu hình rõ, các tài nguyên thực sự hỗ trợ suspend/new transaction.
- [ ] Phân biệt tình huống inner rollback và exception có/không lan ra outer.
- [ ] Thiết kế `rollbackFor`, `noRollbackFor` và `setRollbackOnly()` theo contract nghiệp vụ.
- [ ] Kiểm tra isolation, timeout, readOnly của **T2 mới**, không mặc định kế thừa T1.
- [ ] Không coi `readOnly` là security guarantee hoặc transaction timeout là thread timer.
- [ ] Có đủ connection pool khi T1 giữ C1 và T2 cần C2; có monitoring/timeout giới hạn chờ.
- [ ] Tránh inner cập nhật những hàng/resource đang bị outer T1 khóa.
- [ ] Không đặt outbox message ở T2 nếu business state liên quan nằm ở T1.
- [ ] Kiểm thử cả bốn tổ hợp commit/rollback trên database state sau kết thúc.
- [ ] Kiểm thử case exception lan ra outer và case outer đã catch exception.
- [ ] Không để transaction tự mở bởi test framework làm sai ranh giới đang kiểm thử.
- [ ] Khi đổi DB/driver/framework, chạy lại integration tests và đối chiếu transaction manager thực tế.

## 15. Bài tập và tự kiểm tra

**Bài 1:** Trong project, thay `inner.commitNew(102)` thành `inner.joinRequired(102)`. Nếu outer vẫn ném `IllegalStateException`, row 102 có tồn tại không?

**Đáp án:** Không. `joinRequired` tham gia T1; outer rollback T1 kéo theo toàn bộ thay đổi của inner `REQUIRED`. Cần để ý ID và mô tả chỉ là minh họa theo case thử nghiệm.

**Bài 2:** Trong `outerCommitInnerRollback()`, bỏ `try/catch` quanh `inner.rollbackNew(202)`, giữ exception lan ra. Các row 201/202/203 thế nào?

**Đáp án:** 201 rollback vì lỗi ra khỏi outer; 202 rollback ở T2; 203 không được insert vì code không chạy tới đó. Đây là lỗi exception propagation chứ không phải T1 bị chia sẻ physical transaction với T2.

**Bài 3:** Inner `REQUIRES_NEW` có `timeout=5` và `readOnly=true`, outer `REQUIRED` có `timeout=30` và `readOnly=false`. Khi T2 kết thúc, outer trở thành read-only không?

**Đáp án:** Không. T1 được resume cùng metadata/tài nguyên của nó; T2 có thuộc tính riêng.

**Bài 4:** Tại sao pool có `maximumPoolSize=1` nguy hiểm với T1 gọi T2?

**Đáp án:** T1 giữ connection đầu; T2 cần connection khác nhưng pool không còn connection, có thể chờ đến connection-acquisition timeout hoặc bị kẹt khi nhiều thread cùng tình trạng.

**Bài 5:** T2 commit row ghi nhận shipment, nhưng T1 rollback order. Kết quả có atomic toàn nghiệp vụ không?

**Đáp án:** Không. Đó chính là đặc điểm commit độc lập của `REQUIRES_NEW`; nếu shipment phụ thuộc order, cần thiết kế lại boundary.

## Tài liệu chính thức

- [Spring Framework Reference — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): mô tả chính thức `REQUIRED`, `REQUIRES_NEW` và `NESTED`, độc lập của physical transactions, rollback status, isolation/timeout/readOnly và connection pool.
- [Spring Framework Reference — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): các thuộc tính `propagation`, `isolation`, `timeout`, `readOnly`, `rollbackFor` và `noRollbackFor`.
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): interceptor, transaction manager và transaction boundary.
- [Spring Framework Reference — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation, JDK/class proxies và giới hạn intercept.
- [Spring Framework — `DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC local transaction và resource management.
- [Spring Framework — `JdbcTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): transaction manager dùng trong ví dụ.
- [Spring Framework Reference — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): các bẫy của test-managed transactions.

**Tóm tắt cốt lõi:** `REQUIRES_NEW` tạo **giao dịch vật lý T2 riêng** nếu lời gọi được Spring transaction advice xử lý. T2 có thể **commit dù T1 rollback** và **rollback dù T1 commit**; riêng exception lan từ inner ra outer vẫn có thể làm outer rollback. Isolation, timeout và readOnly của T2 là thuộc tính của **transaction mới**, không tự sửa đặc tính T1. Sự độc lập ấy mang lại sức mạnh, nhưng đòi hỏi chủ động thiết kế business atomicity, lock và connection pool.
