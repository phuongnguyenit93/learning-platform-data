# Phân biệt propagation với isolation và chiến lược khóa trong Spring Transaction Management

> **Spring Framework — Transaction Management → Khóa và đồng thời.** Một transaction có thể được cấu hình đúng `propagation` nhưng vẫn gặp lost update, write skew, deadlock hoặc lock wait. Ngược lại, tăng `isolation` hoặc thêm `SELECT ... FOR UPDATE` không sửa lỗi giao dịch bị tách ngoài ý muốn bởi `REQUIRES_NEW`. Ba khái niệm **propagation**, **isolation** và **chiến lược khóa/concurrency control** giải quyết ba loại câu hỏi khác nhau. Bài học này phân biệt rõ trách nhiệm, mối liên hệ và cách kết hợp an toàn trong Spring Framework, JDBC/JPA và cơ sở dữ liệu quan hệ.

## 1. Ba câu hỏi, ba trục thiết kế độc lập

**Propagation** trả lời:

> Khi một method có giao dịch gọi một method khác, method bên trong **tham gia transaction đang có**, **mở transaction mới**, **tạo savepoint**, hay **chạy ngoài transaction**?

**Isolation** trả lời:

> Trong một physical transaction, các truy vấn có thể **quan sát dữ liệu được thay đổi đồng thời** ra sao, và hệ quản trị cơ sở dữ liệu ngăn những anomaly nào?

**Chiến lược khóa/concurrency control** trả lời:

> Khi nhiều transaction cùng đọc hoặc sửa dữ liệu, làm cách nào **ngăn ghi đè, bảo đảm điều kiện nghiệp vụ và phối hợp truy cập**: SQL atomic update, optimistic version check, row lock, advisory lock, unique constraint hay serializable retry?

Bảng định vị nhanh:

| Trục | Ví dụ API | Điều khiển trực tiếp | Không tự đảm bảo |
| --- | --- | --- | --- |
| **Propagation** | `@Transactional(propagation = Propagation.REQUIRED)` | Quan hệ giữa inner/outer logical scopes và physical transactions | Không tự ngăn lost update, phantom, deadlock hay check business invariant |
| **Isolation** | `@Transactional(isolation = Isolation.READ_COMMITTED)` | Mức độ dữ liệu đồng thời được phép quan sát và các anomaly được DB ngăn theo isolation contract | Không tự tạo transaction độc lập, không chứng minh mọi business race đã được xử lý |
| **Khóa / concurrency strategy** | `SELECT ... FOR UPDATE`, `@Version`, conditional `UPDATE` | Ai được sửa bản ghi nào, khi nào cần chờ/xung đột và cách phát hiện conflict | Không tự thay thế transaction boundary hoặc làm hai databases commit atomic |
| **Rollback rules** *(trục liên quan)* | `rollbackFor`, `noRollbackFor` | Exception nào yêu cầu rollback transaction scope | Không phải propagation, isolation hay lock mode |

Một lựa chọn đúng thường phải kết hợp cả ba trục, ví dụ:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED
)
public void reserveStock(long productId, int amount) {
    // Dùng atomic conditional UPDATE để không bán âm tồn kho.
}
```

Đoạn trên là **fragment**, chưa phải method chạy độc lập. Nó nói rằng use case có transaction phù hợp và muốn isolation `READ_COMMITTED` nếu transaction mới được tạo. **Invariant tồn kho không âm** vẫn phải được bảo vệ bởi điều kiện SQL hoặc một chiến lược khóa/constraint thích hợp; annotation không tự chèn điều kiện đó.

## 2. Ví dụ trực giác: ba yêu cầu khác nhau trên cùng một giao dịch

Giả sử một service giữ đơn hàng và có hai concurrent requests:

```text
Request A                              Request B
---------                              ---------
begin transaction T1                  begin transaction T2
read stock=1                           read stock=1
check stock >= 1                       check stock >= 1
write stock=0                          write stock=0
commit T1                              commit T2
```

Nếu cả hai dựa trên mô hình **đọc trước, rồi ghi giá trị đã tính**, nghiệp vụ có nguy cơ bán vượt khả năng hoặc ghi đè kết quả. Hai methods có thể đều `@Transactional(REQUIRED)` và vẫn gặp race: mỗi request có transaction riêng vì không có caller transaction bao chung **giữa hai requests**.

- Đổi `REQUIRED` sang `REQUIRES_NEW` cho mỗi request **không giúp**: vẫn hai transactions cạnh tranh.
- Đặt isolation mạnh hơn có thể thay đổi snapshot, conflict detection hoặc buộc rollback/retry; **cách chính xác tùy DBMS**.
- Thực hiện **atomic conditional UPDATE** có điều kiện tồn kho còn đủ thường trực tiếp hơn: database kiểm tra điều kiện và sửa dữ liệu như một statement, giúp giới hạn race cho invariant này.
- Nếu nghiệp vụ gồm nhiều rows/điều kiện phức tạp, cần phối hợp locks hoặc serializable transaction + retry hợp lý.

Ví dụ bảo vệ tồn kho bằng một lệnh SQL:

```sql
UPDATE inventory
SET available = available - :amount,
    version = version + 1
WHERE id = :productId
  AND available >= :amount;
```

Đây là **SQL fragment** dùng named parameters (ví dụ `NamedParameterJdbcTemplate`), không thể chạy nguyên văn trực tiếp trong mọi SQL client. Nếu affected rows = 1, tồn kho được trừ; nếu = 0, sản phẩm không có hoặc số lượng không đủ. Cần kiểm tra affected row count và chuyển thành kết quả nghiệp vụ, thay vì mặc nhiên giả định statement đã thành công.

**Phân biệt:** propagation xác định transaction nào chứa UPDATE, isolation ảnh hưởng khả năng quan sát và cạnh tranh với transaction khác, còn điều kiện `available >= :amount` mới chính là **guard cụ thể** của invariant “không trừ quá lượng còn”.

## 3. Propagation: lựa chọn physical transaction, không phải isolation hay lock

Trong Spring, `@Transactional` có default propagation là `Propagation.REQUIRED`.

### 3.1. `REQUIRED`: thường cùng physical transaction

```text
OrderService.place()    @Transactional(REQUIRED) --> physical T1
   |
   +-- InventoryService.reserve() @Transactional(REQUIRED)
           |
           +-- logical scope khác
           +-- thường THAM GIA physical T1
```

Hai logical scopes vẫn có rollback rules và rollback-only status; nhưng nếu cùng physical transaction, inner không thể commit dữ liệu của mình độc lập với outer. Nếu inner đánh dấu transaction rollback-only, outer có thể nhận `UnexpectedRollbackException` khi cố commit.

**Điều không thay đổi:** T1 vẫn phải đối mặt với các transaction T2/T3 từ những requests khác. `REQUIRED` không áp đặt row lock trước mọi SELECT, không bảo đảm serializable execution.

### 3.2. `REQUIRES_NEW`: transaction độc lập không đồng nghĩa tránh concurrency

```text
Outer @Transactional(REQUIRED) --> T1 giữ Connection A, có thể giữ locks
   |
   +-- Inner @Transactional(REQUIRES_NEW)
            |
            +-- suspend context T1
            +-- mở physical T2 trên Connection B
            +-- commit/rollback T2 độc lập
   |
   +-- resume T1
```

Inner có transaction vật lý riêng và có thể đặt isolation riêng; nhưng **T1 không tự nhả lock chỉ vì bị suspend**. Nếu T2 cần row mà T1 đang khóa, T2 có thể chờ lock do chính T1 giữ. Nếu connection pool không còn Connection B, T2 có thể kẹt ở bước mượn connection. Tăng isolation trong T2 không giải quyết hai vấn đề đó.

`REQUIRES_NEW` có thể làm **tăng** nguy cơ lock conflict và connection starvation trong một call chain, đặc biệt khi inner đọc/ghi dữ liệu của outer chưa commit.

### 3.3. `NESTED`: savepoint, không phải level isolation khác

Khi JDBC transaction manager và resource hỗ trợ savepoints, `Propagation.NESTED` cho phép inner tạo savepoint trong **cùng physical transaction**. Rollback inner có thể khôi phục state về savepoint rồi outer tiếp tục. Nó không tạo snapshot/isolation level vật lý mới cho inner.

```text
T1 (READ_COMMITTED)
  +-- update A
  +-- SAVEPOINT s1
  +-- update B
  +-- ROLLBACK TO s1  => update B được hoàn tác
  +-- update C
  +-- COMMIT T1       => update A và C được commit
```

Đây là sơ đồ semantics. Savepoint không thay thế transaction isolation; không phải mọi JPA transaction manager/provider đều hỗ trợ nested transactions theo kiểu này. Khi outer T1 rollback, tất cả thay đổi còn trong T1 đều bị hủy.

### 3.4. `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`

Các mức này chủ yếu xác định contract về **sự hiện diện của transaction**, không được hiểu thành một isolation hoặc lock policy:

| Propagation | Khi caller có transaction | Khi caller không có transaction | Điểm liên quan concurrency |
| --- | --- | --- | --- |
| `SUPPORTS` | Có thể tham gia | Có thể chạy không có physical transaction | Không tự cung cấp snapshot nhất quán nếu không có transaction |
| `MANDATORY` | Bắt buộc tham gia | Ném `IllegalTransactionStateException` | Enforce rằng operation nằm trong boundary của caller |
| `NOT_SUPPORTED` | Suspend transaction của manager rồi chạy ngoài | Chạy ngoài transaction | Nhiều SQL statements có thể autocommit riêng; không có atomicity nhóm |
| `NEVER` | Ném lỗi | Chạy ngoài transaction | Cấm caller có transaction, không tự biến operation thành thread-safe |

Tóm lại: **không chọn propagation để “khử” lost update**. Chọn propagation theo ranh giới nghiệp vụ: việc nào cần commit/rollback cùng nhau, việc nào độc lập, việc nào bắt buộc có caller-owned transaction.

## 4. Isolation: visibility và concurrency anomalies trong physical transaction

`Isolation` của Spring có các giá trị: `DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`. Chúng được ánh xạ theo JDBC/transaction manager đến mức isolation của database nếu supported.

| Isolation | Ý nghĩa khái quát | Lưu ý quan trọng |
| --- | --- | --- |
| `DEFAULT` *(default Spring)* | Giữ mức isolation mặc định của underlying DB/resource | **Không** có nghĩa “không isolation”; giá trị DB mặc định có thể khác nhau |
| `READ_UNCOMMITTED` | Chuẩn SQL cho phép dirty reads | Nhiều DBMS không hỗ trợ dirty read thực sự hoặc ánh xạ sang mức mạnh hơn |
| `READ_COMMITTED` | Một statement không đọc dữ liệu uncommitted của transactions khác | Non-repeatable read/phantom/logic race vẫn có thể xảy ra |
| `REPEATABLE_READ` | Bảo đảm mạnh hơn cho việc đọc lặp lại một row theo contract chuẩn | Hành vi phantom, snapshot, write conflicts khác nhau theo DBMS |
| `SERIALIZABLE` | Kết quả committed transactions tương đương một thứ tự thực thi tuần tự | Có thể phát sinh serialization failures/deadlocks cần retry toàn bộ transaction; không phải “không cần kiểm tra lỗi” |

Các mức isolation trong SQL standard định nghĩa **giới hạn về các anomaly có thể xảy ra**, còn database có thể cung cấp bảo đảm mạnh hơn. Ví dụ PostgreSQL xử lý `READ UNCOMMITTED` tương đương `READ COMMITTED` và triển khai `REPEATABLE READ` với đặc tính mạnh hơn bảng ví dụ SQL chuẩn về phantom reads.

### 4.1. Dirty read

`T1` ghi `balance=5` nhưng chưa commit. Nếu `T2` đọc được giá trị đó rồi T1 rollback, T2 đã đọc dữ liệu **chưa từng được commit**.

```text
T1: UPDATE balance=5 --- chờ --- ROLLBACK
T2:                SELECT balance -> 5 (dirty read)
```

Trong những DBMS hỗ trợ dirty reads, `READ_UNCOMMITTED` có thể cho phép điều này; `READ_COMMITTED` không được phép dirty read theo contract. Nhưng không nên suy luận chỉ từ annotation nếu đang dùng DB khác/manager khác hoặc query chạy ngoài transaction.

### 4.2. Non-repeatable read

T1 đọc một row hai lần; giữa hai lần đó, T2 commit một thay đổi. T1 có thể thấy hai giá trị khác nhau.

```text
T1: SELECT price -> 100
T2: UPDATE price=110; COMMIT
T1: SELECT price -> 110
```

`READ_COMMITTED` có thể cho phép điều này, vì mỗi statement chỉ cần nhìn dữ liệu đã commit ở thời điểm statement tương ứng. Một số use cases cần snapshot ổn định hơn hoặc khóa row.

### 4.3. Phantom read

T1 chạy cùng predicate hai lần; T2 insert/delete các rows matching predicate ở giữa. Số lượng/kết quả rows có thể thay đổi.

```text
T1: SELECT COUNT(*) FROM bookings WHERE room_id=7 -> 2
T2: INSERT INTO bookings(room_id, ...) VALUES(7, ...); COMMIT
T1: SELECT COUNT(*) FROM bookings WHERE room_id=7 -> 3
```

`REPEATABLE_READ` theo chuẩn SQL không nhất thiết ngăn mọi phantom; implementation MVCC, range/predicate locks có thể ngăn hoặc xử lý khác. PostgreSQL `REPEATABLE READ` không cho phantom read như mô tả trong tài liệu chính thức, nhưng không dùng kết luận đó cho mọi DBMS.

### 4.4. Lost update

Hai transactions đọc cùng giá trị rồi cùng tính giá trị mới trong application code:

```text
Initial stock=10

T1: SELECT stock -> 10
T2: SELECT stock -> 10
T1: UPDATE stock=8; COMMIT
T2: UPDATE stock=9; COMMIT
Result=9 (mất thay đổi của T1)
```

Đây là **rủi ro** của read-modify-write không được bảo vệ đúng. Chính xác transaction nào bị block/abort, và kết quả có thể xảy ra không, phụ thuộc isolation/DBMS/query shape. Đặc biệt, một số DBMS ở isolation mạnh hơn có conflict detection. Không coi timeline này là hành vi tất yếu của mọi `READ_COMMITTED` implementation.

Có nhiều cách xử lý: atomic `UPDATE stock=stock-... WHERE...`, optimistic version, pessimistic lock hoặc serializable retry tùy invariant.

### 4.5. Write skew

Hai transactions đọc một tập rows rồi ghi vào **những rows khác nhau**, khiến invariant toàn cục bị vi phạm dù không có hai UPDATE chạm cùng row.

Ví dụ hai bác sĩ trực: quy tắc luôn phải có ít nhất một bác sĩ on-call. Cả T1 và T2 cùng thấy “người kia vẫn trực”, rồi mỗi bên tự đặt mình off-call; trạng thái cuối là không ai trực.

Chỉ kiểm tra `@Version` trên row **mỗi bên tự sửa** có thể không bắt được write skew vì hai writes ở hai rows khác nhau. Cần thiết kế invariant bằng constraint/materialized lock, transactional locking of a shared guard row, serializable transaction + retry hoặc một cơ chế coordinator phù hợp.

**Lưu ý:** isolation mạnh hơn không thay thế việc mô tả invariant. Để biết cần khóa row hay predicate, phải hiểu tất cả rows và conditions quyết định nghiệp vụ.

## 5. Spring áp dụng isolation khi nào?

Điểm thường gây lỗi cấu hình: **isolation được đặt cho một physical transaction mới**, không phải tự nâng cấp isolation của transaction đã tồn tại khi inner method `REQUIRED` tham gia.

Ví dụ:

```java
@Service
class OuterService {
    private final InnerService inner;

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED
    )
    public void outer() {
        inner.inner();  // Cross-bean call qua Spring proxy.
    }
}

@Service
class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // Thường vẫn chạy trong physical T1 READ_COMMITTED của outer.
    }
}
```

Đây là fragment: cần constructors/imports và beans. Với `AbstractPlatformTransactionManager` ở default lenient behavior, inner `REQUIRED` tham gia T1 và local isolation declaration của inner thường **bị bỏ qua**. Nó không bí mật tạo `SERIALIZABLE` snapshot chỉ cho vài SQL của inner.

### 5.1. `validateExistingTransaction` để không bỏ qua mismatch một cách thầm lặng

Nếu muốn **phát hiện lỗi cấu hình** khi inner yêu cầu isolation khác transaction ngoài:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager tx = new JdbcTransactionManager(dataSource);
    tx.setValidateExistingTransaction(true);
    return tx;
}
```

Fragment trong Spring `@Configuration`. Trong trường hợp method tham gia T1 và khai báo isolation không tương thích, manager có thể ném `IllegalTransactionStateException` thay vì cho chạy dưới isolation ngoài. Cấu hình này cũng có kiểm tra read-only mismatch phù hợp.

**Không sửa mismatch bằng cách tự đổi inner sang `REQUIRES_NEW`** nếu nghiệp vụ cần atomic cùng outer. `REQUIRES_NEW` tạo transaction khác, thay đổi hoàn toàn kết quả commit/rollback. Cách sửa chuẩn là đặt isolation tại transaction owner, hoặc thiết kế boundary cho đúng yêu cầu.

### 5.2. Khi REQUIRES_NEW, inner có thể đặt isolation riêng

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void independentStep() {
    // T2 thực sự có boundary mới và yêu cầu SERIALIZABLE.
}
```

Fragment. Vì có T2 độc lập, isolation mới có thể được áp dụng theo khả năng của manager/driver. Nhưng cũng vì có T2, dữ liệu T1 chưa commit **không tự nhìn thấy được** từ T2; một insert có foreign key đến row mới ở T1 có thể fail hoặc block.

### 5.3. Khi NESTED, không có isolation vật lý thứ hai

Nếu inner dùng savepoint trong T1, nó phải tuân theo isolation đã thiết lập cho T1; một savepoint không phải công cụ đổi isolation giữa transaction. Khi cần hai isolation levels thực sự khác nhau, phải xem việc tách physical transaction có phù hợp invariant và resource usage hay không.

### 5.4. DEFAULT không có nghĩa READ_COMMITTED

`Isolation.DEFAULT` yêu cầu dùng mặc định underlying transaction system. PostgreSQL thường mặc định `READ COMMITTED`; DBMS/connection khác có thể dùng mức khác. Ngay cả khi Spring `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` trả `null`, physical JDBC connection vẫn có isolation. Muốn xác minh thực tế, hỏi `Connection.getTransactionIsolation()` trên **connection đang tham gia transaction** hoặc đọc transaction settings của database.

## 6. Locking: đối tượng khác với isolation

**Pessimistic locking**: lấy lock để ngăn/tuần tự hóa các thao tác cạnh tranh trước hoặc trong lúc sửa, thường bằng `SELECT ... FOR UPDATE` hoặc JPA `LockModeType.PESSIMISTIC_WRITE`. Nếu transaction khác giữ lock không tương thích, caller có thể phải chờ, timeout hoặc bị DB đánh dấu deadlock victim.

**Optimistic locking**: không giữ exclusive lock trong suốt giai đoạn đọc; khi ghi, so khớp version/điều kiện mong đợi. Nếu dữ liệu đã thay đổi, phát hiện conflict rồi từ chối hoặc retry với snapshot mới. JPA hỗ trợ `@Version`, JDBC có thể dùng `WHERE version = ?`.

**Atomic conditional write**: tránh mô hình đọc-đổi-ghi trong application bằng một statement có guard: `UPDATE ... WHERE available >= amount`, kiểm tra affected rows. Đây có thể là lựa chọn đơn giản nhất cho một invariant cục bộ của một row.

**Database constraints**: `UNIQUE`, `CHECK`, `FOREIGN KEY` được engine enforce, chống vi phạm invariant kể cả khi nhiều requests hoặc nhiều services cùng ghi. Tuy nhiên constraints không thể mô tả tất cả invariants đa row.

**Serializable + retry**: cho DBMS kiểm soát transaction schedule theo semantics serializable. Ứng dụng phải xử lý serialization failure bằng retry **toàn bộ transaction từ đầu**, không chỉ chạy lại một SQL trong transaction đã bị abort.

Không có một chiến lược tối ưu cho mọi workload. Đánh giá tỷ lệ ghi xung đột, độ dài transaction, kích thước dữ liệu, latency, correctness và khả năng DB/driver.

## 7. So sánh optimistic và pessimistic locking theo quyết định nghiệp vụ

| Tiêu chí | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Khi phát hiện xung đột | Thường ở bước update/flush/commit khi version không khớp | Khi cố lấy lock trước hoặc khi ghi |
| Có giữ row lock xuyên suốt thời gian đọc/người dùng xử lý? | Thường không giữ lock đọc lâu | Có thể giữ lock trong physical transaction đến commit/rollback |
| Kết quả khi xung đột | Update 0 rows, `OptimisticLockException` hoặc tương đương; cần reload/retry/response | Chờ lock, timeout, deadlock detection hoặc fail-fast theo DB syntax |
| Phù hợp khi | Xung đột thấp, web forms, nhiều reads, thời gian người dùng suy nghĩ dài | Xung đột cao, bắt buộc điều phối thứ tự ghi, cần đọc dữ liệu rồi quyết định dưới lock |
| Rủi ro | Retry storm, stale data, version không bao hết multi-row invariant | Lock waits, deadlocks, giảm throughput, connection bị giữ lâu |
| Quan hệ với propagation | Vẫn cần transaction boundary cho writes; không tự đổi REQUIRED/REQUIRES_NEW | Lock sở hữu bởi physical transaction, không tự nhả khi Spring suspend outer |
| Quan hệ với isolation | Isolation có thể làm conflict xuất hiện sớm/muộn và thay đổi visibility | Isolation/DB engine ảnh hưởng loại locks, lock compatibility và query behavior |

Điểm chung: **khóa không loại bỏ nhu cầu thiết kế transaction scope**. Nếu method gọi JPA `@Lock` mà không có actual transaction ở nơi cần giữ lock, semantics bảo vệ có thể không đáp ứng ý định; nếu lock được lấy ở T1 thì chỉ dùng được cho những thao tác thực hiện trong T1 theo DB rules.

## 8. Pessimistic locking trong JDBC: SELECT ... FOR UPDATE

Trong service Spring JDBC:

```java
@Transactional(propagation = Propagation.REQUIRED)
public void transfer(long fromId, long toId, long amount) {
    // Fragment: tên bảng/columns và xử lý kiểm tra cần khớp schema.
    Long current = jdbc.queryForObject(
        "SELECT balance FROM accounts WHERE id = ? FOR UPDATE",
        Long.class,
        fromId
    );

    if (current == null || current < amount) {
        throw new IllegalArgumentException("insufficient balance");
    }

    jdbc.update(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        amount, fromId
    );
    jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        amount, toId
    );
}
```

Đây là **fragment minh họa**, không phải ứng dụng độc lập. Mã chỉ khóa row nguồn trong ví dụ; với transfer thực tế nên xác định toàn bộ rows cần khóa, **thứ tự khóa cố định** (ví dụ theo account id), validation và concurrency strategy. Không coi nó là hoàn chỉnh chỉ vì có `FOR UPDATE`.

Khi `SELECT ... FOR UPDATE` được DB hỗ trợ và có transaction thích hợp, row lock thường được giữ đến khi physical transaction hoàn tất. Nếu T2 khác cần lock không tương thích, nó có thể chờ.

### 8.1. NOWAIT và SKIP LOCKED có thật sự thay đổi gì?

Một số DBMS hỗ trợ biến thể:

```sql
SELECT id FROM work_items
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
```

Đây là **SQL mang tính DB-specific**, đặc biệt hữu ích cho nhiều worker cùng lấy job từ queue. `SKIP LOCKED` có thể giúp worker bỏ qua rows đang bị khóa thay vì đứng chờ, nhưng kết quả là một view **không đầy đủ ở thời điểm đọc**. Không dùng nó để đảm bảo “không còn job tồn đọng” trong nghiệp vụ cần quét đầy đủ.

`NOWAIT` thường yêu cầu lỗi ngay nếu không lấy được lock thay vì chờ, nhưng cú pháp và khả năng hỗ trợ khác giữa DBMS. Không kết luận Spring `Propagation` nào tự bật `NOWAIT` hoặc `SKIP LOCKED`.

### 8.2. Không giữ lock xuyên qua thao tác chậm

```java
@Transactional
public void badExample() {
    lockCustomerRow();
    callExternalApi();  // HTTP có thể mất vài giây.
    updateCustomer();
}
```

Fragment này kéo dài thời gian giữ lock và connection. Dưới concurrency cao, những requests khác sẽ chờ hoặc timeout. Nếu HTTP API cần phản hồi trước quyết định ghi, cân nhắc chuyển ra ngoài boundary hoặc dùng optimistic version để revalidate trước khi commit.

## 9. Optimistic locking với version column

### 9.1. JDBC pattern

Một bảng có `version`:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    available INT NOT NULL,
    version INT NOT NULL
);
```

Đọc một snapshot:

```sql
SELECT available, version
FROM inventory
WHERE id = 42;
```

Khi ghi, dùng version đã đọc làm điều kiện:

```sql
UPDATE inventory
SET available = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :previousVersion;
```

Nếu affected rows = 0, dữ liệu có thể đã thay đổi hoặc row không tồn tại. Đừng tự coi update 0 là thành công; ứng dụng nên báo xung đột, reload/retry có giới hạn hoặc trả HTTP 409 tùy use case.

**Chú ý:** chỉ version check một row không tự bảo vệ invariant phụ thuộc nhiều rows. Đồng thời phải tránh đường ghi khác bỏ qua version check hoặc tự ghi đè `version` bằng giá trị stale.

### 9.2. JPA `@Version`

Với Jakarta Persistence, có thể khai báo:

```java
@Entity
class Product {
    @Id
    private Long id;

    @Version
    private long version;

    private int available;
}
```

Đây là **JPA fragment**, cần imports `jakarta.persistence.*`, constructors, accessors và mapping phù hợp. Provider dùng version để phát hiện stale updates đối với managed entity, thường ném `OptimisticLockException` hoặc exception được Spring translate khi flush/commit.

**Lưu ý:** các bulk JPQL updates hoặc native SQL updates có thể không tự tham gia `@Version` giống thao tác entity bình thường; cần thiết kế version handling/where clause tương ứng. Khi exception từ JPA khiến transaction rollback-only, không retry trong cùng một transaction đã thất bại.

### 9.3. Spring Data JPA `@Lock` khác `@Version`

Một repository query có thể yêu cầu pessimistic lock:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findByIdForUpdate(@Param("id") Long id);
}
```

Đây là **fragment** cần `org.springframework.data.jpa.repository.*`, `jakarta.persistence.LockModeType` và `org.springframework.data.repository.query.Param`. Nó không biên dịch chỉ với Spring JDBC demo ở dưới; phải có Spring Data JPA/JPA entity.

`@Lock` chọn JPA lock mode cho query; `@Version` là optimistic version metadata trên entity. Cả hai không phải `propagation` và không tự tạo transaction boundary khi gọi repository qua mọi đường.

## 10. Atomic conditional UPDATE: nhiều khi ít phức tạp hơn hai kiểu lock trên

Nếu invariant là “số lượng không âm”, một UPDATE có predicate kiểm tra điều kiện có thể là biện pháp rất hiệu quả:

```java
@Transactional
public void reserveStock(long productId, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    int updated = jdbc.update("""
        UPDATE inventory
        SET available = available - ?,
            version = version + 1
        WHERE id = ? AND available >= ?
        """, amount, productId, amount);

    if (updated != 1) {
        throw new IllegalStateException("insufficient stock");
    }
}
```

Fragment cần field `JdbcTemplate jdbc` và Spring bean được intercept. SQL là **read-modify-write trong database engine**, không phải Java read -> compute -> blind update. Với transaction/DB support thích hợp, concurrent updates phải phối hợp ghi cùng row; predicate được đánh giá theo semantics của database statement. Dưới `READ_COMMITTED` của H2/PostgreSQL, pattern này thường ngăn bán âm tồn kho cho **một row**.

Không dùng kết luận này để suy rộng sang invariant đa row (ví dụ “tối đa 100 booking trên nhiều partitions”): cần thêm unique/constraint, guard row, lock hoặc serializable transaction.

**Không quên affected row count.** Khi row count=0, code phải xử lý out-of-stock hoặc race một cách có chủ đích; nếu lặng lẽ bỏ qua, nghiệp vụ có thể thông báo success nhưng không trừ được tồn kho.

## 11. Khi propagation và isolation cùng có mặt trong một call chain

Xét ba methods:

```java
// Tạo T1 nếu chưa có, yêu cầu READ_COMMITTED.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED
)
public void placeOrder() {
    inventoryService.reserve();       // REQUIRED + SERIALIZABLE khai báo riêng
    auditService.recordIndependent(); // REQUIRES_NEW + SERIALIZABLE
}
```

Đây là fragment, giả định hai services là Spring-managed beans được inject. Vẽ kết quả:

```text
placeOrder(): REQUIRED + READ_COMMITTED
     |
     +--> physical T1: READ_COMMITTED
     |
     +--> inventory.reserve(): REQUIRED + SERIALIZABLE
     |       +-- joins T1
     |       +-- isolation hiện hành vẫn T1 (READ_COMMITTED)
     |           trừ khi manager validateExistingTransaction phát hiện mismatch
     |
     +--> audit.recordIndependent(): REQUIRES_NEW + SERIALIZABLE
             +-- physical T2 mới: yêu cầu SERIALIZABLE
             +-- T1 vẫn tồn tại và có thể giữ locks/connection
             +-- T2 commit/rollback độc lập
```

Bảng:

| Inner method | Có T1 bên ngoài? | Physical transaction | Isolation hiệu lực thường thấy | Điều gì không được suy ra |
| --- | --- | --- | --- | --- |
| `REQUIRED, isolation=SERIALIZABLE` | Có, T1 READ_COMMITTED | Tham gia T1 | `READ_COMMITTED` của outer (nếu manager lenient) | Không tự nâng inner lên SERIALIZABLE |
| `REQUIRES_NEW, isolation=SERIALIZABLE` | Có | Mở T2 | `SERIALIZABLE` nếu supported | Không có nghĩa T2 đọc được uncommitted T1 hoặc không cần thêm connection |
| `NESTED` | Có | Cùng T1/savepoint | Cùng isolation của T1 | Không có snapshot isolation mới |
| `REQUIRED, isolation=SERIALIZABLE` | Không | Mở mới | `SERIALIZABLE` nếu supported | Không tự động khóa row trước khi đọc nếu SQL không yêu cầu |
| `SUPPORTS` | Không | Có thể không có physical transaction | Theo nontransactional/default resource behavior | Không có contract snapshot transaction |
| `NOT_SUPPORTED` | Có | Không tham gia T1; T1 suspend | Ngoài transaction của manager | Không bảo đảm atomicity giữa các SQL statements |

Đặc biệt, `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` phản ánh isolation mà Spring đã thiết lập vào transaction context; `null` khi không có giá trị được Spring khai báo riêng **không có nghĩa DB đang ở isolation “NONE”**. Với JDBC có thể hỏi physical connection khi cần.

## 12. Java 17+ runnable demo: chứng minh isolation của REQUIRED và REQUIRES_NEW

Ví dụ hoàn chỉnh dưới đây dùng:

- JDK 17+ và Maven.
- Spring Framework 6.2.8, Spring JDBC và H2 2.3.232.
- `JdbcTransactionManager` quản lý một datasource.
- `@EnableTransactionManagement` để kích hoạt proxy transaction advice.
- `TransactionSynchronizationManager` để **in isolation context** bên trong các scopes.
- **Atomic conditional update** và **optimistic version check** để minh họa hai strategies chống ghi đè, độc lập với propagation.

### 12.1. Tạo cấu trúc thư mục

```text
propagation-isolation-lock-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── PropagationIsolationLockDemo.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>propagation-isolation-lock-demo</artifactId>
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
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <version>3.5.0</version>
                <artifactId>exec-maven-plugin</artifactId>
                <configuration>
                    <mainClass>dev.learning.PropagationIsolationLockDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. `src/main/java/dev/learning/PropagationIsolationLockDemo.java`

```java
package dev.learning;

import java.sql.Connection;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class PropagationIsolationLockDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:iso_lock;DB_CLOSE_DELAY=-1");
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
            // Mặc định lenient: joining REQUIRED dùng isolation của outer.
            return new JdbcTransactionManager(ds);
        }

        @Bean
        InventoryService inventoryService(JdbcTemplate jdbc) {
            return new InventoryService(jdbc);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(AuditService audit) {
            return new OrderService(audit);
        }
    }

    private record Stock(int available, int version) {}

    private static String isolationName() {
        Integer level =
                TransactionSynchronizationManager
                        .getCurrentTransactionIsolationLevel();

        if (level == null) {
            return "DEFAULT_OR_UNSPECIFIED";
        }

        return switch (level) {
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_READ_UNCOMMITTED -> "READ_UNCOMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ -> "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "OTHER";
        };
    }

    public static class InventoryService {
        private final JdbcTemplate jdbc;

        public InventoryService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Propagation lựa chọn boundary. Guard SQL bảo vệ invariant.
        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED
        )
        public void reserve(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }

            int changed = jdbc.update("""
                UPDATE inventory
                SET available = available - ?,
                    version = version + 1
                WHERE id = 1 AND available >= ?
                """, amount, amount);

            if (changed != 1) {
                throw new IllegalStateException("insufficient stock");
            }

            System.out.println(
                    "reserve.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
        }

        // Optimistic locking giản lược: so khớp version ngay lúc ghi.
        @Transactional(propagation = Propagation.REQUIRED)
        public boolean reserveIfVersion(
                int expectedVersion, int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }

            int changed = jdbc.update("""
                UPDATE inventory
                SET available = available - ?,
                    version = version + 1
                WHERE id = 1
                  AND version = ?
                  AND available >= ?
                """, amount, expectedVersion, amount);

            return changed == 1;
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        // Chỉ tạo logical scope mới; đang tham gia T1 READ_COMMITTED.
        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE
        )
        public void joined() {
            System.out.println(
                    "joined.isolation=" + isolationName());
        }

        // Một physical transaction T2 mới, có isolation riêng.
        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            isolation = Isolation.SERIALIZABLE
        )
        public void independent() {
            System.out.println(
                    "new.isolation=" + isolationName());
            jdbc.update("""
                INSERT INTO audit_events(id, detail) VALUES(1, 'T2 committed')
                """);
        }
    }

    public static class OrderService {
        private final AuditService audit;

        public OrderService(AuditService audit) {
            this.audit = audit;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED
        )
        public void demonstrateIsolation() {
            System.out.println(
                    "outer.isolation=" + isolationName());

            // Gọi qua bean khác để Spring proxy intercept từng method.
            audit.joined();
            audit.independent();

            System.out.println(
                    "outer.after.isolation=" + isolationName());
        }
    }

    private static Stock stock(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT available, version FROM inventory WHERE id = 1",
                (rs, rowNum) -> new Stock(
                        rs.getInt("available"),
                        rs.getInt("version")));
    }

    private static void showStock(
            String label, JdbcTemplate jdbc) {
        Stock value = stock(jdbc);
        System.out.printf(
                "%s.qty=%d version=%d%n",
                label, value.available(), value.version());
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                CREATE TABLE inventory (
                    id INT PRIMARY KEY,
                    available INT NOT NULL,
                    version INT NOT NULL
                )
                """);
            jdbc.execute(
                    "INSERT INTO inventory(id, available, version) "
                    + "VALUES(1, 10, 0)");

            jdbc.execute("""
                CREATE TABLE audit_events (
                    id INT PRIMARY KEY,
                    detail VARCHAR(80) NOT NULL
                )
                """);

            InventoryService inventory =
                    context.getBean(InventoryService.class);

            inventory.reserve(3);
            showStock("afterReserve", jdbc);

            try {
                inventory.reserve(10);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "reserve.failure=" + expected.getMessage());
            }
            showStock("afterRejected", jdbc);

            System.out.println(
                    "optimistic.stale="
                    + inventory.reserveIfVersion(0, 1));

            System.out.println(
                    "optimistic.fresh="
                    + inventory.reserveIfVersion(1, 1));
            showStock("afterOptimistic", jdbc);

            context.getBean(OrderService.class)
                    .demonstrateIsolation();

            Integer audits = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_events",
                    Integer.class);
            System.out.println("audit.count=" + audits);
        }
    }
}
```

### 12.4. Biên dịch và chạy

Yêu cầu JDK 17+, Maven và Internet cho lần đầu tải dependencies. Trong thư mục `propagation-isolation-lock-demo`:

```bash
mvn -q clean compile exec:java
```

Các dòng **do chính chương trình in ra** theo thứ tự kỳ vọng, bỏ qua log từ Maven hoặc Spring:

```text
reserve.active=true
afterReserve.qty=7 version=1
reserve.failure=insufficient stock
afterRejected.qty=7 version=1
optimistic.stale=false
optimistic.fresh=true
afterOptimistic.qty=6 version=2
outer.isolation=READ_COMMITTED
joined.isolation=READ_COMMITTED
new.isolation=SERIALIZABLE
outer.after.isolation=READ_COMMITTED
audit.count=1
```

### 12.5. Vì sao kết quả này minh họa đủ ba trục?

**Propagation:** `inventory.reserve` chạy một `REQUIRED` transaction; `audit.joined` được intercept trong T1 và tham gia physical T1 dù annotation khai báo `SERIALIZABLE`; `audit.independent` bắt đầu T2 nhờ `REQUIRES_NEW` và dùng transaction isolation riêng.

**Isolation:** `outer` khai báo `READ_COMMITTED` cho T1, nên `joined.isolation=READ_COMMITTED`. `REQUIRED` của inner **không nâng** T1 lên SERIALIZABLE. `REQUIRES_NEW` tạo T2, nên `new.isolation=SERIALIZABLE` khi H2/JDBC manager hỗ trợ. Khi T2 kết thúc, outer resume với isolation context của T1: `READ_COMMITTED`.

**Concurrency strategy:** `reserve(3)` giảm từ 10 xuống 7 bằng một atomic SQL UPDATE với predicate guard. `reserve(10)` không cập nhật được hàng và ném business exception; trạng thái vẫn 7. `reserveIfVersion(0,1)` là một stale version check (version hiện là 1) nên trả false. `reserveIfVersion(1,1)` cập nhật được hàng, quantity giảm xuống 6, version tăng thành 2.

**Giới hạn cần biết:** Demo chạy tuần tự, nên nó minh họa correctness của conditional update và version predicate nhưng **chưa chứng minh throughput/lock waits dưới nhiều threads**. Để xác nhận hành vi concurrency phải chạy integration tests với ít nhất hai transactions trên các connections khác nhau. Những dòng stdout trên được suy luận theo APIs và H2/Spring configuration đã nêu; kết quả thực nghiệm cần kiểm tra bằng Maven trong môi trường có JDK.

### 12.6. Thử nghiệm tự học

**Thử A — Bật `validateExistingTransaction=true` trong manager.** Với outer T1 `READ_COMMITTED` gọi `audit.joined` yêu cầu `SERIALIZABLE`, manager sẽ kiểm tra mismatch. Lời gọi có thể ném `IllegalTransactionStateException` trước khi đi vào body của `joined`. Kết quả này cho thấy yêu cầu isolation của inner không tự nâng cấp existing physical T1.

**Thử B — Đổi `audit.joined` từ `REQUIRED` sang `REQUIRES_NEW`.** Khi đã có outer T1, method được phép tạo T2 với isolation riêng. Nhưng lúc này nó **không còn cùng atomic unit** với outer và có thể cần thêm connection; đây là thay đổi semantics, không phải một cách sửa mismatch vô điều kiện.

**Thử C — Loại `AND available >= ?` trong `reserve`.** Với amount=10 sau khi available=7, có thể cập nhật thành available=-3 vì đã bỏ guard. `@Transactional(REQUIRED, isolation=READ_COMMITTED)` tự nó không enforce invariant tồn kho không âm.

**Thử D — Bỏ version predicate trong `reserveIfVersion`.** Stale client không còn phát hiện concurrent modification; update có thể ghi đè thay đổi khác. Điều này cũng chứng minh `@Transactional` không đồng nghĩa optimistic locking.

**Thử E — Dùng real concurrency test.** Cho hai threads mượn hai JDBC connections, đồng bộ thời điểm đọc bằng `CountDownLatch` và cố cập nhật cùng row bằng version predicate. Đảm bảo test có timeout để không treo; kết quả chính xác phụ thuộc DB lock/isolation, nhưng **không được chấp nhận hai writes sử dụng cùng expected version đều thành công** khi câu `UPDATE ... WHERE version=?` được implement đúng trên một row.

## 13. Isolation khác lock khi REQUIRES_NEW bị chặn

Một antipattern trong service:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void outer() {
    jdbc.update(
        "UPDATE accounts SET balance = balance - 5 WHERE id = 1"
    ); // T1 giữ row lock.

    auditService.writeNewTransaction(); // T2 truy cập cùng row.
}

@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void writeNewTransaction() {
    jdbc.update(
        "UPDATE accounts SET audited = TRUE WHERE id = 1"
    );
}
```

Đây là **fragment**, và để inner được intercept phải nằm trên bean khác được inject qua Spring proxy. Nếu T1 đang giữ exclusive lock trên row `id=1`, T2 có connection khác và có thể đứng chờ lock. `SERIALIZABLE` của T2 không giúp nó “đi xuyên qua” lock của T1. T1 bị suspend ở tầng Spring và không thể commit trước khi inner trả về, nên dễ xảy ra lock timeout hoặc bế tắc chờ tài nguyên.

Cách sửa phải dựa trên nghiệp vụ:

- Hai updates phải atomic cùng nhau? Dùng một physical transaction `REQUIRED`, cân nhắc cùng một set of locks.
- Audit cần commit riêng dù outer rollback? Không cho inner truy cập dữ liệu mà outer đang khóa/chưa commit; có thể ghi event độc lập vào bảng không có liên hệ khóa hoặc thiết kế outbox/saga thích hợp.
- Outer đang giữ lock quá lâu? Rút ngắn transaction; đưa HTTP/CPU work ra ngoài ranh giới.
- Database deadlock theo nhiều requests? Thiết lập lock order nhất quán, lock timeout, retry toàn bộ transaction khi DB thông báo retryable failure.
- Pool cạn vì inner cần connection mới? Sizing pool theo peak active outer/inner connections và tính thêm concurrency; không chỉ tăng `connectionTimeout`.

**Tăng isolation không thay thế thay đổi lock topology**, và tăng pool không làm row lock của T1 biến mất.

## 14. JPA persistence context làm vấn đề khó quan sát hơn

Khi dùng `JpaTransactionManager`, một transaction thường gắn với `EntityManager`/persistence context. Những thay đổi entity chưa flush hoặc đã flush nhưng **chưa commit** không nhất thiết hiển thị với transaction khác. Nếu T2 của `REQUIRES_NEW` cố đọc entity vừa tạo bởi T1:

- T2 có thể không thấy row.
- Nếu chạm foreign key/index, T2 có thể chờ hoặc báo lỗi.
- Nếu dùng lock mode, khả năng lấy lock thuộc transaction/resource riêng của T2.
- Khi T2 commit rồi T1 resume, persistence context của T1 có thể đang giữ entities với dữ liệu cũ, cần chiến lược refresh/clear phù hợp khi nghiệp vụ dựa vào dữ liệu mới.

`Isolation.SERIALIZABLE` không làm hai persistence contexts chia sẻ uncommitted state. `REQUIRES_NEW` thay đổi physical transaction scope, không tự đồng bộ cache giữa JPA contexts.

Trong JPA, `@Version` thường thuận tiện cho optimistic locking. `@Lock(LockModeType.PESSIMISTIC_WRITE)` phù hợp khi cần lấy DB lock có chủ đích. Cần xem provider/DB hỗ trợ, thời điểm flush và exception translation.

## 15. Chiến lược khóa cho các use cases phổ biến

| Use case | Invariant/cạnh tranh | Transaction boundary thường phù hợp | Isolation / locking strategy tham khảo |
| --- | --- | --- | --- |
| Trừ stock cho một product row | Không âm, không oversell | `REQUIRED` cho toàn bộ đặt hàng | Atomic `UPDATE ... WHERE available >= ?`, kiểm tra rows affected; hoặc row lock/`@Version` |
| Chuyển tiền hai tài khoản | Tổng tiền nhất quán; không commit nửa giao dịch | Một `REQUIRED` outer, helpers có thể `MANDATORY` | Lock hai accounts theo cùng order, cập nhật cùng transaction, constraints và retry có kiểm soát |
| User chỉnh form lưu sau vài phút | Không ghi đè thay đổi của người khác | Một transaction ngắn lúc save | `@Version`/version predicate; báo conflict và yêu cầu merge |
| Worker lấy một job chưa xử lý | Không nhiều workers nhận cùng job | Mỗi claim trong transaction ngắn | `FOR UPDATE SKIP LOCKED` nếu DB hỗ trợ, hoặc atomic claim update; lease + idempotency |
| Đặt booking không trùng room/time | Không có overlap | `REQUIRED` cho ghi booking | Unique/exclusion constraint, guard row hoặc serializable với retry; chỉ lock một booking row có thể chưa đủ |
| Ghi audit cho một lần thử thất bại | Audit tồn tại khi outer rollback | Cân nhắc `REQUIRES_NEW` thật sự độc lập | Tránh lock/foreign key tới uncommitted outer, sizing pool, idempotency |
| Ghi event cho order đã commit | Event không được nói về order rollback | Outbox ghi trong `REQUIRED` với order | DB transaction + outbox publisher sau commit; tránh event riêng commit sớm |
| Tổng hợp báo cáo nhiều SELECT | Cần snapshot nhất quán xuyên queries? | Boundary đọc phù hợp | Isolation/snapshot theo DBMS, tránh lock dài; `readOnly` không thay thế isolation |
| Cập nhật invariant trên nhiều rows | Không write skew | `REQUIRED` cho whole use case | Serializable + retry, shared guard lock hoặc constraint/materialized invariant |
| Import có thể bỏ qua nhóm lỗi | Partial rollback nhóm nhưng tổng job atomic | `NESTED`/savepoint nếu hỗ trợ | Isolation outer giữ nguyên; savepoint không phải lock mode |

Lưu ý “thường phù hợp” không phải lệnh bắt buộc: với từng DBMS, transaction manager, workload và chính sách nghiệp vụ, cần integration tests xác nhận lựa chọn.

## 16. Quy trình chọn thiết kế đúng: hỏi theo thứ tự

### Bước 1 — định nghĩa invariant và data ownership

Viết rõ dữ liệu nào **bắt buộc cùng commit/rollback**, dữ liệu nào có thể độc lập, và điều gì **không bao giờ được xảy ra** dưới concurrent requests.

Ví dụ:

> “Không được xác nhận hai booking cùng một phòng trong cùng khoảng thời gian; việc ghi lịch sử attempt có thể tồn tại dù booking thất bại.”

Câu đầu là concurrency invariant; câu sau là transaction independence. Có thể cần **hai giải pháp** thay vì một annotation.

### Bước 2 — chọn transaction owner và propagation

- Các updates của một use case cần all-or-nothing: outer `REQUIRED`; helpers tham gia, có thể `MANDATORY` để enforce caller.
- Inner cần commit độc lập thật sự: cân nhắc `REQUIRES_NEW`, kiểm tra data visibility và resource budget.
- Muốn rollback một phần bên trong cùng transaction: `NESTED` với savepoint khi manager hỗ trợ.
- Operation hợp lệ không có transaction: xét `SUPPORTS` hoặc `NOT_SUPPORTED` theo contract, không dùng để né lỗi.
- Cấm caller có transaction: `NEVER` thể hiện một architecture constraint.

Không quyết định propagation dựa trên loại exception vừa xuất hiện trước khi hiểu nguyên nhân.

### Bước 3 — chọn consistency/isolation requirements

Nếu chỉ một statement atomic conditional update giải quyết invariant, mức isolation như `READ_COMMITTED` có thể đủ cho phần đó; với nhiều statements và cross-row invariants, cần xem snapshot semantics, locking và serializable anomalies.

**Không bắt đầu bằng “đặt toàn bộ application SERIALIZABLE cho chắc”.** Isolation cao hơn có trade-offs về conflicts, serialization failures, lock contention, latency và retry. Chính xác hậu quả phụ thuộc DBMS.

### Bước 4 — chọn concurrency control

- Atomic SQL predicate/constraint cho invariant đơn giản.
- Optimistic version khi xung đột ít và muốn phát hiện stale client.
- Pessimistic row locking khi phải bảo vệ chuỗi “đọc, quyết định, ghi” và contention cao.
- Serializable + transaction-level retry cho những invariants khó bảo vệ bằng một lock/constraint.
- Phối hợp nhiều cơ chế khi business invariants yêu cầu: transaction + version + unique constraint.

### Bước 5 — tính resource và deadlock

Khi dùng pessimistic locks, giới hạn độ dài physical transaction, tránh HTTP trong transaction, lấy locks theo thứ tự nhất quán. Khi dùng `REQUIRES_NEW`, kiểm tra connection pool vì outer vẫn giữ resources; xác định T2 có cần rows T1 đang khóa không.

### Bước 6 — kiểm thử failure, concurrency và retry

Test không chỉ chạy một request thành công. Cần các trường hợp:

- Hai requests đọc cùng version rồi cố ghi.
- Hai requests cùng trừ stock cận 0.
- Hai transactions update rows theo thứ tự đối nghịch để kiểm tra deadlock handling.
- Inner `REQUIRES_NEW` đọc row outer mới insert nhưng chưa commit.
- Outer `REQUIRED READ_COMMITTED` gọi inner `REQUIRED SERIALIZABLE`.
- Thử `validateExistingTransaction=true` để phát hiện mismatch.
- Kiểm tra dữ liệu **sau** physical commit/rollback, bằng query độc lập.

**Nếu test method itself `@Transactional` trong Spring TestContext**, nó có thể bao một outer transaction và rollback cuối test, làm thay đổi behavior của code được kiểm thử. Thiết kế test boundaries rõ ràng, dùng `TestTransaction` khi cần.

## 17. Lock duration, timeout và retry: không trộn lẫn các lỗi

| Vấn đề | Triệu chứng thường thấy | Hướng xử lý đúng |
| --- | --- | --- |
| Pool exhaustion | Chờ ở `DataSource.getConnection()`/Hikari borrow; active=max; pending tăng | Rút ngắn outer scope, giảm nested REQUIRES_NEW, sizing pool đúng workload, backpressure |
| DB lock wait | Đã có connection nhưng SQL đang chờ row/range lock | Xem DB blocking sessions, giảm giữ lock, lock order, lock timeout, thiết kế lại T1/T2 |
| Deadlock | DB phát hiện vòng chờ và rollback một transaction | Retry **toàn transaction** phù hợp và idempotent, nhất quán lock order |
| Serialization failure | DB hủy một transaction để duy trì SERIALIZABLE | Retry transaction từ đầu với bounded backoff, không retry chỉ phần statement trong tx đã abort |
| Optimistic conflict | Version check 0 rows/`OptimisticLockException` | Reload/reconcile/retry theo nghiệp vụ, không trả success giả |
| Unique constraint violation | `UNIQUE`/constraint chặn duplicate | Trả lỗi nghiệp vụ thích hợp hoặc dùng idempotent upsert đúng DB-specific semantics |
| Unexpected rollback | Participating scope đánh dấu shared tx rollback-only | Sửa rollback handling/boundary; không đổi propagation bừa |
| Mismatch isolation | Inner REQUIRED muốn isolation khác outer | Sửa transaction owner, dùng `validateExistingTransaction` để fail-fast nếu cần |

`@Transactional(timeout=...)` và DB statement/lock timeout, pool connection timeout, HTTP request timeout là những giới hạn ở **các tầng khác nhau**. Không tăng cùng một con số rồi cho rằng đã sửa lock waits. Timeout giúp tránh treo vô hạn; invariant vẫn cần được bảo vệ.

### Vị trí retry

Đối với optimistic conflict hoặc serialization failure, retry nên đặt **bên ngoài transaction đã thất bại** để mỗi attempt tạo một transaction context mới. Ví dụ flow tổng quát:

```text
retry attempt 1
   -> begin T1
   -> read/validate/update
   -> conflict/serialization failure
   -> rollback T1
retry attempt 2
   -> begin T2 mới
   -> re-read state mới
   -> validate/update
   -> commit T2
```

Đừng retry cùng một `EntityManager` hoặc `TransactionStatus` đã rollback-only. Cần idempotency để lặp lại operation không thực hiện side effects bên ngoài hai lần.

## 18. Checklist review code

- [ ] Business invariant được mô tả rõ: atomicity, uniqueness, stock, balance, booking overlap, snapshot consistency.
- [ ] Propagation được chọn theo **transaction ownership và independent commit**, không để che một lỗi hiện có.
- [ ] Inner `REQUIRED` tham gia outer đúng manager/resource; không giả định khai báo `isolation` ở inner sẽ đổi isolation T1.
- [ ] Nếu cần fail-fast mismatch, đã xem `validateExistingTransaction`.
- [ ] `REQUIRES_NEW` được cân nhắc về pool, row locks, foreign key, uncommitted visibility và độc lập commit.
- [ ] `NESTED` chỉ dùng khi savepoint được hỗ trợ, không coi là transaction độc lập.
- [ ] Đã chọn isolation theo database đang chạy, không chỉ dựa vào bảng ANSI tổng quát.
- [ ] Với read-modify-write, có atomic predicate, optimistic version hoặc pessimistic lock thích hợp.
- [ ] Với multi-row invariant, kiểm tra write skew, unique/exclusion constraints, serializable transaction và retry.
- [ ] `@Version` không bị bypass bởi bulk/native updates vô ý.
- [ ] Lock order được cố định để giảm deadlocks; các giao dịch giữ lock ngắn.
- [ ] Không cho rằng `readOnly=true` cấm mọi ghi hoặc thay thế concurrency control.
- [ ] Rollback rules phù hợp checked/unchecked exceptions và transaction boundary thực sự được intercept.
- [ ] Có integration tests với nhiều connections/threads và kiểm tra dữ liệu sau commit/rollback.
- [ ] Các lỗi concurrency được retry có giới hạn trên **transaction mới**, không tiếp tục transaction đã thất bại.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Hai methods cùng `@Transactional(REQUIRED)` có chắc tránh lost update khi hai HTTP requests chạy đồng thời?

Không. Các scopes trong cùng call stack có thể dùng chung physical transaction, nhưng mỗi HTTP request thường có transaction khác. Concurrent requests vẫn cần guard SQL, version, lock hoặc isolation phù hợp.

**Câu 2.** Inner `@Transactional(REQUIRED, isolation=SERIALIZABLE)` được gọi dưới outer `READ_COMMITTED` có tự nâng isolation lên SERIALIZABLE không?

Thông thường không. Nếu tham gia physical transaction hiện có, isolation của outer chi phối. Có thể bật `validateExistingTransaction=true` để báo mismatch thay vì âm thầm bỏ qua inner isolation setting.

**Câu 3.** `REQUIRES_NEW` có làm T2 bỏ qua locks của T1 đang suspend?

Không. T1 vẫn có thể giữ row locks và connection; T2 là transaction khác, phải tuân theo DB locking rules. Nếu cùng row, T2 có thể lock-wait hoặc timeout.

**Câu 4.** `SERIALIZABLE` có nghĩa transaction không bao giờ lỗi vì concurrency?

Không. DBMS có thể abort một transaction do serialization failure hoặc deadlock để duy trì serializable outcome. Ứng dụng phải retry toàn bộ transaction trong một boundary mới khi error retryable.

**Câu 5.** Một method dùng `@Version` có cần `@Transactional` không?

Việc ghi entity cần được đặt trong transaction phù hợp. `@Version` giúp kiểm tra stale data/optimistic conflict, nhưng không tự chọn ranh giới commit, không tự tạo giao dịch cho mọi lời gọi.

**Câu 6.** `SELECT ... FOR UPDATE` khác `@Transactional(isolation=REPEATABLE_READ)` thế nào?

`FOR UPDATE` yêu cầu database lock theo SQL/DB semantics trên rows được chọn; isolation là mức nhìn thấy dữ liệu và anomaly guarantee cho physical transaction. Một transaction có thể có isolation nhất định mà không dùng explicit pessimistic row lock cho SELECT.

**Câu 7.** Khi nào chọn `NESTED` thay vì `REQUIRES_NEW`?

Khi cần rollback-to-savepoint cho inner nhưng vẫn trong cùng physical transaction, và manager hỗ trợ. Nếu dữ liệu inner phải commit độc lập và tồn tại khi outer rollback, `NESTED` không đủ.

**Câu 8.** Tại sao `UPDATE inventory SET available=available-1 WHERE available>=1` tốt hơn “SELECT rồi UPDATE giá trị đã tính”?

Một SQL UPDATE có guard được engine kiểm tra trong cùng statement, tránh khoảng trống giữa việc application đọc số lượng và ghi giá trị dựa trên snapshot cũ. Vẫn phải kiểm tra affected rows và phụ thuộc SQL/DB correctness.

**Câu 9.** Nếu có invariant trên nhiều rows và hai transactions sửa hai rows khác nhau, `@Version` của từng row có luôn tránh write skew không?

Không. Hai transactions có thể không conflict cùng version row. Cần một cơ chế bảo vệ invariant toàn cục: guard row/constraint phù hợp hoặc serializable + retry.

**Câu 10.** Có phải `Isolation.DEFAULT` đồng nghĩa `READ_COMMITTED` trong mọi DB?

Không. Nó dùng isolation mặc định của database/resource. Hãy xác minh cấu hình DB/connection; đừng áp đặt mặc định của PostgreSQL cho MySQL, H2 hay hệ thống khác.

## 20. Kết luận

**Không thay thế lẫn nhau ba tầng sau:**

1. **Propagation** quyết định **phạm vi/quan hệ của physical transactions**: tham gia, tách mới, savepoint hoặc chạy ngoài.
2. **Isolation** quyết định **giao dịch được nhìn thấy và cạnh tranh với dữ liệu đồng thời thế nào**; mức isolation thực tế phải được xác minh trên DBMS và boundary đã mở transaction.
3. **Chiến lược khóa/concurrency control** quyết định **bảo vệ invariant cụ thể** trước concurrent writes: atomic SQL predicates, version check, pessimistic locks, constraints hoặc serializable retry.

Một kiến trúc đúng thường là **chọn transaction owner và propagation trước**, đặt isolation có cơ sở, rồi chọn guard/locking phù hợp từng invariant, sau cùng xác minh bằng integration tests có concurrency. Đừng kỳ vọng một annotation duy nhất tự giải quyết toàn bộ tính nhất quán của dữ liệu.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` chia sẻ physical transaction, `REQUIRES_NEW` độc lập, `NESTED` savepoint và cảnh báo pool.
2. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default propagation/isolation, isolation áp dụng cho new transactions, proxy/self-invocation và các attributes.
3. [Spring Framework — `Isolation` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Isolation.html): `DEFAULT` và bốn JDBC isolation levels.
4. [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `validateExistingTransaction` và propagation handling.
5. [Spring Framework — JDBC `JdbcTransactionManager`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): JDBC transaction manager và resource handling.
6. [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): `@Lock` và JPA lock modes trên repository query methods.
7. [Jakarta Persistence — `Version`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic version metadata và cập nhật có phát hiện conflict.
8. [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): ANSI anomalies, MVCC, khác biệt PostgreSQL `READ_UNCOMMITTED`/`REPEATABLE_READ`/`SERIALIZABLE`.
9. [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks, deadlocks và lock acquisition semantics.
10. [PostgreSQL — `SELECT`](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `NOWAIT` và `SKIP LOCKED` theo DB-specific SQL semantics.
