# Khai báo `propagation`, `isolation`, `readOnly` và `timeout` bằng `TransactionTemplate`

## Mục tiêu

`TransactionTemplate` là API quản lý transaction **theo lệnh (programmatic)** của Spring Framework, dành cho luồng imperative. Bài này tập trung vào cách **khai báo chính xác bốn thuộc tính giao dịch** và hiểu điều kiện chúng thực sự có hiệu lực.

Sau bài học, bạn có thể:

1. Tạo `TransactionTemplate` từ `PlatformTransactionManager` và cấu hình `setPropagationBehavior`, `setIsolationLevel`, `setReadOnly`, `setTimeout`.
2. Nhận biết mặc định `REQUIRED`, `DEFAULT`, `readOnly=false`, `TIMEOUT_DEFAULT=-1`.
3. Phân biệt giá trị khai báo trên template với trạng thái **transaction vật lý** khi callback chạy.
4. Dự đoán hành vi của `REQUIRED` khi tham gia transaction đã có, `REQUIRES_NEW` khi cần transaction độc lập, `NESTED` với savepoint và các propagation còn lại.
5. Biết `isolation`, `readOnly`, `timeout` có ý nghĩa chủ yếu **khi một transaction vật lý mới được bắt đầu**, và phụ thuộc transaction manager/driver/DBMS.
6. Áp dụng cùng `TransactionTemplate` cho nhiều callback một cách an toàn mà không thay đổi configuration trong lúc đang chạy.
7. Thử một project **Java 17+ / Spring Boot 3.3.5 / Spring JDBC / H2**, quan sát isolation và read-only trên connection thật, kiểm tra commit/rollback và viết JUnit 5 test.
8. Phân biệt cách xử lý exception và `status.setRollbackOnly()` trong callback, không nhầm với rollback rules của annotation `@Transactional`.

**Trọng tâm:** khai báo **cả bốn thuộc tính** với `TransactionTemplate`; các chủ đề propagation, JDBC isolation, timeout và AOP được giải thích vừa đủ để hiểu cách cấu hình và giới hạn thực tế.

---

## 1. Vì sao dùng `TransactionTemplate`?

Trong Spring có hai phong cách phổ biến:

**Declarative** — đặt `@Transactional` trên method để Spring AOP proxy tạo ranh giới giao dịch:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true,
    timeout = 15
)
public Report calculateReport() {
    // ...
}
```

**Programmatic** — chủ động bao **một đoạn code cụ thể** bằng `TransactionTemplate.execute(...)`:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
template.setReadOnly(true);
template.setTimeout(15);

Report report = template.execute(status -> calculateReport());
```

Hai đoạn trên **chỉ là minh họa API**, giả định các biến/kiểu `transactionManager`, `Report` và `calculateReport()` đã tồn tại. Chương trình chạy trọn vẹn nằm ở mục 8.

`TransactionTemplate` phù hợp khi cần:

- Đặt transaction quanh **một khối nhỏ** trong method dài, thay vì quanh toàn bộ method.
- Chọn propagation/isolation riêng cho từng thao tác được điều phối.
- Trả kết quả từ callback hoặc đánh dấu rollback-only theo điều kiện nghiệp vụ.
- Tránh phụ thuộc vào việc một method nội bộ có đi lại qua Spring AOP proxy hay không.
- Tổ chức nhiều unit of work có ranh giới rõ ràng ngay trong luồng Java imperative.

Nó **không** làm transaction trở nên độc lập với tài nguyên hoặc tự bảo vệ khỏi mọi vấn đề JDBC. `TransactionTemplate` chỉ điều phối `PlatformTransactionManager` được cung cấp, nên hiệu lực cuối phụ thuộc **manager, datasource, driver, DBMS và transaction hiện có**.

### Ba đối tượng khác vai trò

| Đối tượng | Vai trò |
| --- | --- |
| `PlatformTransactionManager` | Thực sự bắt đầu, commit, rollback, suspend/resume transaction thích hợp |
| `TransactionTemplate` | Giữ transaction definition và bao một callback bằng việc gọi manager |
| `TransactionStatus` | Đại diện scope giao dịch đang thực thi: `isNewTransaction()`, `isRollbackOnly()`, `setRollbackOnly()`... |

`TransactionTemplate` **không phải** một database connection. Nó cũng **không** tự tạo transaction vào thời điểm constructor chạy. Manager chỉ được yêu cầu tạo/tham gia transaction khi gọi `execute()` hoặc `executeWithoutResult()`.

## 2. Bốn thuộc tính và giá trị mặc định

```java
TransactionTemplate tx = new TransactionTemplate(transactionManager);

tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_DEFAULT);
tx.setReadOnly(false);
tx.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
```

Bốn dòng setter trên chỉ lặp lại các giá trị mặc định thông dụng; không bắt buộc phải ghi. `TransactionDefinition.TIMEOUT_DEFAULT = -1` biểu thị sử dụng timeout mặc định của hạ tầng (hoặc không có timeout khi không được hỗ trợ), **không phải luôn là -1 giây**.

| Thuộc tính | Setter | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| Propagation | `setPropagationBehavior(int)` | `PROPAGATION_REQUIRED` (`0`) | Bắt đầu transaction khi chưa có; tham gia transaction phù hợp đang tồn tại |
| Isolation | `setIsolationLevel(int)` | `ISOLATION_DEFAULT` (`-1`) | Không yêu cầu một isolation level cụ thể, dùng resource default |
| Read-only | `setReadOnly(boolean)` | `false` | Giao dịch đọc/ghi theo default; `true` là chỉ dẫn/tối ưu tùy hạ tầng |
| Timeout | `setTimeout(int)` | `TIMEOUT_DEFAULT` (`-1`) | Dùng timeout default của transaction manager/resource |
 
Thuộc tính mặc định **không phụ thuộc vào constructor nhận manager** hay cách inject template thành bean. Nếu muốn đặc tính khác, cần cấu hình trước khi template được chia sẻ.

### Cấu hình trọn bốn thuộc tính

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class TemplateFactory {

    public static TransactionTemplate newReportTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(true);
        tx.setTimeout(15); // đơn vị giây
        tx.setName("report.read");
        return tx;
    }
}
```

Đây là **class Java 17 biên dịch được khi có Spring Transaction trên classpath**, nhưng cần một manager thực và caller để thực thi callback. `setName` là thuộc tính tùy chọn bổ sung, hữu ích để chẩn đoán, không phải một trong bốn thuộc tính chính.

Đoạn tiếp theo dùng template:

```java
TransactionTemplate readTx = TemplateFactory.newReportTemplate(manager);
String result = readTx.execute(status -> readFromRepository());
```

Callback có thể trả giá trị bất kỳ theo generic `T`; `execute()` trả lại giá trị đó khi transaction kết thúc hợp lệ. Nếu transaction commit thất bại, `execute()` có thể **ném exception thay vì trả kết quả**.

## 3. Khai báo bằng số hằng hay tên hằng?

`TransactionTemplate` kế thừa configuration từ `DefaultTransactionDefinition`, nên có hai cách diễn đạt.

### Hằng số kiểu `int`

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_REPEATABLE_READ
);
tx.setReadOnly(true);
tx.setTimeout(30);
```

### Tên hằng số kiểu `String`

```java
tx.setPropagationBehaviorName("PROPAGATION_REQUIRES_NEW");
tx.setIsolationLevelName("ISOLATION_REPEATABLE_READ");
tx.setReadOnly(true);
tx.setTimeout(30);
```

Hai cách dẫn đến cùng ý định cấu hình. Tên không đúng sẽ bị validation của Spring từ chối; đừng đưa giá trị tùy ý như `"REQUIRES_NEW"` khi API này yêu cầu tên hằng `"PROPAGATION_REQUIRES_NEW"`.

Khi dùng annotation, API sẽ sử dụng **enum**:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true,
    timeout = 30
)
```

Khi dùng `TransactionTemplate`, setter nhận **`int`/tên hằng**, không nhận trực tiếp enum `Propagation` hay `Isolation`. Nếu muốn dùng enum để thống nhất cách biểu đạt, có thể truyền `.value()` khi phiên bản API hỗ trợ, nhưng các hằng `TransactionDefinition` là phương án rõ ràng, dễ tra tài liệu.

## 4. `setPropagationBehavior`: quyết định quan hệ với transaction hiện có

Đây là thuộc tính có ảnh hưởng **trước** khi xét ba thuộc tính còn lại, vì một callback có bắt đầu transaction mới hay không phụ thuộc propagation.

### 4.1. `PROPAGATION_REQUIRED` (mặc định)

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
```

- **Chưa có transaction:** manager tạo transaction vật lý mới.
- **Đã có transaction tương thích:** callback tham gia transaction vật lý đó, không tạo transaction mới.
- Nếu callback là participant, isolation/read-only/timeout riêng trên template **không tự override** đặc tính transaction đã được owner xác lập theo cấu hình mặc định của manager.
- Nếu participant gặp lỗi dẫn đến rollback-only, toàn transaction được chia sẻ có thể không commit được; owner có thể nhận `UnexpectedRollbackException` khi nó cố commit.

`REQUIRED` phù hợp cho các bước cần atomicity chung: nếu một bước bắt buộc thất bại, cả unit of work được rollback.

### 4.2. `PROPAGATION_REQUIRES_NEW`

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
```

- Mở **transaction vật lý riêng** cho callback.
- Nếu đã có transaction bên ngoài, manager suspend context của outer trước khi mở inner, rồi resume outer sau khi inner kết thúc.
- Isolation/read-only/timeout mới trên template có cơ hội được áp dụng cho transaction độc lập này.
- Inner có thể commit dù outer sau đó rollback; ngược lại, inner rollback không mặc nhiên rollback outer.
- Với JDBC, có thể cần **connection thứ hai** trong khi outer vẫn giữ connection; connection pool phải đủ lớn.

Không dùng `REQUIRES_NEW` chỉ để làm một câu SQL nhanh hơn. Nó thay đổi **tính atomicity** và thứ tự commit của các bước nghiệp vụ.

### 4.3. `PROPAGATION_NESTED`

```java
tx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_NESTED
);
```

- Khi manager và JDBC driver hỗ trợ savepoint, inner callback có thể tạo savepoint trong **cùng transaction vật lý**.
- Rollback inner có thể quay về savepoint mà outer vẫn tiếp tục transaction.
- Khi không có transaction ngoài, `NESTED` thường bắt đầu một transaction mới giống `REQUIRED`.
- `NESTED` không tạo isolation/timeout/read-only policy độc lập cho một physical transaction đang tồn tại.
- Không giả định JPA/JTA hoặc mọi driver hỗ trợ nested transaction.

Nó thích hợp khi business cho phép **bỏ một đoạn dữ liệu tùy chọn** mà vẫn commit phần trước/sau, nhưng cần kiểm thử trên transaction manager thực.

### 4.4. Các propagation khác

| Hằng số | Khi có transaction ngoài | Khi không có transaction ngoài |
| --- | --- | --- |
| `PROPAGATION_SUPPORTS` | Tham gia transaction nếu phù hợp | Chạy không có transaction vật lý mới |
| `PROPAGATION_MANDATORY` | Bắt buộc tham gia | Báo lỗi vì thiếu transaction |
| `PROPAGATION_NOT_SUPPORTED` | Suspend transaction rồi chạy không có transaction | Chạy không có transaction |
| `PROPAGATION_NEVER` | Báo lỗi khi có transaction | Chạy không có transaction |
| `PROPAGATION_REQUIRED` | Tham gia | Tạo transaction |
| `PROPAGATION_REQUIRES_NEW` | Suspend rồi tạo transaction mới | Tạo transaction |
| `PROPAGATION_NESTED` | Dùng savepoint nếu hỗ trợ | Tạo transaction |

`NOT_SUPPORTED`/`SUPPORTS` không bảo đảm mọi JDBC statement “không có transaction” sẽ lập tức dùng cùng JDBC connection; transaction synchronization và resource binding có chi tiết phụ thuộc manager. Nhưng **chúng không mở một physical transaction mới chỉ để áp isolation/readOnly/timeout**.

**Quy tắc nhớ:** propagation quyết định “tạo/join/suspend/không có transaction” trước khi bạn có thể suy luận các đặc tính còn lại.

## 5. `setIsolationLevel`: mức cô lập của transaction vật lý

```java
tx.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
```

Hằng số Spring:

| Hằng | Giá trị | Ghi chú |
| --- | ---: | --- |
| `ISOLATION_DEFAULT` | `-1` | Dùng isolation hiện có/mặc định của resource |
| `ISOLATION_READ_UNCOMMITTED` | `1` | Có thể bị database nâng/ánh xạ sang mức mạnh hơn |
| `ISOLATION_READ_COMMITTED` | `2` | Không đọc dữ liệu chưa commit theo semantics hỗ trợ |
| `ISOLATION_REPEATABLE_READ` | `4` | Khả năng đọc lặp lại phụ thuộc DBMS |
| `ISOLATION_SERIALIZABLE` | `8` | Mức cô lập cao nhất trong JDBC enum thông dụng |

Bốn mức cụ thể tương ứng `java.sql.Connection.TRANSACTION_*`. `ISOLATION_DEFAULT=-1` **không phải** một JDBC isolation level; Spring hiểu nó là **không yêu cầu override**.

### Isolation áp dụng lúc nào?

Giả sử một callback ngoài đã bắt đầu transaction JDBC T ở `READ_COMMITTED`:

```java
TransactionTemplate outer = new TransactionTemplate(manager);
outer.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
outer.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);

TransactionTemplate inner = new TransactionTemplate(manager);
inner.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
inner.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE
);

outer.execute(outerStatus -> {
    inner.execute(innerStatus -> {
        // Vẫn tham gia T đã có; thường là READ_COMMITTED.
        return null;
    });
    return null;
});
```

Dù `inner` khai báo `SERIALIZABLE`, nó dùng `REQUIRED` nên **tham gia T**. Với manager mặc định, isolation riêng của participant không nâng isolation cho connection của T. Muốn independent isolation, cần tạo transaction thật sự mới **và** chấp nhận sự khác biệt atomicity; hoặc yêu cầu isolation đúng ngay ở outer transaction owner.

### Phát hiện mismatch bằng `validateExistingTransaction`

`AbstractPlatformTransactionManager` hỗ trợ cấu hình:

```java
DataSourceTransactionManager manager =
    new DataSourceTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

Nếu manager này được sử dụng và inner `REQUIRED` yêu cầu isolation không tương thích với T hiện có, nó có thể từ chối join bằng `IllegalTransactionStateException`. Không nên bật flag này mà chưa kiểm thử các call chain vốn dựa vào việc join mặc dù các inner declaration khác nhau.

### Isolation thực tế phụ thuộc tài nguyên

Chẳng hạn, H2 mặc định thường ở `READ_COMMITTED`, PostgreSQL cũng thường ở `READ_COMMITTED`, còn MySQL InnoDB thường dùng `REPEATABLE_READ`. Nhưng connection pool/driver/session có thể thay đổi. Muốn biết physical isolation trong JDBC transaction, đo **chính connection đã được Spring bind**:

```java
Integer actual = jdbcTemplate.execute(
    (ConnectionCallback<Integer>) Connection::getTransactionIsolation
);
```

Đây là snippet cần các imports/bean đầy đủ như trong demo. Không tự mượn connection khác từ pool rồi coi đó là isolation của transaction hiện tại.

## 6. `setReadOnly`: chỉ dẫn cho manager/driver/database

```java
tx.setReadOnly(true);
```

Với `DataSourceTransactionManager`, Spring có thể gọi JDBC `Connection.setReadOnly(true)` khi bắt đầu transaction mới. Driver/DBMS có thể dùng hint này để tối ưu, có thể xử lý thành policy, hoặc **bỏ qua nó**.

**Không có bảo đảm phổ quát** rằng `tx.setReadOnly(true)` khiến mọi `INSERT`, `UPDATE`, `DELETE` thất bại:

- H2 `JdbcConnection.setReadOnly(true)` trên writable in-memory DB có thể bị bỏ qua; `Connection.isReadOnly()` vẫn trả `false`.
- Một database có cơ chế transaction read-only ở tầng SQL có thể từ chối DML khi chế độ đó được bật.
- Với `JpaTransactionManager`/Hibernate, cờ read-only có thể ảnh hưởng flush mode và dirty checking.
- Với một custom manager, giá trị này có thể chỉ được dùng như metadata hoặc routing hint.
- `readOnly=true` **không thay thế quyền `SELECT`-only của database user**.

Để quan sát Spring context:

```java
boolean springReadOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

Để quan sát JDBC driver:

```java
Boolean jdbcReadOnly = jdbcTemplate.execute(
    (ConnectionCallback<Boolean>) Connection::isReadOnly
);
```

Hai giá trị **có thể khác nhau**. `springReadOnly=true` nghĩa Spring đang công bố transaction read-only, không chứng minh database chặn ghi.

### Khi `REQUIRED` tham gia transaction đã mở

Nếu outer T là read-write và inner template đặt `readOnly=true` nhưng dùng `REQUIRED`, inner **thường kế thừa policy của T**. Cờ Spring trong inner context vẫn có thể là `false`. Ngược lại, inner `readOnly=false` tham gia outer read-only không tự mở writable physical transaction.

Trong demo, ta cố ý tạo một template `REQUIRED` khai báo `readOnly=true` rồi gọi nó trong transaction outer read-write. Kết quả cờ Spring trong inner vẫn là `false`, làm rõ nguyên tắc này.

### Muốn database thực sự cấm ghi?

Với Spring JDBC và DBMS phù hợp, `DataSourceTransactionManager#setEnforceReadOnly(true)` có thể yêu cầu **`SET TRANSACTION READ ONLY`** khi bắt đầu transaction mới. Hỗ trợ SQL phụ thuộc DBMS, cấu hình session và driver. Trong production, nếu mục tiêu là **bảo mật**, sử dụng quyền DB giới hạn hoặc tài khoản/replica chỉ đọc, không chỉ một hint trên template.

Ví dụ chương trình của bài dùng H2 và **không bật SQL enforce read-only**, vì nó tập trung vào cấu hình bốn thuộc tính và hiệu lực thực tế của chúng.

## 7. `setTimeout`: giây, mặc định và giới hạn thực tế

```java
tx.setTimeout(15); // 15 giây
```

`TransactionTemplate#setTimeout(int)` nhận số giây. Mặc định:

```java
tx.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT); // -1
```

`-1` nghĩa **dùng timeout mặc định do manager/resource quyết định hoặc không có**. Nó không đặt một timer Java tự dừng mọi code tại thời điểm chính xác.

### Timeout áp dụng ở đâu?

- **Transaction mới:** manager có thể thiết lập deadline tương ứng.
- **`REQUIRED` tham gia một transaction hiện có:** cấu hình timeout của inner template **không đặt lại deadline** của outer T.
- **`REQUIRES_NEW`:** transaction mới có thể dùng timeout riêng.
- **`NESTED` trên cùng T:** savepoint không tự tạo một physical transaction có deadline độc lập.
- **Các propagation chạy không có T:** timeout không biến callback không có transaction thành một transaction mới.

`DataSourceTransactionManager` và `JdbcTemplate` có thể phối hợp **transaction timeout với JDBC statement timeout**. `JdbcTemplate` sử dụng transaction context để đặt timeout còn lại trên các `Statement` khi thích hợp. JDBC driver/DBMS quyết định khả năng ngắt câu query đang chạy, và một thao tác Java CPU-bound hoặc `Thread.sleep()` không được bảo đảm sẽ bị ngắt đúng giây hết hạn.

### Ví dụ timeout mang ý định rõ ràng

```java
TransactionTemplate shortTx = new TransactionTemplate(manager);
shortTx.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
shortTx.setTimeout(3);
shortTx.executeWithoutResult(status -> performDatabaseWork());
```

Đây là snippet, cần `manager` và `performDatabaseWork()` từ ứng dụng. Khi test, không nên assert một câu `Thread.sleep(3001)` **chắc chắn** ném exception: transaction timeout không giống wall-clock cancellation của Java thread. Nếu cần kiểm tra thực sự, chạy integration test với DBMS, driver, query có thể bị timeout và deadline phù hợp; không dựa vào độ trễ máy test.

### Timeout không thay thế network timeout hoặc SLA

- `HikariCP.connectionTimeout` giới hạn **thời gian đợi connection từ pool**, khác transaction timeout.
- JDBC `Statement.setQueryTimeout()` giới hạn **thời gian xử lý một câu lệnh**, với khả năng enforcement tùy driver.
- HTTP client timeout giới hạn một network request, không đồng nghĩa rollback DB.
- Transaction timeout giới hạn thời gian transaction theo transaction manager/resource và cơ chế thực thi tương ứng.

Muốn tránh transaction giữ connection/lock quá lâu, phải phối hợp query timeout, network timeout, queue limits, logic retry, giới hạn transaction scope và observability.

## 8. Mẫu cấu hình chuẩn: một template cho một chính sách

Vì `TransactionTemplate` chứa các property có thể thay đổi bằng setter, nên tốt nhất cấu hình **một lần** khi khởi tạo bean/constructor.

```java
@Configuration
class TransactionPolicyConfiguration {

    @Bean("readerTx")
    TransactionTemplate readerTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(true);
        tx.setTimeout(10);
        return tx;
    }

    @Bean("auditTx")
    TransactionTemplate auditTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_DEFAULT
        );
        tx.setReadOnly(false);
        tx.setTimeout(5);
        return tx;
    }
}
```

Đây là **snippet cấu hình minh họa**; cần imports của Spring và manager phù hợp. Không thêm nguyên snippet này vào project ở mục 10 vì ở đó đã có bean riêng.

Hai bean có chính sách khác nhau:

- `readerTx`: read-only transaction chỉ khi được mở mới; nếu tham gia outer writable T, policy inner không nhất thiết có tác dụng độc lập.
- `auditTx`: transaction mới độc lập, read-write; nó **có thể commit dù caller ngoài rollback**, một đặc tính phải được nghiệp vụ cho phép.

**Không dùng một singleton template rồi thay setter theo từng request:**

```java
// Phản ví dụ: tránh làm như thế khi template đang được chia sẻ.
sharedTx.setReadOnly(request.isReadOnly());
sharedTx.setTimeout(request.timeoutSeconds());
sharedTx.execute(status -> doWork(request));
```

Nếu hai thread chạy đồng thời, thread A có thể làm thay cấu hình mà thread B tưởng mình đang dùng. **`TransactionTemplate` thread-safe khi thực thi callback với configuration đã ổn định**, nhưng các setter thay đổi configuration state; nó không phải “một definition độc lập cho mỗi call”.

Giải pháp: định nghĩa **nhiều template** được cấu hình sẵn, hoặc tạo một instance mới (trong phạm vi cần thiết) cho một policy thực sự động. Cách latter nên đi kèm validation vì timeout/isolation từ request trực tiếp có thể thành một rủi ro về hiệu năng và consistency.

### Tạo template từ `DefaultTransactionDefinition`?

`TransactionTemplate` tự kế thừa `DefaultTransactionDefinition`, nên trực tiếp gọi setter như trên là đúng và ngắn. `TransactionTemplate` không có constructor phổ quát nhận mọi `TransactionDefinition` rồi tự sao chép mọi property theo một callback kiểu bạn tự tưởng tượng; đọc đúng Javadoc của phiên bản Spring nếu dùng một overload mới hơn.

## 9. Callback, kết quả và rollback policy

Khi chạy:

```java
String orderId = tx.execute(status -> {
    insertOrder();
    insertOrderLines();
    return "ORDER-100";
});
```

`execute()` lấy một transaction status phù hợp, chạy callback rồi commit/rollback theo kết quả. Callback có thể quan sát:

```java
boolean newPhysicalTx = status.isNewTransaction();
boolean markedRollback = status.isRollbackOnly();
```

### Trả kết quả bình thường

```java
Result result = tx.execute(status -> {
    writeTwoRecords();
    return Result.ok();
});
```

Đây là snippet giả định `Result` và `writeTwoRecords()` được định nghĩa trong ứng dụng. `return` bình thường thường dẫn tới **commit** nếu transaction mới được sở hữu và không bị rollback-only, không gặp lỗi manager/DB.

### Ném unchecked exception để rollback

```java
tx.executeWithoutResult(status -> {
    writeFirstRecord();
    throw new IllegalStateException("Cannot finish operation");
});
```

Với transaction mới, Spring `TransactionTemplate` xử lý unchecked exception/Error bằng rollback rồi ném lại. Nếu code bên ngoài callback bắt exception **sau `execute()`**, transaction manager đã có cơ hội rollback trước khi catch.

### Chủ động `status.setRollbackOnly()`

```java
Result result = tx.execute(status -> {
    writeFirstRecord();

    if (!businessRuleSatisfied()) {
        status.setRollbackOnly();
        return Result.rejected();
    }

    writeSecondRecord();
    return Result.accepted();
});
```

Phương án này hữu ích khi hợp đồng yêu cầu **trả Result thất bại** thay vì ném exception. Với transaction mới do template sở hữu, nó rollback trước khi trả kết quả. Nếu template tham gia transaction bao ngoài, dấu rollback-only có thể lan tới transaction chung; caller ngoài có thể nhận `UnexpectedRollbackException` khi cố commit.

### Checked exception trong callback

Interface `TransactionCallback<T>.doInTransaction(TransactionStatus)` **không khai báo `throws IOException`**. Vì vậy, không thể viết `throw new IOException(...)` trực tiếp trong lambda `execute(...)` nếu chưa bắt/wrap theo Java checked exception rules.

```java
try {
    return tx.execute(status -> {
        try {
            return readFromExternalSource(); // có thể ném IOException
        } catch (java.io.IOException ex) {
            throw new java.io.UncheckedIOException(ex);
        }
    });
} catch (java.io.UncheckedIOException ex) {
    // Callback đã ném unchecked exception qua TransactionTemplate.
    throw ex;
}
```

Đây là snippet giả định method `readFromExternalSource()` và biến `tx` tồn tại. Có thể dùng `status.setRollbackOnly()` và trả kết quả thất bại nếu muốn xử lý checked exception **bên trong** callback.

Điểm khác biệt quan trọng: không áp nguyên si mặc định **“checked exception không rollback” của `@Transactional`** vào callback rồi suy đoán. Cần xét **lỗi nào có thể thoát từ `TransactionCallback`**, việc bạn wrap, và `TransactionTemplate.execute` điều phối exception ra sao. `TransactionTemplate` không có thuộc tính `rollbackFor` như annotation; chính code callback kiểm soát conversion hoặc rollback-only.

## 10. Dự án runnable: khai báo đủ bốn thuộc tính, quan sát hiệu lực thật

### 10.1. Mục tiêu thí nghiệm

Dự án gồm **năm template cấu hình sẵn**, tập trung vào bốn thuộc tính:

1. `defaultTx`: không set property nào; kiểm tra defaults.
2. `outerTx`: `REQUIRED`, `READ_COMMITTED`, `readOnly=false`, `timeout=15`.
3. `joinTx`: `REQUIRED`, `SERIALIZABLE`, `readOnly=true`, `timeout=2`, được gọi từ `outerTx` đang mở.
4. `separateTx`: `REQUIRES_NEW`, `SERIALIZABLE`, `readOnly=true`, `timeout=4`.
5. `queryTx`: `REQUIRED`, `DEFAULT`, `readOnly=true`, `timeout=8`, được gọi khi chưa có transaction.

H2 được nối qua HikariCP; pool được cấu hình **baseline `REPEATABLE_READ`** để thể hiện `ISOLATION_DEFAULT` lấy isolation của connection/resource, không tự động chọn `READ_COMMITTED`. Khi `outerTx` yêu cầu `READ_COMMITTED`, Spring JDBC manager tạm đổi isolation của connection thuộc transaction mới; sau đó khôi phục.

Ta sẽ chứng minh bằng các dòng log tự tạo:

- `joinTx` **không** đổi isolation, read-only flag hay timeout của outer physical transaction đang có.
- `separateTx` dùng transaction mới nên yêu cầu isolation `SERIALIZABLE` và cờ Spring read-only riêng có cơ hội được áp dụng.
- H2 có thể bỏ qua JDBC `setReadOnly(true)`, do đó `springRO=true` nhưng `jdbcRO=false`.
- `TransactionTemplate.execute()` ném exception thì rollback; `setRollbackOnly()` có thể rollback mà vẫn trả `Result` rõ nghĩa.

**Lưu ý về timeout:** demo in giá trị **cấu hình** timeout của template và sử dụng timeout trong manager, nhưng không cố tạo một bài kiểm thử wall-clock thiếu ổn định. Không khẳng định việc chạy dưới 2/4/15 giây đã chứng minh cơ chế timeout cưỡng chế của driver.

### 10.2. Cấu trúc project

```text
transaction-template-properties/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/template/
    │   │   ├── TemplateConfig.java
    │   │   ├── TemplateScenarioService.java
    │   │   └── TransactionTemplateDemoApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/template/
        └── TransactionTemplateDemoTest.java
```

Tạo project Gradle Java 17+ từ Spring Initializr (Spring Boot 3.3.5), có wrapper. Thêm các file đúng tên và package. Không cần web server hoặc kết nối database ngoài.

### 10.3. `settings.gradle`

```groovy
rootProject.name = 'transaction-template-properties'
```

### 10.4. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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

`spring-boot-starter-jdbc` cung cấp Spring transaction API, `JdbcTemplate` và HikariCP. H2 được dùng làm DB in-memory. Không thêm `spring-boot-starter-web` chỉ để chạy một demo transaction.

### 10.5. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:template_properties;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
    hikari:
      maximum-pool-size: 4
      transaction-isolation: TRANSACTION_REPEATABLE_READ
  sql:
    init:
      mode: always
```

Pool baseline là `TRANSACTION_REPEATABLE_READ`. Cấu hình `maximum-pool-size=4` giúp `REQUIRES_NEW` mượn thêm connection khi outer vẫn đang giữ một connection. Với pool chỉ có một connection, `REQUIRES_NEW` lồng trong JDBC transaction có thể **chờ connection** rồi timeout ở pool dù transaction timeout còn lại khác.

### 10.6. `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

Tạo một bảng quan sát commit/rollback thật. Không tạo dữ liệu ban đầu; mỗi scenario sẽ `DELETE FROM tx_events` **ngoài** transaction của nó để reset fixture. ID duy nhất cho từng scenario, và câu SQL hợp lệ giúp cô lập hành vi transaction khỏi DB constraint error.

### 10.7. `src/main/java/example/template/TemplateConfig.java`

```java
package example.template;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration(proxyBeanMethods = false)
public class TemplateConfig {

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new DataSourceTransactionManager(source);
    }

    @Bean("defaultTx")
    TransactionTemplate defaultTx(PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }

    @Bean("outerTx")
    TransactionTemplate outerTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_READ_COMMITTED
        );
        tx.setReadOnly(false);
        tx.setTimeout(15);
        tx.setName("demo.outer");
        return tx;
    }

    @Bean("joinTx")
    TransactionTemplate joinTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_SERIALIZABLE
        );
        tx.setReadOnly(true);
        tx.setTimeout(2);
        tx.setName("demo.participant");
        return tx;
    }

    @Bean("separateTx")
    TransactionTemplate separateTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_SERIALIZABLE
        );
        tx.setReadOnly(true);
        tx.setTimeout(4);
        tx.setName("demo.independent");
        return tx;
    }

    @Bean("queryTx")
    TransactionTemplate queryTx(PlatformTransactionManager manager) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        tx.setIsolationLevel(
            TransactionDefinition.ISOLATION_DEFAULT
        );
        tx.setReadOnly(true);
        tx.setTimeout(8);
        tx.setName("demo.query");
        return tx;
    }
}
```

Mỗi template giữ **một chính sách ổn định**, được Spring inject và dùng lại. Import `Qualifier` không cần ở file configuration này (Java cho phép import chưa sử dụng); nó sẽ được dùng trong service. Có một transaction manager JDBC duy nhất, dùng đúng `DataSource` mà `JdbcTemplate` sử dụng. Không khai báo thêm manager khác trong project.

Các giá trị trên `joinTx` là **yêu cầu của transaction definition**, không phải bằng chứng isolation hay read-only đã thay đổi khi nó join T. Đó là điều chúng ta kiểm chứng tiếp.

### 10.8. `src/main/java/example/template/TemplateScenarioService.java`

```java
package example.template;

import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TemplateScenarioService {

    private final JdbcTemplate jdbc;
    private final TransactionTemplate outer;
    private final TransactionTemplate joined;
    private final TransactionTemplate separate;
    private final TransactionTemplate query;

    public TemplateScenarioService(
            JdbcTemplate jdbc,
            @Qualifier("outerTx") TransactionTemplate outer,
            @Qualifier("joinTx") TransactionTemplate joined,
            @Qualifier("separateTx") TransactionTemplate separate,
            @Qualifier("queryTx") TransactionTemplate query) {
        this.jdbc = jdbc;
        this.outer = outer;
        this.joined = joined;
        this.separate = separate;
        this.query = query;
    }

    private static String isolationName(int level) {
        return switch (level) {
            case Connection.TRANSACTION_NONE -> "NONE";
            case Connection.TRANSACTION_READ_UNCOMMITTED ->
                "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ ->
                "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "UNKNOWN(" + level + ")";
        };
    }

    private String flags(TransactionStatus status) {
        Integer isolation = jdbc.execute(
            (ConnectionCallback<Integer>) Connection::getTransactionIsolation
        );
        Boolean jdbcReadOnly = jdbc.execute(
            (ConnectionCallback<Boolean>) Connection::isReadOnly
        );

        if (isolation == null || jdbcReadOnly == null) {
            throw new IllegalStateException("No JDBC transaction metadata");
        }

        boolean springReadOnly = TransactionSynchronizationManager
            .isCurrentTransactionReadOnly();

        return "new=" + status.isNewTransaction()
            + " isolation=" + isolationName(isolation)
            + " springRO=" + springReadOnly
            + " jdbcRO=" + jdbcReadOnly;
    }

    private void insert(int id, String eventName) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, eventName
        );
    }

    private String rows() {
        List<String> values = jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, index) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
        return values.toString();
    }

    public List<String> runScopes() {
        jdbc.update("DELETE FROM tx_events");

        List<String> trace = new ArrayList<>();

        outer.execute(outerStatus -> {
            insert(1, "outer");
            trace.add("OUTER " + flags(outerStatus));

            joined.execute(innerStatus -> {
                insert(2, "joined");
                trace.add("JOINED " + flags(innerStatus));
                return null;
            });

            separate.execute(innerStatus -> {
                trace.add("SEPARATE " + flags(innerStatus));
                return null;
            });

            trace.add("RESUMED " + flags(outerStatus));
            return null;
        });

        trace.add("ROWS=" + rows());
        return trace;
    }

    public String runQuery() {
        return query.execute(this::flags);
    }

    public String runExceptionRollback() {
        jdbc.update("DELETE FROM tx_events");
        String signal = "completed";

        try {
            outer.execute(outerStatus -> {
                insert(10, "before-error");

                joined.execute(innerStatus -> {
                    insert(11, "joined-before-error");
                    return null;
                });

                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            signal = ex.getMessage();
        }

        return "signal=" + signal + " rows=" + rows();
    }

    public String runManualRollback() {
        jdbc.update("DELETE FROM tx_events");

        String result = outer.execute(status -> {
            insert(20, "temporary");
            status.setRollbackOnly();
            return "REJECTED";
        });

        return "result=" + result + " rows=" + rows();
    }
}
```

**Phân tích code:**

- `flags(status)` sử dụng `JdbcTemplate.execute(ConnectionCallback)` để đo **connection JDBC đang gắn với transaction**. Nếu tự lấy connection tùy ý từ pool, có thể đo nhầm connection.
- `status.isNewTransaction()` phân biệt một callback tạo transaction vật lý mới với callback `REQUIRED` đang join. Đây không phải phép đo số JDBC connections trong mọi manager, nhưng đúng ý nghĩa trong demo JDBC này.
- `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` đọc metadata Spring của transaction đang chạy.
- H2 `Connection.isReadOnly()` trên database writable có thể trả `false` dù transaction definition là read-only, vì driver bỏ qua hint.
- `runScopes()` tạo outer transaction, rồi thực thi `joined` và `separate` bằng **chính API `execute()`**, không cần Spring AOP để intercept method `runScopes()`.
- `runQuery()` chạy ngoài transaction nào khác, do đó `queryTx` tạo một T mới ở isolation `DEFAULT` từ pool baseline `REPEATABLE_READ`.
- `runExceptionRollback()` ném `IllegalStateException` **ra khỏi outer callback**; template rollback toàn T. Việc `joined` return thành công trước đó không tạo commit độc lập.
- `runManualRollback()` đặt rollback-only trên `outerStatus`, trả chuỗi `"REJECTED"`; manager rollback T thay vì commit.

`ArrayList trace` là biến cục bộ của một lần gọi và callback diễn ra **đồng bộ**, không tạo nhiệm vụ background; việc callback thêm chuỗi vào list là hợp lệ. Các template bean vẫn có thể được nhiều thread dùng đồng thời vì configuration không thay đổi.

### 10.9. `src/main/java/example/template/TransactionTemplateDemoApplication.java`

```java
package example.template;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionTemplateDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionTemplateDemoApplication.class, args);
    }

    private static void showConfig(
            String name, TransactionTemplate template) {
        System.out.println(
            "CONFIG " + name
            + "=" + template.getPropagationBehavior()
            + "/" + template.getIsolationLevel()
            + "/" + template.isReadOnly()
            + "/" + template.getTimeout()
        );
    }

    @Bean
    ApplicationRunner demonstrate(
            TemplateScenarioService service,
            @Qualifier("defaultTx") TransactionTemplate defaultTx,
            @Qualifier("outerTx") TransactionTemplate outerTx,
            @Qualifier("joinTx") TransactionTemplate joinTx,
            @Qualifier("separateTx") TransactionTemplate separateTx,
            @Qualifier("queryTx") TransactionTemplate queryTx) {
        return args -> {
            showConfig("default", defaultTx);
            showConfig("outer", outerTx);
            showConfig("joined", joinTx);
            showConfig("separate", separateTx);
            showConfig("query", queryTx);

            for (String line : service.runScopes()) {
                System.out.println(line);
            }

            System.out.println("QUERY " + service.runQuery());
            System.out.println("ROLLBACK " +
                service.runExceptionRollback());
            System.out.println("MANUAL " +
                service.runManualRollback());
        };
    }
}
```

`@SpringBootApplication` quét cùng package và nhận `TemplateConfig`, `TemplateScenarioService`. Các templates không phải Spring AOP proxies; chúng là các object Spring bean với cấu hình transaction definition. Spring Boot khởi tạo `JdbcTemplate` và datasource H2 nhờ JDBC starter.

Không cần `@EnableTransactionManagement` chỉ để `TransactionTemplate.execute()` chạy, vì nó gọi `PlatformTransactionManager` trực tiếp. Nếu dự án đồng thời dùng `@Transactional`, Spring Boot sẽ cấu hình transaction infrastructure theo các điều kiện auto-configuration của nó.

### 10.10. Cách chạy

Trong project đã tạo Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu chưa có wrapper, dùng `gradle bootRun` với bản Gradle tương thích hoặc tạo wrapper. Không gọi `javac`/`java` trực tiếp mà thiếu JAR Spring Boot/JDBC/Hikari/H2 trong classpath.

### 10.11. Stdout dự kiến

Bỏ qua Spring Boot/Gradle startup logs. Những dòng do chính ứng dụng in ra:

```text
CONFIG default=0/-1/false/-1
CONFIG outer=0/2/false/15
CONFIG joined=0/8/true/2
CONFIG separate=3/8/true/4
CONFIG query=0/-1/true/8
OUTER new=true isolation=READ_COMMITTED springRO=false jdbcRO=false
JOINED new=false isolation=READ_COMMITTED springRO=false jdbcRO=false
SEPARATE new=true isolation=SERIALIZABLE springRO=true jdbcRO=false
RESUMED new=true isolation=READ_COMMITTED springRO=false jdbcRO=false
ROWS=[1:outer, 2:joined]
QUERY new=true isolation=REPEATABLE_READ springRO=true jdbcRO=false
ROLLBACK signal=boom rows=[]
MANUAL result=REJECTED rows=[]
```

Đây là **kết quả kỳ vọng từ code và cấu hình**, không phải tuyên bố rằng project đã được biên dịch/chạy trong môi trường hiện tại.

### 10.12. Diễn giải stdout theo từng property

**`CONFIG ...`:** bốn số/giá trị theo thứ tự `propagation/isolation/readOnly/timeout`. Hằng `REQUIRED=0`, `REQUIRES_NEW=3`, `DEFAULT isolation=-1`, `READ_COMMITTED=2`, `SERIALIZABLE=8`. `TIMEOUT_DEFAULT=-1` không đồng nghĩa timeout âm ngoài DB, mà là sentinel “dùng default”.

**`OUTER`:** `outerTx` sở hữu transaction vật lý mới; isolation được thiết lập `READ_COMMITTED`. Spring read-only flag `false` và H2 JDBC read-only flag `false`.

**`JOINED`:** dù `joinTx` **khai báo** isolation `SERIALIZABLE`, readOnly `true`, timeout 2 giây, `REQUIRED` thấy T ngoài nên join T. Status là `new=false`, isolation connection vẫn `READ_COMMITTED`, Spring read-only vẫn `false`. **Timeout 2 giây cũng không thay deadline của outer**, dù không được thể hiện trực tiếp qua hai cờ.

**`SEPARATE`:** `REQUIRES_NEW` bắt đầu transaction vật lý khác. Connection trong callback nhận isolation `SERIALIZABLE`; Spring công bố read-only `true`. Nhưng H2 `JdbcConnection.isReadOnly()` có thể trả `false` vì read-only chỉ là hint bị bỏ qua.

**`RESUMED`:** sau khi callback `separate` kết thúc, transaction outer tiếp tục với isolation `READ_COMMITTED` và read-only flag `false`, không bị “rò rỉ” metadata của transaction mới vào nó.

**`ROWS`:** hai INSERT của outer và joined đều thuộc cùng physical T, nên commit outer làm cả hai hàng tồn tại. Callback `separate` không ghi dữ liệu.

**`QUERY`:** khi không có outer T, `queryTx` với isolation `DEFAULT` bắt đầu T mới. Hikari baseline `REPEATABLE_READ` được giữ nguyên; Spring read-only metadata là `true`, H2 JDBC read-only flag vẫn `false`.

**`ROLLBACK`:** `IllegalStateException` thoát khỏi outer callback sau hai INSERT; Spring rollback toàn T và caller bắt exception sau `execute()`. Kết quả không có hàng nào còn.

**`MANUAL`:** callback trả `"REJECTED"` đồng thời đặt `status.setRollbackOnly()`; transaction mới rollback mà không cần ném exception. Đây là một mô hình return-result minh bạch, không nên trả `"SUCCESS"` sau khi mark rollback-only.

## 11. JUnit 5: kiểm tra configuration và hành vi thay vì nhìn annotation

Tạo file `src/test/java/example/template/TransactionTemplateDemoTest.java`:

```java
package example.template;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class TransactionTemplateDemoTest {

    @Autowired TemplateScenarioService service;
    @Autowired JdbcTemplate jdbc;

    @Autowired
    @Qualifier("defaultTx")
    TransactionTemplate defaultTx;

    @Autowired
    @Qualifier("outerTx")
    TransactionTemplate outerTx;

    @Autowired
    @Qualifier("joinTx")
    TransactionTemplate joinTx;

    @Autowired
    @Qualifier("separateTx")
    TransactionTemplate separateTx;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    @Test
    void defaultConfigurationMatchesTransactionDefinition() {
        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRED,
            defaultTx.getPropagationBehavior()
        );
        assertEquals(
            TransactionDefinition.ISOLATION_DEFAULT,
            defaultTx.getIsolationLevel()
        );
        assertEquals(false, defaultTx.isReadOnly());
        assertEquals(
            TransactionDefinition.TIMEOUT_DEFAULT,
            defaultTx.getTimeout()
        );
    }

    @Test
    void configurationHoldsFourDeclaredProperties() {
        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRED,
            outerTx.getPropagationBehavior()
        );
        assertEquals(
            TransactionDefinition.ISOLATION_READ_COMMITTED,
            outerTx.getIsolationLevel()
        );
        assertEquals(false, outerTx.isReadOnly());
        assertEquals(15, outerTx.getTimeout());

        assertEquals(
            TransactionDefinition.ISOLATION_SERIALIZABLE,
            joinTx.getIsolationLevel()
        );
        assertEquals(true, joinTx.isReadOnly());
        assertEquals(2, joinTx.getTimeout());

        assertEquals(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW,
            separateTx.getPropagationBehavior()
        );
        assertEquals(true, separateTx.isReadOnly());
        assertEquals(4, separateTx.getTimeout());
    }

    @Test
    void participantInheritsEffectiveOuterCharacteristics() {
        assertEquals(
            List.of(
                "OUTER new=true isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "JOINED new=false isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "SEPARATE new=true isolation=SERIALIZABLE " +
                    "springRO=true jdbcRO=false",
                "RESUMED new=true isolation=READ_COMMITTED " +
                    "springRO=false jdbcRO=false",
                "ROWS=[1:outer, 2:joined]"
            ),
            service.runScopes()
        );
    }

    @Test
    void resourceDefaultAndReadOnlyAreSeparatelyObservable() {
        assertEquals(
            "new=true isolation=REPEATABLE_READ " +
                "springRO=true jdbcRO=false",
            service.runQuery()
        );
    }

    @Test
    void uncheckedExceptionRollsBackPhysicalTransaction() {
        assertEquals(
            "signal=boom rows=[]",
            service.runExceptionRollback()
        );
    }

    @Test
    void statusSetRollbackOnlyReturnsFailureWithoutCommit() {
        assertEquals(
            "result=REJECTED rows=[]",
            service.runManualRollback()
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

Các test **không đặt `@Transactional`** trên test class/method. Nếu test framework tự tạo transaction, `REQUIRED` của `outerTx` có thể join T của test, khiến cả `isNewTransaction()` lẫn kết luận commit/rollback sai so với mục tiêu bài.

`@SpringBootTest` có thể chạy `ApplicationRunner` lúc dựng context; `@BeforeEach` xóa bảng trước mỗi test để fixture độc lập. Nếu chạy tests song song trên cùng H2 database, cần cô lập schema/fixture để tránh race.

**Phạm vi chứng minh:** test trên H2 chứng minh wiring/config và behavior của JDBC/H2. Khi chuyển sang PostgreSQL/MySQL/JPA, cần kiểm thử lại effective isolation, JDBC read-only flag và timeout bằng chính stack đó.

## 12. Cấu hình nâng cao: timeout, validation và default của transaction manager

### 12.1. Manager default timeout không phải template timeout

`TransactionTemplate` có thể giữ:

```java
template.setTimeout(TransactionDefinition.TIMEOUT_DEFAULT);
```

Tại runtime, manager có thể có default timeout được cấu hình, hoặc backend không hỗ trợ timeout. Ngược lại, nếu template đặt `15`, đó là **yêu cầu** timeout cho transaction mới được manager quản lý, không bảo đảm một deadline được thực thi bằng cách interrupt mọi Java statement.

Khi cần SLA, phải đo và giới hạn các bước network/CPU/query riêng biệt; transaction timeout chỉ là một thành phần.

### 12.2. Isolation/readOnly mismatch trên participant

Nếu `joinTx` dùng `REQUIRED` với `SERIALIZABLE`, `readOnly=true` nhưng outer T đang ở `READ_COMMITTED`, `readOnly=false`, manager **mặc định** có thể cho join và bỏ qua các inner declarations không tương thích. Điều này không tự làm code sai, nhưng có thể phá giả định của người viết callback.

Có thể bật:

```java
manager.setValidateExistingTransaction(true);
```

Khi đó manager có thể ném `IllegalTransactionStateException` khi isolation không tương thích. Với read-only, validation thường đặc biệt hữu ích cho yêu cầu **read-write tham gia outer read-only**, thay vì coi mọi read-only participant trong outer writable là sai. Hãy đọc contract thực tế của manager, không suy đoán manager kiểm tra tất cả biến thể readOnly theo cùng quy tắc.

### 12.3. Chọn manager đúng cho resource

- **Spring JDBC:** `DataSourceTransactionManager` hoặc `JdbcTransactionManager` phù hợp với transaction JDBC trên datasource được quản lý.
- **Spring Data JPA/Hibernate:** thường sử dụng `JpaTransactionManager`, không ghép bừa một JDBC manager khác cho repository JPA nếu không hiểu chia sẻ connection/EntityManager.
- **JTA/multiple resources:** cần manager phù hợp với phối hợp tài nguyên; một JDBC local transaction không tự trở thành distributed atomic transaction.
- **Reactive R2DBC:** dùng `ReactiveTransactionManager` và `TransactionalOperator`, không dùng imperative `TransactionTemplate` để tạo transaction context trên reactive subscription.

Trong ví dụ này, **một** `DataSourceTransactionManager` và **một** `JdbcTemplate` cùng dùng một `DataSource`, nên việc join/suspend/resume có ý nghĩa rõ ràng.

## 13. `@Transactional` so với `TransactionTemplate`

| Tiêu chí | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Cấu hình | Annotation với enums `Propagation`, `Isolation` | Setters với `TransactionDefinition` constants |
| Boundary | Method được Spring AOP/AspectJ advice | Phần code nằm trong callback `execute()` |
| Phụ thuộc proxy mode | Có thể bị self-invocation bỏ qua | Callback được gọi trực tiếp, không cần proxy để khởi tạo T |
| Trả kết quả | Return từ annotated method | Return value của callback được chuyển qua `execute()` |
| Rollback theo exception | Quy tắc `rollbackFor`/`noRollbackFor` được cấu hình | `execute` xử lý unchecked/Error; có thể `setRollbackOnly()` |
| Checked exception | Annotated method có thể khai báo `throws` | Callback interface không cho ném checked exception trực tiếp |
| Cấu hình nhiều chính sách | Nhiều annotations/methods | Nhiều template instances được cấu hình sẵn |
| Quan hệ với DB | Phụ thuộc manager/resource | **Cũng phụ thuộc manager/resource** |
| Reactive | Có quy tắc riêng với reactive transaction manager | Dùng `TransactionalOperator` cho reactive |

Một ứng dụng có thể kết hợp hai cách khi có lý do rõ ràng. Nhưng cần tránh lồng ngẫu nhiên một `@Transactional` outer với các template propagation khác nhau rồi ngạc nhiên khi `REQUIRES_NEW` commit độc lập hoặc `REQUIRED` làm rollback-only transaction chung.

## 14. Một số lỗi thường gặp

| Triệu chứng / ngộ nhận | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `setPropagationBehavior(Propagation.REQUIRES_NEW)` không compile | Setter nhận `int`, không phải enum | Dùng `TransactionDefinition.PROPAGATION_REQUIRES_NEW` |
| Đặt `setIsolationLevel(-1)` rồi tưởng là READ_UNCOMMITTED | `-1` nghĩa DEFAULT, không phải JDBC level | Dùng constants rõ nghĩa, kiểm tra resource |
| `joinTx` cấu hình `SERIALIZABLE` nhưng thực tế READ_COMMITTED | `REQUIRED` tham gia outer T | Yêu cầu isolation ở outer owner hoặc kiểm tra validation |
| `joinTx.setReadOnly(true)` nhưng Spring context vẫn false | Callback tham gia outer read-write T | Đặt policy ở transaction owner; đừng xem flag như mode riêng |
| `REQUIRES_NEW` làm mất atomicity của toàn workflow | Inner tạo/commit physical transaction độc lập | Chỉ dùng khi nghiệp vụ cho phép |
| `setTimeout(2)` trên inner không giới hạn outer | Outer đã có deadline riêng | Đặt timeout ở boundary sở hữu T |
| `Thread.sleep` quá 2 giây nhưng không thấy exception ngay | Timeout không tự interrupt Java thread | Kiểm thử thực trên JDBC statement và DBMS |
| `readOnly=true` mà SQL vẫn ghi được | JDBC hint có thể bị driver bỏ qua | Dùng DB enforcement/permissions khi phải cấm ghi |
| Test H2 chạy nhưng production khác | Driver/DB isolation/timeout khác | Integration test trên DB production-like |
| Thay template setter theo mỗi HTTP request | Configuration state dùng chung, race condition | Tạo policy bean bất biến sau setup hoặc template riêng |
| Callback đã `setRollbackOnly()` nhưng caller tin đã commit | Callback trả success sai hợp đồng | Trả failure result rõ nghĩa |
| Ném checked `IOException` trực tiếp trong lambda | `TransactionCallback` không khai báo checked throws | Catch/wrap hoặc rollback-only |
| Transaction “không chạy” dù có template bean | Chỉ khởi tạo template, chưa gọi `execute()` | Đặt code cần transaction trong callback |
| Callback dùng JDBC connection khác | Lấy connection ngoài transaction binding | Dùng `JdbcTemplate`/`DataSourceUtils` đúng manager |
| `UnexpectedRollbackException` khi outer commit | Inner `REQUIRED` participant đã mark shared T rollback-only | Truy nguyên scope rollback, giữ đúng invariant |
| `NESTED` không hoạt động | Manager/driver không hỗ trợ savepoint | Xác minh capability; đừng tự giả định |
| Dùng `TransactionTemplate` trong `CompletableFuture` không cùng T | Transaction imperative thường gắn với thread/resource context | Mở transaction riêng nơi task chạy hoặc thiết kế khác |
| `@Transactional` và template chồng nhau khó hiểu | Không xác định physical transaction owner | Vẽ call tree/propagation và kiểm tra status |
| Query không bị cancel đúng timeout | Driver/statement timeout không đảm bảo lập tức cancel | Kết hợp query/network timeouts, metrics, retry |

## 15. Một số mẫu thiết kế thực tế

### Mẫu A — đọc dữ liệu với policy truy vấn

```java
public List<CustomerView> findCustomers() {
    return readerTx.execute(status -> repository.findAllViews());
}
```

Mẫu snippet giả định có bean `readerTx`, `repository`, `CustomerView`. `readOnly=true` của template giúp thể hiện ý định; hiệu lực tối ưu/enforcement phụ thuộc backend. Nếu method được gọi trong outer T thì propagation được chọn quyết định có kế thừa outer hay không.

### Mẫu B — ghi hai bảng all-or-nothing

```java
public Receipt placeOrder(CreateOrder command) {
    return writeTx.execute(status -> {
        Long id = orders.insert(command);
        ledger.insertDebit(id, command.total());
        return new Receipt(id);
    });
}
```

Đây là snippet kiến trúc, chưa có các repository/types. Hai operations cần cùng manager/resource và transaction vật lý. Nếu một bước ném runtime exception, manager sẽ rollback scope cần thiết.

### Mẫu C — timeout ngắn cho một unit độc lập

```java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
isolated.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED
);
isolated.setReadOnly(false);
isolated.setTimeout(5);
```

Chỉ dùng khi unit thực sự **được phép commit độc lập**. Cấu hình tốt cho trường hợp này có thể không tốt cho atomicity của đơn hàng.

### Mẫu D — trả thất bại có chủ đích

```java
OperationResult result = tx.execute(status -> {
    debitAccount();

    if (!canCreditDestination()) {
        status.setRollbackOnly();
        return OperationResult.failure("No destination");
    }

    creditAccount();
    return OperationResult.success();
});
```

Snippet giả định domain types/helpers đã tồn tại. Gọi `setRollbackOnly()` phải đi đôi với một **failure result**; không báo thành công khi DB đã rollback. Kiểm thử dữ liệu sau transaction để xác nhận.

## 16. Bài tập tự kiểm tra

1. Template không gọi setter nào có propagation gì? **`PROPAGATION_REQUIRED`**.
2. `ISOLATION_DEFAULT=-1` có phải mức JDBC isolation không? **Không**; đó là sentinel của Spring để dùng resource default.
3. `setTimeout(20)` dùng đơn vị nào? **Giây**, cho transaction mới nếu manager hỗ trợ.
4. `setReadOnly(true)` có đảm bảo mọi DB từ chối UPDATE? **Không**, phụ thuộc manager/driver/DBMS.
5. `REQUIRED` inner đặt `SERIALIZABLE` mà outer T đã ở `READ_COMMITTED`, validation mặc định tắt thì sao? **Inner thường join outer ở `READ_COMMITTED`**.
6. `REQUIRES_NEW` inner có thể commit dù outer rollback không? **Có**, vì physical transaction độc lập.
7. `NESTED` bên trong T có luôn mở connection riêng không? **Không**; khi hỗ trợ, thường dùng JDBC savepoint trong cùng physical T.
8. Cấu hình timeout 2 giây ở `REQUIRED` inner có đặt lại deadline 15 giây của outer không? **Không theo mặc định**, inner không sở hữu physical T.
9. Vì sao không nên gọi setter trên singleton template theo từng request? **Configuration dùng chung có thể bị thay đổi giữa các thread**.
10. `status.setRollbackOnly()` trên callback sở hữu T có thể trả kết quả bình thường không? **Có**; T rollback và callback nên trả trạng thái thất bại minh bạch.
11. Tại sao ném `new IOException()` trực tiếp từ lambda `execute` không compile? **Callback không khai báo checked exception**.
12. Muốn xác nhận isolation thực tế nên gọi gì? **`Connection.getTransactionIsolation()` trên connection đúng đang tham gia transaction**.
13. `@Transactional` và `TransactionTemplate` có nhất thiết dùng hai transaction managers khác nhau không? **Không**; cả hai có thể sử dụng cùng `PlatformTransactionManager`.
14. Muốn một transaction read-only ở JPA thì có dùng thẳng JDBC template manager hay không? **Không tự suy ra**; chọn đúng JPA transaction manager/provider và kiểm thử.
15. Vì sao test kiểm tra `getTimeout()==4` chưa chứng minh một query bị hủy đúng giây thứ 4? **Đó mới là cấu hình trên template, không phải thử nghiệm deadline/driver**.

## 17. Checklist trước khi đưa `TransactionTemplate` vào production

1. Xác định đúng **một manager/resource** cho unit of work, đặc biệt nếu có JDBC lẫn JPA hoặc nhiều datasource.
2. Chọn propagation theo invariant: cần transaction chung, độc lập, savepoint hay không có T?
3. Xác định template có **thật sự bắt đầu T mới** ở call path hiện tại trước khi tin isolation/readOnly/timeout sẽ được áp riêng.
4. Đặt isolation cụ thể nếu nghiệp vụ cần consistency/locking tương ứng, thay vì dựa vào `DEFAULT` rồi suy đoán.
5. Hiểu `readOnly=true` là hint/optimization/enforcement tùy stack; với yêu cầu an ninh phải dùng quyền DB và test.
6. Đặt timeout hợp lý cho transaction owner, phối hợp statement timeout, connection pool timeout, network timeout và xử lý lỗi.
7. Không thay setters sau khi template được chia sẻ; tạo **template riêng cho từng policy**.
8. Test `REQUIRED` tham gia outer transaction và `REQUIRES_NEW` mở T độc lập; nhận diện bất ngờ commit/rollback.
9. Dùng `status.setRollbackOnly()` khi cần, và trả kết quả thất bại chính xác.
10. Giữ code bên trong callback ngắn và có thể retry/idempotent theo business requirements.
11. Đừng mở async/background operation rồi kỳ vọng nó được bao trong transaction imperative của callback đã return.
12. Khi dùng SQL cập nhật thực tế, kiểm tra DB sau **outermost transaction boundary**, không chỉ số row updated bên trong callback.
13. Viết integration tests trên DBMS và transaction manager production-like; không suy kết luận về timeout/lock từ H2.
14. Cung cấp observability về transaction manager, propagation, deadline và lỗi commit/rollback.
15. Khi đổi driver/Spring Boot/database, chạy lại tests vì các thuộc tính resource-dependent có thể thay đổi.

## Tài liệu tham khảo

- Spring Framework — **Programmatic Transaction Management / TransactionTemplate**: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — **Transaction Propagation** (physical vs logical transaction, `REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **`TransactionTemplate` Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — **`DefaultTransactionDefinition` setters/getters**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework — **`TransactionDefinition` constants**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — **`TransactionStatus` interface**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — **`DataSourceTransactionManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — **Declarative `@Transactional` settings**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- HikariCP — **Connection pool configuration (`transactionIsolation`)**: https://github.com/brettwooldridge/HikariCP/wiki/Configuration
- H2 — **JDBC `JdbcConnection` read-only behavior**: https://h2database.github.io/javadoc/org/h2/jdbc/JdbcConnection.html