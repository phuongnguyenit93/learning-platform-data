# Đánh giá tính đúng đắn trước khi giảm mức cô lập

> **Chủ đề:** Spring Framework — Transaction Management. **Nhóm:** Khóa và đồng thời. **Mục tiêu:** xây dựng một quy trình có bằng chứng để trả lời câu hỏi: *có thể giảm isolation level của giao dịch mà vẫn giữ đúng mọi bất biến nghiệp vụ không?* Bài tập trung vào correctness, các lịch trình tranh chấp, Spring `@Transactional`, khóa và điều kiện cập nhật nguyên tử, không đánh đồng một phép đo throughput tốt với dữ liệu đúng. Ví dụ thực hành dùng Java 17, Spring Boot 3.5.7, Maven, Spring JDBC và H2.

## 1. Vì sao giảm mức cô lập là một thay đổi nghiệp vụ?

Khi nhiều transaction cùng đọc và ghi, mỗi transaction có thể nhìn một phần trạng thái hệ thống khác nhau. Mức cô lập (*transaction isolation level*) giúp database giới hạn những lịch trình được phép. Giảm isolation có thể cải thiện throughput, giảm lock wait hoặc giảm chi phí giữ snapshot, nhưng cũng có thể tạo ra lịch trình khiến **mọi transaction đều commit thành công trong khi trạng thái chung vi phạm quy tắc nghiệp vụ**.

Ví dụ: một slot chỉ có **một** chỗ, nhưng hai request đều `SELECT COUNT(*) = 0` rồi tạo hai bookings khác ID. Đó là lỗi về tính đúng đắn của nghiệp vụ, mặc dù không có dirty read và không hề có exception Java.

Trước khi quyết định đổi `SERIALIZABLE` xuống `READ_COMMITTED`, phải xác định:

1. **Bất biến nào phải luôn đúng?** Một slot tối đa một booking, số tồn không âm, một idempotency key chỉ gây tác động một lần, tối thiểu một nhân viên trực, tổng debit bằng tổng credit.
2. **Bất biến phải đúng tại mốc nào?** Sau từng database commit, sau một workflow có nhiều commits, hay có thể tạm sai trong một cửa sổ eventual consistency đã được hợp đồng cho phép?
3. **Những câu đọc nào quyết định câu ghi?** Đặc biệt các `SELECT COUNT`, `EXISTS`, `SELECT balance` rồi `if(...) UPDATE/INSERT`.
4. **Có transaction khác nào sửa cùng hàng, hàng khác nhưng liên quan đến cùng quy tắc, hoặc hàng chưa tồn tại?**
5. **Bảo vệ hiện tại nằm ở đâu?** Isolation, database constraint, khóa, optimistic version, atomic SQL update, queue hoặc transaction coordinator?
6. **Đã thử lịch trình xấu nhất trên database thực tế chưa?** Hay mới chỉ kiểm tra một request tuần tự?

**Quy tắc:** tính đúng của trạng thái **đã commit** là tiêu chí chấp nhận đầu tiên. Hiệu năng chỉ được đánh giá sau đó.

## 2. Bảng nhận diện các anomaly khi isolation yếu hơn

| Hiện tượng | Lịch trình minh họa | Vì sao quan trọng? |
| --- | --- | --- |
| **Dirty read** | A đọc update của B **trước khi B commit**, sau đó B rollback | A có thể quyết định dựa trên dữ liệu chưa từng được commit. |
| **Non-repeatable read** | A SELECT hàng X; B update+commit; A SELECT lại X và thấy giá trị mới | Một transaction có hai lần quan sát hàng không giống nhau. |
| **Phantom read** | A COUNT theo predicate; B INSERT hàng phù hợp+commit; A COUNT lại và thấy nhiều hàng hơn | Quy tắc dựa trên tập hàng/range có thể thay đổi. |
| **Lost update** | A/B cùng đọc giá trị cũ, rồi ghi đè các giá trị được tính riêng trong Java | Một update có thể biến mất khỏi giá trị cuối. |
| **Write skew** | A/B cùng đọc điều kiện tổng thể, nhưng mỗi bên cập nhật hàng **khác nhau** | Hai commit thành công vẫn phá bất biến xuyên nhiều hàng. |
| **Serialization anomaly** | Không có thứ tự chạy tuần tự nào tạo ra cùng kết quả các transactions đã commit | Các transaction có thể đồng thời “đúng riêng” nhưng “sai chung”. |

### 2.1. Các mức cô lập theo tên chuẩn

| Isolation | Định hướng bảo vệ | Cần kiểm tra trước khi giảm |
| --- | --- | --- |
| `READ_UNCOMMITTED` | Rất yếu, ở engine hỗ trợ có thể cho phép dirty read | Không dùng cho quyết định nghiệp vụ nhạy cảm chỉ vì muốn giảm blocking; một số engine thực tế nâng hành vi lên READ_COMMITTED. |
| `READ_COMMITTED` | Ngăn dirty reads của transaction khác | Non-repeatable read, phantom read, check-then-act và các race vẫn có thể xảy ra. |
| `REPEATABLE_READ` | Ngăn đọc lại cùng hàng thấy committed value mới theo mức bảo đảm tối thiểu | Không hứa tương đương serializable; snapshot isolation có thể gặp write skew. |
| `SERIALIZABLE` | Mục tiêu là tương đương một thứ tự transaction chạy tuần tự | Có thể phát sinh serialization/deadlock conflicts; ứng dụng phải rollback và retry đúng. |

Đây là bảng **khái niệm**, không phải cam kết implementation chung của mọi DB. PostgreSQL `REPEATABLE READ` còn ngăn các phantom reads theo định nghĩa thông thường nhưng vẫn có thể bị write skew; MySQL/InnoDB `REPEATABLE READ` có gap/next-key locking khác; SQL Server `READ COMMITTED` có hai cơ chế khi `READ_COMMITTED_SNAPSHOT` ON/OFF; Oracle cung cấp cách ánh xạ khác cho JDBC levels. Khi ra quyết định phải tra đúng phiên bản DB.

### 2.2. Snapshot ổn định vẫn chưa chắc serializable

Giả sử một transaction đọc ảnh chụp không đổi trong suốt thời gian chạy. Điều đó giúp các lần đọc nhất quán **trong transaction**, nhưng hai transactions có thể cùng đọc ảnh chụp “hai bác sĩ đều đang trực”, rồi mỗi transaction bỏ trực một bác sĩ khác nhau. Vì hai bên cập nhật hàng khác nhau, không có write-write conflict trực tiếp; trạng thái cuối là không ai trực.

Vậy **snapshot consistency ≠ serializable correctness**. Nếu invariant liên quan nhiều rows hoặc predicates, phải kiểm tra cả **read/write dependency** chứ không chỉ kiểm tra “SELECT hai lần có đổi không”.

## 3. Viết bất biến thành điều kiện kiểm chứng được

Một yêu cầu “dữ liệu nhất quán” không đủ để làm acceptance test. Nên ghi rõ điều kiện trước khi đổi isolation.

| ID | Bất biến | Phép kiểm tra sau commit |
| --- | --- | --- |
| B-01 | Mỗi slot chỉ có một booking đang hiệu lực | Không slot nào có hơn một booking `CONFIRMED`. |
| B-02 | Tồn kho không âm | `available >= 0` cho mọi SKU. |
| B-03 | Không thu tiền trùng cho cùng yêu cầu | Mỗi `idempotency_key` gây tối đa một khoản thu hiệu lực. |
| B-04 | Nhật ký kế toán cân bằng | Tổng debit bằng tổng credit cho từng journal/currency theo quy tắc kế toán. |
| B-05 | Ít nhất một bác sĩ trực mỗi ca | Mỗi shift còn ít nhất một row có `on_duty=true`. |
| B-06 | Số booking không vượt capacity | `confirmed_count(slot) <= capacity(slot)` ở mọi commit. |

Hãy ghi cả **phạm vi** của bất biến: chỉ một database, nhiều schemas, nhiều services, hay phụ thuộc hệ thống ngoài. `@Transactional` trên một JDBC manager không khiến HTTP payment hoặc database khác cùng rollback.

### 3.1. “An toàn ở isolation thấp” là câu kết luận có điều kiện

Có thể giảm mức cô lập nếu **mọi lịch trình được mức mới cho phép vẫn giữ invariant** nhờ cơ chế khác:

- `UNIQUE(slot_key)` thật sự biểu diễn “tối đa một booking cho slot”.
- `CHECK(available >= 0)` cùng atomic conditional DML ngăn kho âm.
- `version`/optimistic locking buộc một trong hai stale writers retry hoặc fail.
- Một row đại diện cho aggregate được khóa trước khi quyết định.
- SERIALIZABLE được giữ riêng cho transaction có invariant nhiều hàng khó bảo vệ.

Không nên coi “chúng tôi chưa thấy lỗi trên staging” là một lập luận đầy đủ nếu chưa tạo được lịch trình cạnh tranh.

## 4. Tình huống write skew: hai bác sĩ cùng rời ca

Giả sử:

```sql
CREATE TABLE on_call (
    doctor_id INT PRIMARY KEY,
    shift_id INT NOT NULL,
    on_duty BOOLEAN NOT NULL
);
INSERT INTO on_call VALUES (1, 99, TRUE), (2, 99, TRUE);
```

Quy tắc: **mỗi shift phải còn tối thiểu một bác sĩ trực**.

```text
T1 (A)                              T2 (B)
BEGIN                               BEGIN
SELECT COUNT(*) = 2
                                    SELECT COUNT(*) = 2
UPDATE doctor_id=1 SET on_duty=FALSE
                                    UPDATE doctor_id=2 SET on_duty=FALSE
COMMIT                              COMMIT

Kết quả: COUNT(on_duty=true, shift=99) = 0.
```

Hai transactions không ghi cùng `doctor_id`. Một `UNIQUE(doctor_id)` không giải quyết điều kiện “tồn tại ít nhất một bác sĩ”. Đây là **write skew**, tiêu biểu cho lý do phải kiểm tra invariants xuyên nhiều hàng trước khi dùng snapshot isolation như một thay thế cho serializable.

Các cách giải quyết có chủ đích:

1. Giữ `SERIALIZABLE` cho hoạt động rời ca, và retry **toàn transaction** khi DB báo serialization failure.
2. Tạo một row `shift` làm điểm khóa/điều phối, yêu cầu **mọi** thao tác đổi lịch đều khóa row đó trước khi đếm và cập nhật.
3. Dùng một counter/version trên aggregate `shift` với atomic conditional update, bảo đảm không về 0 và mọi writer tuân theo protocol.
4. Xây dựng constraint/trigger phù hợp engine và thực sự an toàn khi concurrent writes. Một `CHECK` đơn giản trên từng `doctor` không thể tự bảo vệ điều kiện xuyên nhiều hàng.
5. Nếu toàn bộ thao tác đã được serialize theo shift key ở application queue, vẫn phải định nghĩa failover/replay và các write paths ngoài queue.

**Không đủ:** chỉ thêm `@Transactional` hoặc dùng `readOnly` cho bước đếm.

## 5. Tình huống check-then-insert: hai booking cho một chỗ

Một slot `SLOT-A` có capacity=1. Hai transactions `READ_COMMITTED`:

```text
T1: SELECT COUNT(*) WHERE slot_key='SLOT-A' -> 0
T2: SELECT COUNT(*) WHERE slot_key='SLOT-A' -> 0
T1: INSERT booking_id=1, slot_key='SLOT-A'
T2: INSERT booking_id=2, slot_key='SLOT-A'
T1: COMMIT
T2: COMMIT

Kết quả: 2 bookings cho 1 chỗ.
```

Ở đây `PRIMARY KEY(booking_id)` không xung đột vì IDs khác nhau. Thao tác `SELECT COUNT(*)` không giữ quyền độc quyền insert vào slot còn trống ở mọi database/isolation. Nếu schema không có constraint tương đương bất biến, hai transactions có thể cùng commit.

Với quy tắc **tối đa một booking trên mỗi slot**, có thể đặt:

```sql
CREATE TABLE bookings (
    booking_id INT PRIMARY KEY,
    slot_key VARCHAR(40) NOT NULL,
    CONSTRAINT uq_booking_slot UNIQUE (slot_key)
);
```

Bây giờ DB **không cho phép** hai committed rows có cùng `slot_key`. Một attempt sẽ bị từ chối ở concurrency conflict dù cả hai từng đọc `COUNT=0`. `UNIQUE` là **phòng tuyến tính đúng độc lập với việc Java đọc trước đó**.

**Quan trọng:** nếu slot có capacity=5, `UNIQUE(slot_key)` sẽ sai nghiệp vụ; phải dùng thiết kế capacity/counter, locking hoặc constraint khác. Nếu booking có trạng thái canceled/confirmed, xác định chính xác “booking hiệu lực” trước khi chọn unique/index có điều kiện.

## 6. Phương pháp đánh giá: bảy bước

### Bước 1 — Inventory transaction boundaries

Liệt kê các method service, entry points, `@Transactional`, propagation, `transactionManager`, database, pool và mọi API có thể gọi. Phân biệt transaction **đang thực sự mở** với annotation chỉ xuất hiện trên source. Với Spring proxy mode, bean tự tạo bằng `new`, method `private/final` hoặc self-invocation `this.inner()` có thể không được interceptor xử lý như mong đợi.

### Bước 2 — Vẽ read set và write set

Cho mỗi transaction:

- Những key/rows, ranges, predicates nào được đọc?
- Những giá trị đọc được dùng để quyết định ghi?
- Những rows nào được insert/update/delete?
- Có hai request cập nhật cùng row không? Có cập nhật **hai rows khác nhau** nhưng cùng invariant không?
- Có điều kiện trên **hàng chưa tồn tại** không, ví dụ “không có booking nào cho slot này”?
- Có nhiều writers khác như batch job, admin script, service khác, migration không?

Một write set không giao nhau **không** chứng minh an toàn: write skew chính là trường hợp hai transactions ghi khác row nhưng phụ thuộc chung vào một điều kiện đã đọc.

### Bước 3 — Tạo lịch trình đối kháng

Với mỗi mô hình `SELECT → if → INSERT/UPDATE`, tạo hai transactions và ép chúng:

1. Cùng đọc state ban đầu.
2. Cùng vượt qua điều kiện `if`.
3. Cùng thực hiện mutation lên same row, different rows, hoặc một predicate range.
4. Cùng commit, một fail, một rollback, và một retry.
5. Đọc dữ liệu **sau khi cả hai kết thúc** từ một connection/transaction mới.
6. Kiểm tra invariants, không chỉ HTTP status/exception.

Dùng `CountDownLatch` hoặc `CyclicBarrier` để tái hiện race có kiểm soát, thay vì `Thread.sleep` rồi trông chờ timing tình cờ.

### Bước 4 — Xác định cơ chế bảo vệ

Với mỗi invariant, chọn và chứng minh **một** hoặc nhiều cơ chế:

- `UNIQUE`, `CHECK`, foreign key, filtered/partial unique index.
- Atomic `UPDATE ... SET x=x+1 WHERE x<limit`, kiểm tra affected rows.
- `@Version`/optimistic locking, có xử lý version conflict.
- `SELECT FOR UPDATE`/row locking theo cùng lock protocol.
- SERIALIZABLE với retry transaction đúng.
- Một aggregate row/counter, queue hoặc advisory lock được thiết kế đúng cho engine.

### Bước 5 — So sánh correctness ở mức cũ/mới

Chạy cùng các tests ở isolation cũ và mới, dùng đúng database/driver/schema/index/manager. Nếu level mới cho phép invariant violation mà không có cơ chế bù, **không phê duyệt**. Nếu không thấy lỗi, phải giải thích **tại sao constraint/atomic DML/lock** giữ đúng, không chỉ nêu số lần chạy.

### Bước 6 — Benchmark sau khi correctness đạt

Giữ workload, concurrency, connection pool, indexes và dataset tương đương. Đo p50/p95/p99, throughput **giao dịch hợp lệ**, retry/deadlock/conflict rate, pool wait, lock wait, version/undo pressure. Nếu throughput cao hơn nhưng số booking sai tăng, thay đổi thất bại.

### Bước 7 — Canary và rollback plan

Áp dụng thay đổi cho endpoint/transaction có phạm vi rõ; giám sát business invariants; có điều kiện dừng rollout. Đổi isolation trở lại mạnh hơn **không tự sửa dữ liệu đã commit sai**: cần reconciliation/compensation.

## 7. Các cách giữ đúng ở READ_COMMITTED

### 7.1. Atomic update tránh stale read

Đoạn dễ bị lost update:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void addPoints(long id, int delta) {
    int current = jdbc.queryForObject(
        "SELECT points FROM wallets WHERE id = ?",
        Integer.class, id
    );
    jdbc.update(
        "UPDATE wallets SET points = ? WHERE id = ?",
        current + delta, id
    );
}
```

Đây là **trích đoạn**, `jdbc` là `JdbcTemplate` được inject. Nếu hai requests cùng đọc 100 rồi ghi 110 và 120, một phép cộng có thể bị mất do stale application values.

Cách tốt hơn nếu chỉ cộng điểm:

```java
int affected = jdbc.update(
    "UPDATE wallets SET points = points + ? WHERE id = ?",
    delta, id
);
if (affected != 1) {
    throw new IllegalStateException("Wallet not found");
}
```

SQL cập nhật dựa trên row value lúc thực thi DML và dùng cơ chế concurrency control của DB. Với một hàng, đây thường là cách đơn giản hơn read-modify-write trong Java; vẫn cần kiểm tra overflow, constraints và driver/engine.

### 7.2. Atomic conditional decrement và CHECK

```java
int updated = jdbc.update(
    "UPDATE stock " +
    "SET available = available - ? " +
    "WHERE sku = ? AND available >= ?",
    quantity, sku, quantity
);
if (updated != 1) {
    throw new IllegalStateException("Insufficient stock");
}
```

Đây là trích đoạn, `quantity` phải dương và `sku` đã validate. Nếu cả hai requests muốn lấy lượng hàng vượt tồn, DB phải thực thi điều kiện cập nhật trên row phù hợp. Thêm `CHECK (available >= 0)` là một tầng bảo vệ. Chọn index theo `sku` và kiểm tra affected rows; không trả thành công nếu `0` rows updated.

### 7.3. Optimistic locking bằng version

```sql
UPDATE wallet
SET balance = 110,
    version = version + 1
WHERE id = 42
  AND version = 7;
```

Nếu transaction khác đã cập nhật version từ 7 thành 8, câu UPDATE điều kiện trên không cập nhật row. Java cần kiểm tra affected-row count:

```java
int count = jdbc.update(
    "UPDATE wallet SET balance=?, version=version+1 " +
    "WHERE id=? AND version=?",
    nextBalance, id, oldVersion
);
if (count == 0) {
    throw new IllegalStateException("Stale wallet version");
}
```

Đây là trích đoạn. Với JPA, mapping `@Version` cung cấp optimistic locking trong các tình huống được provider hỗ trợ; mọi writer phải tuân thủ version protocol. Retry phải **đọc state mới và chạy lại toàn bộ quyết định**, không chỉ gửi lại câu UPDATE với `oldVersion`.

### 7.4. Pessimistic locking cho row đại diện

Với capacity nhiều chỗ, có thể tạo một row `slot_capacity(id,capacity,used)` luôn tồn tại và khóa nó trước khi kiểm tra/quyết định:

```sql
BEGIN;

SELECT capacity, used
FROM slot_capacity
WHERE id = 10
FOR UPDATE;

-- Chỉ khi used < capacity:
UPDATE slot_capacity
SET used = used + 1
WHERE id = 10;

INSERT INTO bookings(booking_id, slot_id)
VALUES (101, 10);

COMMIT;
```

Đây là **kịch bản**, cú pháp/lock semantics khác theo engine. Mọi writer phải khóa **cùng row** trước khi update; nếu `SELECT FOR UPDATE` trả về 0 row, đừng mặc định đã khóa khoảng trống trên mọi database. Với SQL Server có thể dùng lock hints được thiết kế phù hợp thay vì sao chép `FOR UPDATE` từ PostgreSQL.

### 7.5. Serializable cho invariant nhiều hàng

Khi điều kiện liên quan nhiều rows khó chuyển thành constraint/aggregate lock, giữ SERIALIZABLE là lựa chọn dễ lý giải. Có thể có serialization failure (PostgreSQL SQLSTATE `40001`, ví dụ) và cần retry có giới hạn. Đừng nuốt exception rồi trả success, cũng đừng retry cùng transaction đã rollback-only.

**Không có biện pháp nào đúng nếu chỉ một trong nhiều write paths tuân theo.** Batch import hay admin script có thể làm hỏng invariant nếu bỏ qua locking/versioning protocol. Constraint trực tiếp tại DB giúp giảm lỗ hổng này.

## 8. Spring Framework: mức cô lập áp dụng ở đâu?

Ví dụ:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void placeOrder() {
    // Khi lời gọi đi qua proxy và tạo transaction mới,
    // manager yêu cầu database dùng READ_COMMITTED.
}
```

**Lưu ý kỹ thuật:**

- `@Transactional` là metadata, không phải engine MVCC/lock tự viết bằng Java.
- Propagation mặc định là `REQUIRED`. Nếu chưa có transaction, method có thể mở mới với READ_COMMITTED. Nếu inner `REQUIRED` tham gia outer đã mở SERIALIZABLE, isolation của **physical transaction hiện có** thường vẫn là SERIALIZABLE.
- `REQUIRES_NEW` tạo physical transaction mới, có thể áp isolation riêng, nhưng làm thay đổi commit/rollback boundary và thường cần thêm JDBC connection; không dùng như cách “hạ isolation riêng inner” mà bỏ qua hậu quả.
- `Isolation.DEFAULT` là mặc định của datasource/database, không đồng nghĩa READ_COMMITTED ở mọi engine.
- Bean phải Spring-managed và lời gọi đi qua proxy trong proxy mode; self-invocation `this.method()` bỏ qua advice của inner method.
- Một transaction manager chỉ quản lý những resources của nó; nhiều datasources không tự tạo distributed ACID.
- `readOnly=true` chỉ là metadata/hint và không tự cung cấp transaction-level consistent snapshot.

### 8.1. Inner annotation không tự hạ level của outer

```java
@Service
class OuterService {
    private final InnerService inner;
    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void outer() {
        inner.run();
    }
}

@Service
class InnerService {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void run() {
        // REQUIRED: tham gia physical transaction outer.
    }
}
```

Đây là **trích đoạn**, cần import `@Service` và transaction annotations. Trong cùng manager/resource, `run()` tham gia T1, không bắt đầu một READ_COMMITTED transaction mới. Nếu benchmark chỉ thay annotation inner thì có thể **chưa thay đổi isolation vật lý**.

Một số transaction manager có `setValidateExistingTransaction(true)` để **từ chối** isolation mismatch thay vì âm thầm tham gia. Nó không đổi T1 thành isolation khác.

### 8.2. Kiểm tra JDBC connection thực tế

Trong transaction được Spring quản lý có thể kiểm tra:

```java
Connection c = DataSourceUtils.getConnection(dataSource);
try {
    int isolation = c.getTransactionIsolation();
    System.out.println("actual-jdbc-isolation=" + isolation);
} finally {
    DataSourceUtils.releaseConnection(c, dataSource);
}
```

Đây là trích đoạn; import `java.sql.Connection` và `org.springframework.jdbc.datasource.DataSourceUtils`, `dataSource` là đúng nguồn của manager. `Connection.TRANSACTION_READ_COMMITTED=2`, `TRANSACTION_REPEATABLE_READ=4`, `TRANSACTION_SERIALIZABLE=8`. Không tự commit/rollback/close connection đang tham gia Spring transaction.

Mã JDBC isolation **chưa phản ánh mọi database option**: với SQL Server cần biết `READ_COMMITTED_SNAPSHOT` ON/OFF; MySQL có session-level isolation và consistent-read behavior; replication routing cũng ảnh hưởng visibility.

## 9. Khác biệt triển khai theo hệ quản trị

### PostgreSQL

- `READ COMMITTED` thường mặc định; mỗi plain statement `SELECT` nhìn snapshot của statement đó.
- `REPEATABLE READ` có snapshot ổn định và ngăn phantom theo cách PostgreSQL triển khai, nhưng có thể gặp write skew/serialization anomalies.
- `SERIALIZABLE` dùng Serializable Snapshot Isolation và có thể abort một transaction để tránh kết quả không serialize được; app cần retry toàn transaction khi gặp `40001`.
- `READ UNCOMMITTED` được PostgreSQL xử lý như READ COMMITTED, không phải dirty-read mode như tên chuẩn.
- `UPDATE/DELETE/SELECT FOR UPDATE` xử lý row locks và có thể re-evaluate điều kiện trên row version mới theo quy tắc engine, không thể suy diễn chỉ từ plain SELECT.

Tài liệu: https://www.postgresql.org/docs/current/transaction-iso.html và https://www.postgresql.org/docs/current/applevel-consistency.html.

### MySQL / InnoDB

- Mặc định của InnoDB thường là `REPEATABLE READ`; các consistent nonlocking SELECT trong một transaction dùng read view được thiết lập ở consistent read đầu tiên.
- `READ COMMITTED` tạo fresh read view cho mỗi consistent read, có các khác biệt về gap/record locking đối với locking reads và DML.
- `SELECT ... FOR UPDATE` không tương đương plain consistent SELECT, và range/next-key locking phụ thuộc index, predicate và isolation.
- Khi hạ từ RR xuống RC, cần kiểm tra phantom insert, `IF NOT EXISTS`, gap locks, batch jobs và replication/binlog format requirements.

Tài liệu: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html.

### Microsoft SQL Server

- `READ COMMITTED` khi `READ_COMMITTED_SNAPSHOT=OFF` thường dùng shared locks; khi ON sử dụng row-versioned statement-level snapshots cho normal reads.
- RCSI khác isolation `SNAPSHOT` (transaction-level snapshot). `REPEATABLE READ` dùng read locks mạnh hơn nhưng không mặc nhiên có key-range locking như SERIALIZABLE.
- Giảm isolation có thể cho phantom/predicate races; thay đổi RCSI là database option, không chỉ một annotation Spring.
- `WITH (NOLOCK)` có thể gây dirty reads, không nên dùng như công cụ “an toàn hơn và nhanh hơn”.

Kiểm tra RCSI:

```sql
SELECT name, is_read_committed_snapshot_on,
       snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
```

Tài liệu: https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide.

### Oracle Database

Oracle hỗ trợ `READ COMMITTED` với statement-level read consistency qua SCN/undo, cùng `SERIALIZABLE` và read-only transaction modes. Không giả định tất cả bốn levels của enum JDBC đều có hành vi như PostgreSQL/MySQL. Với transaction SERIALIZABLE tranh chấp, Oracle có thể báo `ORA-08177`. Các queries ở READ COMMITTED có thể nhìn committed snapshots khác nhau giữa các statements.

Tài liệu: https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html.

### H2

H2 hỗ trợ READ_COMMITTED và có thể tái hiện race `SELECT COUNT→INSERT`. Nó phù hợp học transaction isolation và test cơ chế constraint, nhưng không thay thế locking/index/MVCC semantics của database production. Khi phê duyệt thay đổi cần chạy integration test đúng DB/driver/version.

## 10. Dự án runnable: READ_COMMITTED + race + UNIQUE

**Mục tiêu:** chạy hai transactions đồng thời qua Spring proxy. Cả hai đọc số booking của `SLOT-A` bằng 0 rồi cùng INSERT. Bảng không có UNIQUE sẽ nhận **hai** bookings; bảng có `UNIQUE(slot_key)` chỉ có **một** booking sau commit. Không dùng `Thread.sleep`; dùng `CyclicBarrier` để chắc chắn cả hai transactions đã hoàn tất bước pre-check trước khi INSERT.

### Cấu trúc

```text
isolation-correctness-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/correctness/
    │   ├── CorrectnessApplication.java
    │   └── BookingService.java
    └── resources/application.properties
```

### 10.1. pom.xml

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
    <artifactId>isolation-correctness-demo</artifactId>
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

### 10.2. src/main/resources/application.properties

```properties
spring.datasource.url=jdbc:h2:mem:isolation_correctness;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
```

Hai threads cần ít nhất hai physical JDBC connections. `DB_CLOSE_DELAY=-1` giữ H2 in-memory database giữa các connections trong cùng JVM.

### 10.3. src/main/java/vn/example/correctness/BookingService.java

```java
package vn.example.correctness;

import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookingService {
    private final JdbcTemplate jdbc;

    public BookingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void book(String caseName, int bookingId, CyclicBarrier gate) {
        String table = switch (caseName) {
            case "unsafe" -> "bookings_unsafe";
            case "safe" -> "bookings_safe";
            default -> throw new IllegalArgumentException("Unknown case");
        };

        int existing = jdbc.queryForObject(
            "SELECT COUNT(*) FROM " + table + " WHERE slot_key = ?",
            Integer.class, "SLOT-A"
        );

        if (existing != 0) {
            throw new IllegalStateException("Slot already occupied");
        }

        try {
            gate.await(10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted at barrier", e);
        } catch (BrokenBarrierException | TimeoutException e) {
            throw new IllegalStateException("Barrier failed", e);
        }

        jdbc.update(
            "INSERT INTO " + table +
            " (booking_id, slot_key) VALUES (?, ?)",
            bookingId, "SLOT-A"
        );
    }
}
```

**Giải thích:**

- Chỉ hai tên bảng cố định được chọn trong `switch`; không nối SQL identifier lấy tùy ý từ input.
- Transaction được bắt đầu khi caller gọi public method trên Spring-managed proxy.
- Hai transactions cùng nhìn `COUNT=0` vì `CyclicBarrier` được đặt **sau SELECT, trước INSERT**.
- `READ_COMMITTED` ngăn dirty read nhưng không biến check-then-insert thành thao tác atomic.
- Với bảng safe, `UNIQUE(slot_key)` bảo vệ bất biến lúc ghi/commit, bất kể hai requests trước đó đã cùng thấy slot còn trống.
- Lỗi barrier là unchecked exception, giúp transaction rollback nếu test bị kẹt hoặc interrupted.

### 10.4. src/main/java/vn/example/correctness/CorrectnessApplication.java

```java
package vn.example.correctness;

import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class CorrectnessApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorrectnessApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner run(JdbcTemplate jdbc, BookingService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE bookings_unsafe (" +
                "booking_id INT PRIMARY KEY, " +
                "slot_key VARCHAR(40) NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE bookings_safe (" +
                "booking_id INT PRIMARY KEY, " +
                "slot_key VARCHAR(40) NOT NULL, " +
                "CONSTRAINT uq_safe_slot UNIQUE(slot_key))"
            );

            int unsafe = race(jdbc, service, "unsafe", 1, 2);
            int safe = race(jdbc, service, "safe", 11, 12);

            System.out.println("without_constraint=" + unsafe);
            System.out.println("with_unique_constraint=" + safe);
        };
    }

    private static int race(
            JdbcTemplate jdbc, BookingService service,
            String caseName, int idA, int idB
    ) throws Exception {
        CyclicBarrier gate = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Boolean> a = pool.submit(
                () -> attempt(service, caseName, idA, gate)
            );
            Future<Boolean> b = pool.submit(
                () -> attempt(service, caseName, idB, gate)
            );

            boolean committedA = a.get(20, TimeUnit.SECONDS);
            boolean committedB = b.get(20, TimeUnit.SECONDS);

            String table = switch (caseName) {
                case "unsafe" -> "bookings_unsafe";
                case "safe" -> "bookings_safe";
                default -> throw new IllegalArgumentException("Unknown case");
            };
            int rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table +
                " WHERE slot_key = ?",
                Integer.class, "SLOT-A"
            );

            if ("unsafe".equals(caseName)) {
                if (!committedA || !committedB || rows != 2) {
                    throw new AssertionError("Unexpected unsafe result");
                }
            } else {
                if (committedA == committedB || rows != 1) {
                    throw new AssertionError("Unexpected safe result");
                }
            }
            return rows;
        } finally {
            pool.shutdownNow();
        }
    }

    private static boolean attempt(
            BookingService service, String caseName,
            int bookingId, CyclicBarrier gate
    ) {
        try {
            service.book(caseName, bookingId, gate);
            return true; // Proxy method returned after commit.
        } catch (DuplicateKeyException expected) {
            return false; // Database rejected the duplicate slot.
        }
    }
}
```

**Tại sao ví dụ có tính kiểm chứng?**

1. Hai bảng và constraint được tạo **trước** các service transactions; không có DDL giữa transaction khiến kết quả rollback khó đo.
2. `@EnableTransactionManagement(proxyTargetClass = true)` cùng `@Service` và injection đảm bảo runner gọi `BookingService` qua Spring proxy.
3. Hai executor threads có transaction contexts/DB connections riêng; không chia sẻ một imperative transaction qua threads.
4. `CyclicBarrier` buộc cả hai SELECT hoàn tất trước INSERT, tạo lịch trình đối kháng.
5. Hai booking IDs trong từng case là khác nhau, nên bảng unsafe chỉ có một giới hạn PK theo ID, không bảo vệ slot.
6. Với bảng safe, uniqueness index từ chối một thao tác; demo chỉ coi `DuplicateKeyException` là kết quả mong đợi. Nếu có timeout, deadlock hoặc exception khác, `Future.get` báo lỗi thay vì in thành công giả.
7. `Future.get` đợi cả hai service calls kết thúc; lời gọi qua proxy trả về sau commit/rollback. Việc đếm ở runner quan sát **trạng thái đã commit**.

### 10.5. Chạy và stdout

Trong thư mục `isolation-correctness-demo`:

```bash
java -version
mvn -version
mvn -q package
java -jar target/isolation-correctness-demo-1.0.0.jar
```

Với Java 17, Spring Boot 3.5.7, H2 và cấu hình trên, hai dòng do ứng dụng chủ động in là:

```text
without_constraint=2
with_unique_constraint=1
```

Spring Boot/HikariCP có thể có thêm log startup. Nếu DB/driver/isolation khác làm một transaction chờ hoặc fail vì lock khác dự kiến, **không** được sửa kỳ vọng theo cách che lỗi; cần điều tra vì mục tiêu là hiểu scheduling và cơ chế bảo vệ, không phải ép output “xanh”.

### 10.6. Giới hạn của demo

Bài chỉ chứng minh một bất biến “một slot một booking” với `UNIQUE(slot_key)`. Nó **không** chứng minh:

- Tất cả invariants đa hàng đều được giải bằng UNIQUE.
- H2 mô phỏng hoàn toàn PostgreSQL/Oracle/MySQL/SQL Server.
- READ_COMMITTED có throughput cao hơn trong mọi workload.
- Mọi lỗi cạnh tranh đều là duplicate key; có thể có deadlock, lock timeout, optimistic conflicts, serialization failures.
- Một run trên H2 là đầy đủ để phê duyệt production migration.

Nếu capacity>1, cần một schema và một invariant khác; nếu có status CANCELLED, phải định nghĩa “booking hiệu lực” và thiết kế constraint thích hợp.

## 11. Kiểm thử đúng trên database sản xuất

### 11.1. Kiểm thử lịch trình

Với PostgreSQL/MySQL/SQL Server/Oracle version sản xuất, dùng Testcontainers hoặc staging:

1. Tạo dữ liệu baseline và constraints như sản xuất.
2. Mở **hai physical transactions riêng** với connections khác nhau.
3. Đồng bộ sau SELECT, trước mutation; tránh `Thread.sleep` không kiểm soát.
4. Thử cả hai commit, một rollback, một timeout, một transaction được retry.
5. Kiểm tra invariant sau commit từ connection mới.
6. Thử cập nhật cùng row, hai rows khác nhau và predicate range khi không có row.
7. Kiểm tra `SET TRANSACTION`/`@Transactional` thực sự tác động level của transaction mới; không bị outer `REQUIRED` che khuất.

### 11.2. Kiểm thử bất biến, không chỉ API status

Ví dụ với booking:

```sql
SELECT slot_key, COUNT(*) AS total
FROM bookings
GROUP BY slot_key
HAVING COUNT(*) > 1;
```

Truy vấn trả row nào thì có slot vi phạm invariant **nếu schema thật sự định nghĩa mọi row trong bảng là booking hiệu lực**. Nếu có status, chỉ đếm các trạng thái phải tham gia constraint.

Với hàng tồn kho: `SELECT sku FROM stock WHERE available < 0`. Với ca trực: phải đối chiếu bảng `shift` và nhóm bác sĩ trực để không bỏ sót shift **không còn row nào**. Với journal, cần cộng debit/credit theo currency và trạng thái committed phù hợp. Không chỉ dựa vào log request.

### 11.3. Stress test và deterministic test bổ trợ nhau

Stress test với hàng nghìn requests tìm được race chưa biết, nhưng “0 lỗi” trong 100.000 request không chứng minh không tồn tại một lịch trình xấu hiếm. Deterministic barrier test giúp cố ý tạo conflict đúng điểm nghiệp vụ; sau đó stress test đo khả năng vận hành ở tải thực tế.

### 11.4. Spring TestContext có thể làm sai giả định

Nếu test method tự có `@Transactional`, Spring TestContext có thể bắt đầu **test-managed transaction** và rollback cuối test. Service `REQUIRED` có thể tham gia transaction test thay vì tạo transaction riêng. Điều này che giấu boundary, isolation và committed state.

Để kiểm tra concurrent commits, ưu tiên test không được bao bởi outer test transaction, hoặc dùng cơ chế quản lý test transactions có chủ đích. Đếm dữ liệu sau khi cả hai service calls đã kết thúc.

## 12. Retry, exception và idempotency

**Ở SERIALIZABLE** hoặc khi dùng optimistic locking, một transaction đúng có thể bị **từ chối** để bảo vệ invariant. Ứng dụng phải xem đó là kết quả kiểm soát cạnh tranh, không tự coi mọi lỗi là bug.

Quy trình retry phù hợp:

```text
Begin new transaction
    -> read fresh state
    -> revalidate invariant/business rules
    -> attempt write
    -> commit
If known retryable conflict:
    -> rollback fully
    -> bounded backoff
    -> begin another NEW transaction
Else:
    -> report the business/infrastructure failure
```

Không retry chỉ câu `UPDATE` cũ dựa trên snapshot cũ. Không dùng một transaction đã bị rollback-only để thử lại.

Trong Spring, retry logic nên nằm **ngoài** boundary `@Transactional`, hoặc có aspect order được cấu hình và kiểm thử chính xác, để mỗi attempt thực sự nhận transaction mới. Cần phân loại exception theo transaction manager/driver: `CannotSerializeTransactionException`, `OptimisticLockingFailureException`, deadlock/lock timeout hoặc SQLSTATE của engine có thể xuất hiện khác nhau.

### Idempotency ngoài database

Nếu payment HTTP đã thành công nhưng local database transaction rollback, retry có thể thu tiền hai lần. `@Transactional` dù dùng SERIALIZABLE cũng **không** rollback remote side effect. Cần idempotency key, transactional outbox/saga hoặc reconciliation design. Không chọn mức isolation dựa trên giả định mọi bước của một workflow phân tán cùng physical transaction.

## 13. Benchmark sau khi correctness PASS

| Phạm vi | Metric nên đo | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Hiệu năng API | p50/p95/p99 latency; throughput requests thành công đúng nghiệp vụ | p99 tăng vì lock wait/retry dù median giảm. |
| Cạnh tranh DB | Lock waits, deadlocks, serialization/optimistic conflicts | Đổi level làm conflict pattern tăng hoặc giảm bất ngờ. |
| JDBC pool | Active, idle, pending connections; acquisition latency | Transaction dài hoặc `REQUIRES_NEW` khiến pool cạn. |
| MVCC | Undo/version store pressure; tuổi transaction; cleanup lag | Transactions giữ snapshot lâu hoặc đọc rất rộng. |
| Correctness | Bất biến vi phạm sau commit, duplicate booking, stock âm | **Bất kỳ** vi phạm nào cần chặn rollout. |
| Retry | Attempts per success, exhausted retries, final error rate | Tăng throughput SQL nhưng giảm số business operations hoàn tất. |

Giữ dataset, concurrency, schema/index, DB/driver, pool, load distribution và query patterns tương đương giữa các phép đo. Test cả workload read-heavy, write-heavy và **hot key contention**. Nên đo “giao dịch nghiệp vụ đúng hoàn tất trên một giây” hơn là chỉ “SQL statements trên một giây”.

## 14. Giảm blocking mà chưa cần hạ isolation

Trước khi thay đổi isolation, có thể ưu tiên:

- Tối ưu index và predicate để giảm rows/ranges bị scan/lock.
- Rút ngắn transaction: không giữ connection/locks trong khi gọi HTTP hoặc tính toán lâu.
- Chuyển check-then-act thành atomic conditional DML.
- Dùng constraint để DB bảo vệ invariant bất kể mọi caller.
- Tách đọc dashboard/report khỏi transaction ghi nhưng định nghĩa rõ eventual-consistency SLA.
- Dùng row đại diện/aggregate version khi invariant nằm trên nhiều rows.
- Đảm bảo mọi writer đều tuân thủ cùng lock ordering và protocol.
- Hạn chế tranh chấp hot row bằng partition/queue thích hợp.
- Điều chỉnh pool/backpressure/retry policy sau khi đã quan sát bottleneck thực.

Nếu chỉ một vài reports chấp nhận thấy dữ liệu mới giữa các câu SELECT, có thể cân nhắc một transaction read-only có level nhẹ hơn **riêng** cho phần đó, thay vì giảm level của operations chuyển tiền/booking nhạy cảm. Nhưng `readOnly=true` không tự tạo snapshot ổn định và không phải security boundary.

## 15. Quy trình triển khai và rollback

**Trước thay đổi**, ghi lại:

- Transaction boundaries, isolation hiện hành, DB/driver/manager, nguồn giá trị config.
- Bất biến và chủ sở hữu nghiệp vụ.
- Lịch trình concurrent đã test, các write paths, ràng buộc/khóa đang bảo vệ.
- Kết quả baseline correctness/performance.
- Cách giám sát anomalies và phương án sửa dữ liệu sai nếu thay đổi bị lỗi.

**Trong canary**:

1. Áp isolation mới cho phạm vi rõ ràng, không đổi global default của database nếu chưa được duyệt.
2. Kiểm tra transaction realmente dùng isolation mong muốn; không chỉ dựa vào source annotation.
3. Đo invariant violations, conflict/retry và latency.
4. Có ngưỡng dừng rollout, rollback config và reconciliation plan.
5. Ghi lại evidence đủ để review/điều tra.

**Sau rollback:** isolation mạnh hơn trở lại **không tự hoàn tác** các booking trùng hoặc ledger sai đã commit trong giai đoạn trước. Cần reconciliation/compensation và kiểm tra consistency.

## 16. Các lỗi phân tích dễ gặp

| Nhận định sai | Điều cần sửa |
| --- | --- |
| “READ_COMMITTED không dirty read, vậy dữ liệu luôn nhất quán.” | Dirty read chỉ là một hiện tượng; vẫn có non-repeatable, phantom và read-check-write races. |
| “Hai transactions update hai rows khác nhau thì an toàn.” | Write skew có thể phá invariant trên tập rows. |
| “REPEATABLE_READ luôn serializable.” | Không; phụ thuộc engine, snapshot isolation có write skew. |
| “Transaction có @Transactional là đủ.” | Phải xác minh proxy, propagation, manager và database constraints. |
| “Inner isolation=READ_COMMITTED chắc chắn hạ outer.” | Inner `REQUIRED` thường tham gia outer, isolation physical transaction không tự đổi. |
| “SELECT FOR UPDATE ở query không trả row khóa được slot rỗng.” | Không bảo đảm ở mọi engine/isolation; nên dùng row đại diện hoặc unique/range-lock mechanism đã test. |
| “Chạy stress test không lỗi nghĩa là không có race.” | Chưa test lịch trình xấu không phải bằng chứng an toàn. |
| “Nếu có exception thì không transaction nào commit.” | Exception propagation, rollback rules và `REQUIRES_NEW` có thể tạo committed side effect khác dự tính. |
| “Đổi isolation về cũ sẽ sửa dữ liệu.” | Không sửa committed corruption, cần reconciliation. |
| “H2 giống hệt production DB.” | H2 là môi trường học; lock/MVCC/index semantics khác engine thật. |

## 17. Checklist quyết định

- [ ] Business invariants và phạm vi đúng sau commit được viết thành điều kiện kiểm chứng.
- [ ] Đã vẽ transaction boundaries, read sets, write sets và toàn bộ đường ghi.
- [ ] Đã thử cùng row, khác row, predicate range và trường hợp chưa có row.
- [ ] Đã mô phỏng dirty read/non-repeatable read/phantom read, lost update, write skew nếu chúng liên quan.
- [ ] Đã hiểu engine/version: PostgreSQL, MySQL InnoDB, SQL Server RCSI, Oracle.
- [ ] Đã xác nhận isolation **hiệu lực** trên JDBC transaction mới và propagation của Spring.
- [ ] Invariant được bảo vệ bằng constraint, atomic DML, optimistic version, locking protocol hoặc SERIALIZABLE có retry.
- [ ] Có test với hai transactions/physical connections thực, barrier/latch và committed-state assertions.
- [ ] Có test đúng database/driver/schema production; không chỉ H2.
- [ ] Các exceptions có thể retry được phân loại, bounded và operation idempotent.
- [ ] Có số liệu throughput **giao dịch đúng**, p95/p99, lock wait, deadlock, pool wait và retry rate.
- [ ] Có canary, monitoring business invariants, rollback plan và kế hoạch sửa committed corruption.
- [ ] Không đổi global isolation chỉ vì một benchmark đơn luồng.

## 18. Câu hỏi tự kiểm tra

**1.** Hai requests READ_COMMITTED cùng đọc COUNT=0 rồi INSERT hai booking khác ID. Vì sao có thể bị overbooking?

**Đáp án:** Vì bước kiểm tra và bước ghi là các statement khác nhau; hai transactions có thể đọc cùng trạng thái hợp lệ trước khi bên nào commit. Không có unique/atomic protocol ngăn hai writes.

**2.** UNIQUE(slot_key) có giúp được trường hợp mỗi slot một chỗ không?

**Đáp án:** Có, nếu invariant đúng là một committed row cho mỗi slot_key. DB ngăn bản ghi thứ hai trùng key; phải xử lý duplicate theo business contract.

**3.** Nếu capacity=5 thì UNIQUE(slot_key) có đúng không?

**Đáp án:** Không. Cần mô hình counter/atomic conditional update hoặc khóa và constraint phù hợp.

**4.** Vì sao cùng snapshot trong REPEATABLE_READ chưa đủ để ngăn hai bác sĩ cùng bỏ trực?

**Đáp án:** Hai transactions cập nhật hai rows khác nhau dựa trên điều kiện chung; write skew có thể xảy ra nếu engine không buộc một transaction fail.

**5.** Tại sao phải đo actual JDBC isolation level thay vì chỉ annotation inner method?

**Đáp án:** Vì inner `REQUIRED` có thể đang tham gia outer transaction mức khác; annotation inner không đặt lại isolation.

**6.** Có nên retry một SQL UPDATE với oldVersion cũ sau optimistic conflict?

**Đáp án:** Không. Phải bắt đầu transaction mới, đọc lại dữ liệu, kiểm tra lại business rule rồi mới ghi; có giới hạn retry.

**7.** 100.000 lần thử không lỗi có chứng minh không có race không?

**Đáp án:** Không. Cần lịch trình concurrency xác định và lập luận về ràng buộc/lock semantics; stress test chỉ bổ sung bằng chứng.

**8.** Nếu đã commit sai booking, rollback cấu hình isolation có sửa được không?

**Đáp án:** Không. Cần reconciliation/compensation và kiểm tra dữ liệu đã sai.

## Nguồn tham khảo chính thức

1. [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation và isolation khi bắt đầu transaction mới.
2. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): scope logic/vật lý, `REQUIRED` và `REQUIRES_NEW`.
3. [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): read committed, repeatable read và serializable anomalies.
4. [PostgreSQL — Application-Level Data Consistency Checks](https://www.postgresql.org/docs/current/applevel-consistency.html): giữ invariants bằng serializable transactions hoặc explicit locking.
5. [MySQL 8.4 — InnoDB Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html): consistent reads, gap/next-key locks và default level.
6. [Microsoft SQL Server — Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide): lock-based reads, RCSI và serializable.
7. [Oracle — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): statement read consistency, serializable, SCN.
8. [H2 Database — Advanced](https://h2database.com/html/advanced.html): JDBC transaction isolation của môi trường thực hành.

**Kết luận:** giảm mức cô lập là **mở rộng tập lịch trình concurrent có thể commit**. Chỉ làm khi invariants đã được định nghĩa, các races được tái hiện, constraints/locks/atomic updates/optimistic versions hoặc serializable alternatives được chứng minh đúng, và kết quả được kiểm tra trên database sản xuất tương ứng. **Tính đúng trước — hiệu năng sau.**
