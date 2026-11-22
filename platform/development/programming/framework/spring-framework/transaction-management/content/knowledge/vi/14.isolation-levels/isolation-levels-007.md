# SERIALIZABLE và khả năng phải thử lại giao dịch trong Spring Framework

## Trọng tâm cần nắm

`SERIALIZABLE` là mức cô lập giao dịch hướng tới bảo đảm rằng **những giao dịch đã commit có kết quả tương đương một lịch chạy tuần tự nào đó**. Nó không hứa tất cả giao dịch đồng thời đều thành công, cũng không đồng nghĩa database bắt mọi giao dịch chạy lần lượt. Để duy trì tính đúng đắn khi có xung đột đọc/ghi, database **có thể buộc một hoặc nhiều giao dịch rollback**. Ứng dụng khi đó cần **retry toàn bộ transaction từ đầu**, bao gồm việc đọc lại dữ liệu, kiểm tra điều kiện nghiệp vụ, lựa chọn SQL và ghi dữ liệu.

Trong Spring, ta thường khai báo:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void allocateResources() {
    // Đọc trạng thái hiện tại, kiểm tra bất biến, rồi cập nhật dữ liệu
}
```

Đây là **fragment minh họa**, chưa có class và repository để chạy độc lập. Nó chỉ có hiệu lực ở transaction boundary thực sự được Spring advice quản lý. Nếu lời gọi này **tham gia** một transaction `REQUIRED` bên ngoài vốn đã chạy ở isolation khác, khai báo inner `SERIALIZABLE` **không tự nâng mức cô lập** của physical transaction đã tồn tại theo mặc định. Cần đặt isolation ở boundary mở transaction mới, hoặc chọn `REQUIRES_NEW` khi nghiệp vụ cho phép.

Với PostgreSQL, lỗi tiêu biểu là SQLSTATE **`40001` (`serialization_failure`)**. Đây là tín hiệu giao dịch hiện tại không thể tiếp tục/commit an toàn trong lịch chạy đồng thời quan sát được. Retry đúng nghĩa là **bắt đầu một transaction mới và chạy lại toàn bộ logic nghiệp vụ**, không phải bắt exception ở giữa một transaction rồi chạy lại chỉ câu `UPDATE`. Một số deadlock cũng có thể retry theo chính sách riêng (`40P01` trong PostgreSQL), nhưng không được biến tất cả lỗi SQL thành lỗi tạm thời.

Bài này thuộc nhóm **Mức cô lập** của **Spring Framework – transaction-management**. Nội dung tập trung vào khả năng phải retry ở `SERIALIZABLE`, cách mô phỏng xung đột, cấu trúc transaction/retry trong Spring, giới hạn độ an toàn và ví dụ Java 17 chạy độc lập.

---

## 1. SERIALIZABLE bảo đảm điều gì, không bảo đảm điều gì?

Một giao dịch thường gồm nhiều bước:

```text
T1:
  đọc dữ liệu hiện tại
  kiểm tra điều kiện nghiệp vụ
  tính quyết định
  cập nhật một hoặc nhiều hàng
  commit

T2 chạy đồng thời:
  đọc dữ liệu hiện tại
  kiểm tra điều kiện tương tự
  cập nhật dữ liệu
  commit
```

Nếu các thao tác đọc/ghi đan xen, kết quả cuối có thể không tương ứng với thứ tự **T1 rồi T2** hoặc **T2 rồi T1**. Một lịch như vậy có **serialization anomaly**.

`SERIALIZABLE` hướng tới bảo đảm rằng mỗi tập giao dịch commit thành công có thể được giải thích như một **serial history** nào đó. Database có thể thực hiện điều này bằng:

- Khóa và chặn những thao tác xung đột theo cơ chế cụ thể.
- Kiểm tra conflict/dependency để quyết định một giao dịch phải abort.
- Kết hợp MVCC, predicate locking hoặc thuật toán concurrency control khác tùy hệ quản trị.

Đặc biệt ở PostgreSQL, `SERIALIZABLE` sử dụng **Serializable Snapshot Isolation (SSI)**: transaction được đọc qua snapshot, đồng thời theo dõi những phụ thuộc đọc/ghi có thể tạo lịch không serializable; khi phát hiện nguy cơ, hệ thống có thể hủy một transaction. Không nên hình dung tất cả `SELECT` đều lập tức lấy khóa chặn người ghi. SSI có overhead phát hiện conflict và vẫn có thể có các loại blocking khác vì row locks hay lệnh SQL.

### 1.1. Serializable không đồng nghĩa linearizable

- **Serializability**: các transaction commit tương đương một thứ tự tuần tự hợp lệ.
- **Strict serializability/linearizability**: còn ràng buộc thứ tự theo thời gian thực đối với những thao tác không chồng lấp.

Đây là những thuộc tính nhất quán khác nhau. Không nên chỉ thấy `Isolation.SERIALIZABLE` rồi suy ra hệ thống phân tán hoặc toàn bộ API của ứng dụng cung cấp linearizability.

### 1.2. Serializable không làm “mọi thao tác ngoài DB” transactional

Email, HTTP request, file write, event gửi đến một message broker khác transaction resource hoặc một datasource khác **không tự rollback** khi một JDBC transaction bị abort. Chạy lại toàn bộ transaction có thể làm những hiệu ứng ngoài DB xảy ra **hai lần** nếu đặt chúng vào đoạn code sẽ retry. Phải tách các side effects hoặc dùng outbox/transactional messaging/idempotency phù hợp.

### 1.3. Serializable không cam kết thành công trong thời gian hữu hạn

Một transaction có thể được abort nhiều lần khi contention cao. Retry không có nghĩa lần thứ hai chắc chắn thành công; hệ thống cần giới hạn attempts, backoff, theo dõi mức độ tranh chấp và trả lỗi có thể xử lý nếu hết ngân sách retry.

## 2. Vì sao SERIALIZABLE có thể thất bại dù từng SQL đều hợp lệ?

Các SQL trong hai giao dịch riêng lẻ có thể đúng cú pháp, đúng constraint và hợp lệ khi chạy tuần tự. Vấn đề xuất hiện từ **quan hệ giữa các snapshot và thao tác ghi của nhiều transaction đồng thời**.

Ví dụ trực quan với quy tắc: *phải luôn có ít nhất một bác sĩ trực*. Ban đầu có hai bác sĩ A và B cùng trực:

| ID | Bác sĩ | `on_call` |
| --- | --- | --- |
| 1 | A | `true` |
| 2 | B | `true` |

Giao dịch T1 muốn cho A nghỉ, T2 muốn cho B nghỉ. Cả hai đều thực hiện:

1. `SELECT COUNT(*) FROM doctors WHERE on_call = TRUE`.
2. Nếu số lượng đang trực lớn hơn 1, cập nhật bác sĩ của mình thành `on_call=FALSE`.
3. Commit.

Một lịch chạy chồng lấp có thể là:

```text
Thời điểm      T1 (A nghỉ)                      T2 (B nghỉ)
----------------------------------------------------------------
t0             BEGIN SERIALIZABLE              BEGIN SERIALIZABLE
t1             COUNT(on_call)=2
t2                                                COUNT(on_call)=2
t3             UPDATE id=1 SET false
t4                                                UPDATE id=2 SET false
t5             COMMIT
t6                                                COMMIT -> có thể bị 40001
```

Nếu cả hai đều commit, cuối cùng số bác sĩ trực là **0**, vi phạm bất biến. Nhưng trong bất kỳ lịch chạy **tuần tự** nào, transaction chạy sau sẽ quan sát chỉ còn một bác sĩ trực và không cho người cuối nghỉ. Do đó lịch mà cả hai cùng quyết định từ count=2 rồi commit là không serializable.

Ở một implementation SSI như PostgreSQL, database có thể phát hiện các phụ thuộc đọc/ghi và **abort ít nhất một transaction** trong kịch bản xung đột phù hợp. Giao dịch bị abort phải đọc lại count ở **một transaction mới**; lúc đó điều kiện nghiệp vụ có thể trả kết quả khác. Đây chính là lý do retry phải chạy lại **logic quyết định**, không đơn thuần gửi lại câu UPDATE.

### 2.1. Write skew khác lost update

- **Lost update**: hai transaction cập nhật cùng một dữ liệu theo cách một thay đổi có thể bị ghi đè.
- **Write skew**: hai transaction đọc một tập dữ liệu chung, sau đó cập nhật **những hàng khác nhau**, khiến một bất biến tổng thể bị phá vỡ dù không có row update trùng nhau.

Ví dụ bác sĩ trực là **write skew**. Nó giải thích vì sao chỉ khóa hoặc kiểm tra **hàng mình sắp UPDATE** chưa chắc bảo vệ được một bất biến liên quan nhiều hàng.

### 2.2. Phụ thuộc database

Các database không triển khai isolation theo cùng một cơ chế. Một mức tên `SERIALIZABLE` có thể đi kèm locking, optimistic validation, MVCC/SSI và các loại exception khác. PostgreSQL có lỗi `40001` tiêu chuẩn cho serialization failure; MySQL/InnoDB, SQL Server, Oracle hay H2 có thể có mẫu lỗi, cách phát hiện và chi phí khác.

Vì thế, một ví dụ JDBC/H2 mô phỏng exception **không chứng minh** behavior SSI của PostgreSQL. Bài này tách một minh họa SQL thực với PostgreSQL và một ví dụ Java dùng H2 để kiểm thử **cơ chế retry** một cách xác định.

## 3. Minh họa PostgreSQL thực với hai phiên làm việc

Phần này dành cho **PostgreSQL**, cần hai terminal `psql` kết nối **cùng một database**. Mỗi phiên là một connection riêng. Dùng một database thử nghiệm, không chạy trên dữ liệu production.

### 3.1. Chuẩn bị dữ liệu một lần, ngoài transaction tranh chấp

```sql
DROP TABLE IF EXISTS doctors;

CREATE TABLE doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO doctors(id, name, on_call)
VALUES (1, 'A', TRUE),
       (2, 'B', TRUE);
```

Chạy chuẩn bị trong một session và đợi commit/autocommit hoàn tất. Mở hai session mới hoặc hai kết nối song song.

### 3.2. Điều phối thứ tự hai session

**Session 1:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- 2; giữ transaction mở, chưa COMMIT
```

**Session 2:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- 2; giữ transaction mở, chưa COMMIT
```

Bây giờ cả hai đã đọc snapshot ban đầu trước khi bất kỳ session nào commit.

**Session 1:**

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 1;
COMMIT;
```

**Session 2:**

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 2;
COMMIT;
```

Trong lịch này, để tránh một kết quả không serializable, **một trong các transaction có thể bị hủy với SQLSTATE `40001`**. Thời điểm phát lỗi có thể là khi chạy lệnh ghi hoặc khi commit; thứ tự xử lý và session bị chọn abort phụ thuộc lịch thực tế và PostgreSQL. Nếu một session đã bị abort, không tiếp tục dùng transaction đó để thử ghi lại; kết thúc scope/rollback rồi mở transaction mới.

Có thể dùng `\set VERBOSITY verbose` trong `psql` để thấy SQLSTATE hoặc đọc thông tin lỗi do driver cung cấp; không dựa vào chính xác câu chữ lỗi vì thông điệp có thể thay đổi. Khi đã có một transaction commit, session retry phải bắt đầu bằng `BEGIN ... SERIALIZABLE` mới, đọc lại số người trực rồi quyết định có được cập nhật hay không.

### 3.3. Vì sao retry câu UPDATE đơn độc là sai?

Giả sử T1 commit trước, đánh dấu A nghỉ. T2 bị abort. Nếu T2 chỉ gửi lại:

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 2;
```

mà không đọc lại `COUNT(*)`, kết quả có thể vi phạm bất biến: cả A và B đều nghỉ. Quyết định “có thể cho B nghỉ” ban đầu dựa vào count=2 của **snapshot cũ**, không còn hợp lệ. Retry đúng phải chạy lại bước đọc, kiểm tra, rồi mới có quyền UPDATE trong transaction mới.

**Quy tắc bắt buộc:** Retry toàn bộ transaction *kể cả các phép đọc và tính toán quyết định SQL/value*. PostgreSQL không thể tự retry chung một giao dịch ở tầng server vì không thể biết business decision của ứng dụng đã phụ thuộc vào các kết quả đọc như thế nào.

## 4. Những loại lỗi nào nên được xem là retryable?

Với PostgreSQL:

| SQLSTATE | Tên lỗi | Cách xử lý điển hình |
| --- | --- | --- |
| `40001` | `serialization_failure` | **Retry toàn bộ transaction**, với giới hạn và chính sách backoff |
| `40P01` | `deadlock_detected` | Có thể retry toàn bộ transaction theo policy riêng |
| `23505` | `unique_violation` | **Không** tự retry mọi trường hợp; có thể là lỗi dữ liệu cố định hoặc một race tương tự serialization tùy logic |
| `23P01` | `exclusion_violation` | Chỉ cân nhắc retry nếu hiểu mối liên hệ với concurrent decision |
| `23503` | `foreign_key_violation` | Thường là vi phạm điều kiện dữ liệu; không tự retry vô điều kiện |
| `42601` | `syntax_error` | Lỗi câu SQL; retry y nguyên không sửa được |
| `28P01` | Authentication failure | Lỗi cấu hình/credential; không coi là serialization conflict |

**Phân biệt `40001` và `40P01`:** lỗi serialization khác deadlock, dù cả hai đều thuộc nhóm lỗi transaction rollback ở PostgreSQL. Nhiều hệ thống retry cả hai, nhưng việc mở rộng tập retry cần dựa trên cơ chế DB/driver và business semantics, không phải bắt mọi `RuntimeException`.

**Phân biệt SQLSTATE với message:** text kiểu “could not serialize access due to concurrent update” là thông báo dễ đọc nhưng không ổn định như SQLSTATE. Với PostgreSQL, hãy ưu tiên `SQLException.getSQLState()` từ nguyên nhân gốc hoặc bộ phân loại exception của data-access layer.

### 4.1. Spring có dịch SQLException sang exception riêng

Spring JDBC sử dụng exception translation để chuyển nhiều `SQLException` thành các subclass của `DataAccessException`. Một số lỗi concurrency/locking được ánh xạ sang các lớp như `PessimisticLockingFailureException`, `CannotAcquireLockException` hoặc subclass khác tùy translator, driver và version.

Không giả định **mọi** lỗi `40001` trong mọi Spring version luôn thành đúng **một** Java exception class, đặc biệt khi lỗi phát ra ở `commit()` thay vì `JdbcTemplate.update()`. `CannotSerializeTransactionException` là một kiểu cũ đã được Spring đánh dấu deprecated từ 6.0.3; không nên xây một retry policy chỉ phụ thuộc duy nhất tên class đó.

Một chiến lược chẩn đoán PostgreSQL là duyệt cause chain để tìm `SQLException` có SQLSTATE `40001`; trong hệ thống thực tế cũng cần kiểm tra cách connection pool, ORM, JPA hoặc transaction manager wrap exception. Nếu có `SQLException.getNextException()`, nhiều driver còn chứa thông tin bổ sung theo chuỗi đó.

### 4.2. Không retry lỗi mà ta không hiểu

Nếu code làm:

```java
catch (Exception ex) {
    // thử lại toàn bộ method với bất kỳ lỗi nào
}
```

đây là **fragment minh họa cách sai**, không phải đoạn code nên dùng. Nó có thể lặp lại exception nghiệp vụ (không đủ tiền, dữ liệu sai), lỗi SQL syntax, lỗi quyền, hoặc gọi HTTP nhiều lần. Retry nên là một **chính sách có điều kiện**, không phải cơ chế che mọi lỗi.

## 5. Bắt retry ở đâu trong Spring?

Mô hình đúng:

```text
Caller
  |
  v
RetryCoordinator (ngoài transaction)
  |
  +-- attempt 1:
  |      begin NEW SERIALIZABLE transaction T1
  |      đọc lại dữ liệu, kiểm tra quy tắc, ghi DB
  |      commit T1 hoặc rollback T1 khi 40001
  |
  +-- nếu 40001 và còn ngân sách:
  |      backoff (+ jitter), rồi attempt 2
  |      begin NEW SERIALIZABLE transaction T2
  |      đọc lại dữ liệu, tính lại, ghi DB
  |      commit T2 hoặc rollback T2
  |
  +-- nếu commit thành công -> trả kết quả
  +-- nếu hết ngân sách -> báo lỗi, không nhận là đã commit
```

**Retry ở ngoài transaction boundary.** Điều này quan trọng vì một transaction đã bị database đánh dấu aborted/rollback-only không thể trở thành transaction mới chỉ bằng cách chạy lại câu SQL trong `catch`.

### 5.1. `TransactionTemplate`: an toàn về thứ tự begin/commit/rollback

Với imperative Spring transaction:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
        TransactionDefinition.ISOLATION_SERIALIZABLE);

for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        template.executeWithoutResult(status -> {
            // đọc lại, kiểm tra, thực hiện toàn bộ công việc DB
        });
        break;
    } catch (RuntimeException ex) {
        // chỉ retry nếu đã xác minh lỗi serialization/deadlock phù hợp
        // các exception khác phải được ném ra
    }
}
```

Đây là **cấu trúc minh họa**, chưa có logic xác định retry và backoff. `TransactionTemplate` tự đảm nhận lifecycle, đảm bảo callback lỗi thì rollback trước khi lỗi thoát ra khỏi `executeWithoutResult`. Khi lỗi phát sinh ở giai đoạn commit, exception cũng thoát ra ngoài lời gọi `execute...` để retry coordinator phân loại. `REQUIRES_NEW` tạo physical transaction riêng cho mỗi lượt nếu dùng manager/resource phù hợp.

**Đừng** để một `@Transactional(REQUIRED)` bên ngoài ôm toàn bộ vòng lặp và chỉ gọi repository bên trong rồi nghĩ mỗi vòng có một physical transaction mới. Khi cùng tham gia T1, các lần thử vẫn chịu cùng snapshot/rollback-only context của T1.

### 5.2. Declarative `@Transactional`: tách hai Spring beans

```java
@Service
public class RetryCoordinator {
    private final TxWorker worker;

    public RetryCoordinator(TxWorker worker) {
        this.worker = worker;
    }

    public void submit() {
        // vòng lặp retry ở đây, không đặt @Transactional lên submit()
        worker.executeOneAttempt();  // lời gọi qua proxy bean khác
    }
}

@Service
public class TxWorker {
    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void executeOneAttempt() {
        // đọc, kiểm tra và ghi dữ liệu cho một attempt
    }
}
```

Đây là **fragment minh họa**, thiếu vòng lặp/DAO/imports và chưa phải chương trình độc lập. Ý chính: `RetryCoordinator` là bean ngoài transaction, `TxWorker` là bean khác được gọi qua **Spring proxy**, và mỗi attempt có transaction riêng. Exception khi commit có thể xuất hiện **sau khi method target đã return nhưng trước khi lời gọi proxy trả về**; vì vậy retry coordinator bên ngoài proxy là nơi có thể bắt được lỗi ở cả business execution lẫn commit.

Nếu `RetryCoordinator` gọi `this.executeOneAttempt()` trên cùng bean, proxy mode bỏ qua advice của inner method; `REQUIRES_NEW` có thể không được áp dụng. Phải xử lý rõ self-invocation, injection và AOP order.

### 5.3. Dùng Spring Retry / `@Retryable`

Một ứng dụng có thể dùng Spring Retry, retry library khác hoặc `RetryTemplate`, nhưng thư viện retry **không mặc nhiên thay transaction manager**. Cần kiểm tra thứ tự các advice:

- **Retry advice ngoài transaction advice:** mỗi attempt đi vào transaction boundary mới; đây thường là cấu hình mong muốn.
- **Retry advice bên trong transaction advice:** toàn bộ vòng lặp có thể dùng một physical transaction đã bị đánh dấu rollback-only; đó là cấu trúc sai đối với serialization failure.

Không dựa vào mặc định thứ tự advisor khi chưa xác minh version/config. Có thể tách coordinator và transactional worker ra hai bean như ở trên để cơ chế rõ ràng, hoặc dùng `TransactionTemplate` tạo transaction mới cho từng lần.

## 6. Retry phải bao gồm phần tính toán điều kiện nghiệp vụ

Retry chỉ câu lệnh SQL thất bại không đủ:

```text
SAI:
  kiểm tra số lượng còn lại một lần
  nếu đủ thì:
      LOOP retry(UPDATE ...)
```

Đúng hơn:

```text
ĐÚNG:
  LOOP attempt:
      BEGIN SERIALIZABLE transaction mới
      SELECT dữ liệu hiện hành
      áp dụng lại quy tắc nghiệp vụ
      tính lại quyết định/tham số cập nhật
      UPDATE/INSERT theo quyết định mới
      COMMIT
      nếu 40001 -> rollback/đóng attempt; backoff; chạy lại từ SELECT
```

Điểm tinh tế: ngay cả **các tham số SQL** chọn trong Java cũng có thể phụ thuộc vào dữ liệu đã đọc. Nếu lần retry chỉ dùng lại giá trị tính từ snapshot cũ, việc retry câu lệnh có thể vẫn sai nghiệp vụ dù transaction thứ hai commit thành công.

Ví dụ với hệ thống đặt chỗ:

- Attempt 1 đọc phòng A còn trống, định đặt A.
- Attempt 1 bị `40001` vì transaction đồng thời thay đổi trạng thái phòng.
- Attempt 2 phải truy vấn lại trạng thái phòng A và phương án thay thế; không thể tự gửi lại `UPDATE room A` mà bỏ kiểm tra.

Tương tự với số dư, kho hàng, định giá theo tồn kho, phát vé cuối cùng hoặc quy tắc tổng số hàng hợp lệ.

## 7. Ví dụ Java 17 chạy độc lập: transaction retry đúng boundary

### 7.1. Mục tiêu và giới hạn kiểm chứng

Ví dụ này dùng **Java 17+**, **Spring Framework 6.2.19**, **Spring JDBC**, **H2 in-memory 2.3.232** và **Maven 3.9+**.

Chúng ta cần một bài test **lặp lại được với output ổn định**. Vì H2 không phải PostgreSQL SSI, chương trình **cố tình tạo một exception giả lập có nguyên nhân `SQLException` với SQLSTATE `40001` ở attempt 1**. Nó kiểm tra được:

1. `TransactionTemplate` tạo một transaction `SERIALIZABLE` riêng cho từng attempt.
2. SQL đã chạy trong attempt 1 **rollback** khi exception thoát callback.
3. Retry coordinator **ở ngoài** transaction mở attempt 2 và **đọc lại dữ liệu**.
4. Attempt 2 commit; final balances chính xác và không bị trừ tiền hai lần.

Đây là test **cơ chế rollback + retry**, không chứng minh H2 phát hiện một serialization anomaly thật hay PostgreSQL sẽ luôn lỗi ở thời điểm cụ thể. Một test xung đột thực tế với PostgreSQL được mô tả ở phần 3.

### 7.2. Cấu trúc dự án

```text
serializable-retry-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SerializableRetryDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>serializable-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong ví dụ, `spring-context` cung cấp Java configuration/IoC, `spring-jdbc` cung cấp `JdbcTemplate`, `DriverManagerDataSource`, `JdbcTransactionManager` và các dependency transaction tương ứng. H2 là database chỉ dùng khi chạy.

### 7.3. Mã Java đầy đủ

File `src/main/java/demo/SerializableRetryDemo.java`:

```java
package demo;

import java.sql.SQLException;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class SerializableRetryDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:serializable_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SerializableRetryDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO wallet(id, balance) VALUES (1, 100), (2, 50)");

            System.out.println("BEFORE=" + balances(jdbc));

            TransactionTemplate template = new TransactionTemplate(manager);
            template.setIsolationLevel(
                    TransactionDefinition.ISOLATION_SERIALIZABLE);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            template.setTimeout(10);

            transferWithRetry(template, jdbc, 10);

            System.out.println("AFTER=" + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 2", Integer.class);
        return "A=" + a + ", B=" + b;
    }

    private static void transferWithRetry(
            TransactionTemplate template, JdbcTemplate jdbc, int amount) {

        final int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            final int current = attempt;

            try {
                template.executeWithoutResult(status -> {
                    System.out.println("ATTEMPT=" + current);

                    // Quyết định phải được tính lại trong MỖI transaction.
                    int source = jdbc.queryForObject(
                            "SELECT balance FROM wallet WHERE id = 1",
                            Integer.class);

                    if (source < amount) {
                        throw new IllegalStateException(
                                "insufficient balance");
                    }

                    jdbc.update(
                            "UPDATE wallet SET balance = balance - ? "
                            + "WHERE id = 1", amount);

                    if (current == 1) {
                        // Lỗi tổng hợp có SQLSTATE 40001 để test retry.
                        // Không phải PostgreSQL concurrency thật.
                        SQLException sql = new SQLException(
                                "simulated serialization failure", "40001");

                        throw new IllegalStateException(
                                "synthetic transaction abort", sql);
                    }

                    jdbc.update(
                            "UPDATE wallet SET balance = balance + ? "
                            + "WHERE id = 2", amount);
                });

                System.out.println("COMMITTED_ATTEMPT=" + current);
                return;
            } catch (RuntimeException ex) {
                boolean serialization = hasSqlState(ex, "40001");

                if (!serialization || current == maxAttempts) {
                    throw ex;
                }

                System.out.println("RETRY_40001_AFTER=" + current);
            }
        }
    }

    private static boolean hasSqlState(Throwable failure, String state) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }
}
```

`@Configuration` chỉ khai báo các beans; demo dùng `TransactionTemplate` **programmatic**, nên không bắt buộc có `@EnableTransactionManagement` hoặc Spring AOP proxy để điều khiển callback transaction.

### 7.4. Lệnh chạy

Tại thư mục `serializable-retry-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SerializableRetryDemo
```

Các dòng **do chương trình tự in** (không tính log Maven/Spring):

```text
BEFORE=A=100, B=50
ATTEMPT=1
RETRY_40001_AFTER=1
ATTEMPT=2
COMMITTED_ATTEMPT=2
AFTER=A=90, B=60
```

### 7.5. Đọc từng bước của output

**Attempt 1:**

- `template.executeWithoutResult` bắt đầu T1 mới với requested isolation `SERIALIZABLE`.
- Callback đọc lại balance A=100, xác nhận đủ 10 đơn vị và thực hiện `UPDATE A -= 10`.
- Exception tổng hợp có nguyên nhân `SQLException(..., "40001")` thoát khỏi callback.
- `TransactionTemplate` xử lý rollback T1 **trước khi** coordinator bắt exception.
- Coordinator nhận diện SQLSTATE `40001` trong cause chain và còn ngân sách retry, nên in `RETRY_40001_AFTER=1`.

**Attempt 2:**

- Một transaction T2 mới bắt đầu; callback **truy vấn lại** balance A từ DB. Vì T1 đã rollback, A vẫn là 100.
- Không tạo synthetic exception lần này; thực hiện cả `UPDATE A -= 10` và `UPDATE B += 10`.
- Callback return bình thường, `TransactionTemplate` commit T2; coordinator in `COMMITTED_ATTEMPT=2`.

**Kết quả cuối:** A=90, B=60. Nếu T1 không rollback đúng, kết quả có thể bị trừ tiền sai. Vì vậy ví dụ chứng minh cả transaction boundary và cơ chế retry đã được đặt đúng.

`hasSqlState` dùng ở demo là bộ dò tối giản theo **cause chain**; production có thể cần xử lý JDBC `SQLException.getNextException()`, exception translation của JPA/provider và phân loại các lỗi commit không có nguyên nhân SQLSTATE trực tiếp. Tuyệt đối không suy ra mọi `IllegalStateException` đều retryable: trong ví dụ chỉ lỗi có SQLSTATE cụ thể mới được thử lại.

### 7.6. Vì sao chọn exception tổng hợp?

H2 trong bài này không được dùng làm hệ DB phát sinh xung đột SSI thực. Nếu cố chạy hai thread rồi kỳ vọng một SQLSTATE `40001` ở mọi máy, kết quả có thể phụ thuộc timing và cơ chế isolation của H2. Chèn lỗi tổng hợp vào **sau câu UPDATE đầu tiên nhưng trước câu UPDATE thứ hai** tạo một bài test ổn định cho rollback/retry.

Đối với production PostgreSQL, thay phần synthetic exception bằng **lỗi thực tế do DB/driver báo**; test integration dùng hai transaction đồng thời như phần 3. Không giữ cơ chế giả lập lỗi trong code nghiệp vụ thật.

## 8. Retry policy cho production: giới hạn, backoff, jitter, deadline

Một vòng retry nghiêm túc có ít nhất bốn giới hạn:

1. **Tối đa số attempt:** ví dụ 3 hoặc 5, tùy SLO/độ cạnh tranh; không có vòng lặp vô hạn.
2. **Tổng thời gian retry:** đảm bảo caller/request còn đủ deadline; mỗi transaction riêng có timeout **không đồng nghĩa** toàn bộ chuỗi retry luôn nằm trong giới hạn đó.
3. **Backoff:** chờ tăng dần giữa các lần thử để các transaction không liên tục xung đột cùng thời điểm.
4. **Jitter:** thêm ngẫu nhiên có giới hạn để nhiều client không retry đồng loạt.

Ví dụ snippet Java 17 để tạo độ trễ, chỉ dùng **sau khi transaction trước đã rollback/đóng**:

```java
long baseMillis = 20L;
long capMillis = 250L;
long maxBackoff = Math.min(capMillis,
        baseMillis << Math.min(attempt - 1, 4));

long pause = java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(maxBackoff + 1);

try {
    Thread.sleep(pause);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("retry interrupted", ex);
}
```

Đây là **fragment**, `attempt` phải là số attempt dương trong vòng lặp bên ngoài. Công thức trên chỉ minh họa bounded backoff với jitter; tùy tải hệ thống nên dùng retry policy chung, metrics và deadline thay vì copy y nguyên magic numbers.

Không ngủ `Thread.sleep` **bên trong** transaction đang giữ connection/lock vì sẽ kéo dài contention. Khi đã nhận `40001`, điều phối xong rollback rồi mới backoff và mở transaction mới.

### 8.1. Bắt lỗi commit đúng ranh giới

Một serialization failure có thể xuất hiện trong SQL của callback **hoặc lúc commit**. Nếu retry được đặt bên trong một `@Transactional` method và method return trước khi proxy commit, retry code bên trong target không bắt được lỗi commit. Đặt retry **bên ngoài lời gọi transaction boundary**, như `TransactionTemplate.execute...` hoặc coordinator gọi transactional worker qua proxy.

### 8.2. Không bao phủ cả HTTP request bằng một transaction dài

Một request có thể làm validation, đọc input, gọi dịch vụ ngoài, rồi mới ghi DB. Chỉ phần **thực sự cần một snapshot và commit nguyên tử** nên nằm trong SERIALIZABLE transaction. Giữ transaction ngắn giúp giảm thời gian giữ resource, contention và xác suất conflict.

Nếu các phép đọc nghiệp vụ quyết định SQL, chúng phải nằm trong phần transaction được retry. Các thao tác chuẩn bị độc lập với snapshot có thể ở bên ngoài.

### 8.3. Retry exhaustion phải được báo đúng

Nếu hết ngân sách, phải propagate lỗi hoặc chuyển thành kết quả thất bại rõ ràng; không trả “đã xử lý thành công” khi transaction cuối cùng chưa commit. Caller có thể trả HTTP status phù hợp với API contract (ví dụ lỗi tạm thời cho client retry có idempotency key) và ghi metrics để điều chỉnh tải.

## 9. Idempotency và side effects: điều kiện để retry an toàn

Một lần retry giao dịch DB không nên khiến người dùng bị:

- Trừ tiền nhiều lần.
- Tạo nhiều đơn hàng từ cùng một yêu cầu.
- Gửi hai email xác nhận.
- Gọi một API thanh toán bên ngoài hai lần.
- Phát hai event cho downstream consumer.

### 9.1. Tách side effect khỏi retryable transaction

Mô hình khuyến nghị:

```text
Retry coordinator
   |
   +--> BEGIN SERIALIZABLE transaction Tn
          |
          +-- kiểm tra business state
          +-- áp dụng thay đổi DB
          +-- ghi outbox event vào CÙNG transaction DB
          |
          +-- COMMIT hoặc ROLLBACK
   |
   +--> thành công mới cho phép outbox publisher gửi message
```

Outbox record commit cùng dữ liệu kinh doanh; transaction bị `40001` rollback thì record outbox của attempt đó cũng biến mất. Publisher ngoài transaction gửi sau commit, cần idempotency/at-least-once processing cho delivery. Việc chỉ đặt `@Transactional` quanh code gửi email không khiến email có thể rollback.

### 9.2. Idempotency key cho mỗi yêu cầu

Nếu client gửi lại cùng một yêu cầu sau timeout mạng, **kết quả commit trước đó có thể không được client biết chắc**. Lỗi mất kết nối trong giai đoạn commit không giống `40001` có nghĩa transaction bị abort. Do đó không được retry mù mọi lỗi kết nối rồi giả định chắc chắn giao dịch trước chưa commit.

Dùng `request_id`/idempotency key và bảng trạng thái/unique constraint đặt trong DB giúp xử lý việc nhận lại cùng request mà không lặp business effect.

### 9.3. Dữ liệu tính toán phải được tính lại, nhưng input yêu cầu giữ ổn định

Có hai nhóm dữ liệu:

- **Input cố định của yêu cầu:** request id, người dùng, số tiền mong muốn, giới hạn/phương án do caller chấp thuận.
- **Dữ liệu phụ thuộc snapshot:** số dư hiện tại, số lượng còn trống, giá theo chính sách hiện hành, thứ tự cấp phát, điều kiện còn đủ tài nguyên.

Khi retry, giữ input yêu cầu nhất quán nhưng **đọc và tính lại dữ liệu phụ thuộc snapshot** trong transaction mới.

## 10. JDBC/JPA và Spring exceptions: phân loại có chủ đích

### 10.1. JDBC và `JdbcTemplate`

`JdbcTemplate` tham gia Spring-managed transaction nếu dùng datasource mà transaction manager đang quản lý. Một `JdbcTransactionManager` bao quanh local JDBC transaction; JDBC driver cung cấp `SQLException` với SQLSTATE, Spring exception translation có thể bao gói thành `DataAccessException`.

Một lỗi có thể đi theo chuỗi:

```text
PostgreSQL server
   -> JDBC SQLException(SQLSTATE 40001)
   -> Spring DataAccessException hoặc transaction exception
   -> retry coordinator ngoài transaction boundary
```

Đừng chỉ bắt class `CannotSerializeTransactionException` cũ đã deprecated. Với PostgreSQL, SQLSTATE là tín hiệu chuẩn quan trọng. Với nhiều provider, cần xác nhận mapping thực tế bằng integration test; một lỗi ném ở commit có thể được wrap khác lỗi từ `JdbcTemplate.update`.

### 10.2. JPA/Hibernate

Một JPA transaction `SERIALIZABLE` chỉ được cấu hình thật nếu `JpaTransactionManager`/provider/backend hỗ trợ điều khiển isolation cho physical transaction. Một annotation trên inner method chỉ join transaction ngoài có thể **không** thay isolation.

`flush()` không đồng nghĩa `commit()`: lỗi serialization hoặc constraint có thể lộ ra khi flush, nhưng cũng có thể đến tận commit mới rõ. Retry phải đặt **ngoài** JPA transaction boundary và tái tạo persistence context/snapshot thích hợp; đừng dùng tiếp `EntityManager` của transaction đã rollback như thể nó sạch.

### 10.3. Spring Test và transaction tự rollback

Một test class hoặc test method có `@Transactional` có thể được Spring Test bao quanh bởi transaction của framework. Khi đó method bạn tưởng đang mở transaction `SERIALIZABLE` riêng có thể đang **join** test transaction với isolation khác.

Để test retry thật, cần caller ngoài transaction, transaction manager cấu hình đúng, hai connection/threads hoặc sessions phù hợp; quan sát commit và trạng thái DB sau transaction boundary chứ không chỉ metadata trong method.

## 11. Phân biệt SERIALIZABLE với READ COMMITTED và REPEATABLE READ

| Mức cô lập | Mục tiêu chính | Điều cần lưu ý |
| --- | --- | --- |
| `READ_COMMITTED` | Mỗi statement chỉ thấy dữ liệu đã commit phù hợp với snapshot của statement | Giữa các statement có thể quan sát dữ liệu mới; một số read-then-write invariants cần khóa/version check |
| `REPEATABLE_READ` | Snapshot ổn định hơn trong transaction, tùy DB | Không đồng nghĩa tránh mọi write skew ở mọi DB; PostgreSQL `REPEATABLE READ` tương ứng snapshot isolation |
| `SERIALIZABLE` | Kết quả những transaction commit tương đương một lịch tuần tự | Có thể abort transaction để tránh serialization anomalies; application phải sẵn sàng retry |

Các mức trong Java/Spring là **yêu cầu tới backend**. Chi tiết triển khai khác nhau giữa database vendors; không chuyển kết luận riêng của PostgreSQL SSI thành luật chung cho mọi hệ quản trị.

### 11.1. Có phải SERIALIZABLE lúc nào cũng đáng dùng?

Không. SERIALIZABLE hữu ích khi business invariant phụ thuộc các phép đọc và ghi nhiều record, khó bảo đảm bằng một unique constraint, optimistic version hoặc row-level locking đơn giản. Nhưng nó có chi phí phát hiện conflict, abort/retry, tăng thời gian xử lý khi tải cao và độ phức tạp trong idempotency.

Có những trường hợp `READ_COMMITTED` + atomic SQL (`UPDATE ... WHERE balance >= ?`), unique constraint hoặc version column đạt mục tiêu với chi phí thấp hơn. Chọn isolation theo **invariant cần bảo vệ** và test concurrency, không theo suy nghĩ “càng cao luôn càng tốt”.

### 11.2. Serializable không thay thế constraint

Database `UNIQUE`, `CHECK`, foreign key và điều kiện `WHERE` có thể bảo vệ những bất biến cụ thể hiệu quả hơn. Isolation xử lý tương tác giữa transaction; constraint xử lý tính hợp lệ của dữ liệu. Hệ thống quan trọng thường cần cả hai.

## 12. Những lỗi lập trình phổ biến

### Lỗi 1 — Retry câu SQL thay vì toàn bộ logic

Đây là lỗi nguy hiểm nhất. `UPDATE` lặp lại có thể dùng điều kiện được tính từ snapshot cũ. Cần bắt đầu transaction mới và thực hiện lại `SELECT`, validation, lựa chọn tham số và write.

### Lỗi 2 — Bắt `40001` bên trong transaction, sau đó thử tiếp trên connection đó

Database có thể đã đánh dấu transaction là aborted. Chạy SQL tiếp trong cùng transaction có thể dẫn tới lỗi “current transaction is aborted” hoặc các trạng thái manager rollback-only. Hãy thoát transaction boundary để rollback/cleanup rồi mới retry.

### Lỗi 3 — `@Transactional` bao ngoài toàn bộ vòng retry

Nếu retry loop nằm trong một method đã có T1, các lần thử vẫn chia sẻ physical transaction, snapshot và rollback-only state. Retry coordinator nên ở ngoài boundary; dùng separate transactional worker hoặc `TransactionTemplate` tạo transaction mới từng attempt.

### Lỗi 4 — Self-invocation làm `REQUIRES_NEW` không có hiệu lực

Trong Spring proxy mode, `this.executeOneAttempt()` không đi qua transaction proxy, vì vậy annotation riêng trên method inner không tạo T2 như mong đợi. Tách worker sang bean khác và gọi qua Spring-managed proxy.

### Lỗi 5 — Chỉ catch một subclass Spring cũ

Exception mapping tùy Spring version, driver và điểm lỗi (query hoặc commit). Dựa vào một tên subclass deprecated dễ bỏ sót trường hợp. Với PostgreSQL nên kiểm tra SQLSTATE qua cause chain hoặc một error classifier đã được integration-test.

### Lỗi 6 — Retry mọi lỗi SQL, kể cả constraint cố định

Một unique violation cố định sẽ tiếp tục thất bại; syntax/permission errors không tự khỏi. Chỉ retry các lỗi có policy rõ và business operation retry-safe.

### Lỗi 7 — Không giới hạn số lần và thời gian retry

Khi contention cao, vòng retry vô hạn có thể làm hệ thống càng quá tải. Dùng max attempts, overall deadline, backoff + jitter, metrics và fallback lỗi rõ ràng.

### Lỗi 8 — Giữ transaction mở trong lúc backoff

`Thread.sleep()` bên trong transaction giữ connection/locks/snapshot lâu hơn, khiến conflict tệ hơn. Delay phải nằm **sau rollback hoặc commit failure đã được xử lý** và trước transaction mới.

### Lỗi 9 — Side effect bên ngoài DB bị nhân đôi

Email, HTTP call, message publish hoặc charge bên ngoài DB không rollback cùng T1. Tách side effects; dùng outbox, idempotency keys và cơ chế bù trừ.

### Lỗi 10 — Tin mọi serialization failure xảy ra ở câu UPDATE

Một số lỗi xuất hiện **lúc COMMIT**. Nếu catch chỉ bao quanh repository method target bên trong transaction, lỗi commit có thể lọt ra ngoài và không được retry. Catch ngoài `TransactionTemplate.execute...` hoặc ngoài proxy call.

### Lỗi 11 — Nghĩ SERIALIZABLE cấm toàn bộ hoạt động song song

PostgreSQL SSI thường cho phép concurrent execution và hủy một transaction khi cần; nó không đơn thuần tuần tự hóa mọi query qua một khóa toàn cục. Thiết kế capacity dựa trên contention/abort rate thật.

### Lỗi 12 — Gọi `setRollbackOnly()` rồi tiếp tục tin kết quả cũ

`setRollbackOnly()` là dấu hiệu transaction không được commit thành công. Dữ liệu đọc hoặc object tính toán trong scope bị rollback không nên được publish như kết quả đã lưu. Retry phải xử lý lại business logic trên transaction mới.

### Lỗi 13 — Nghi ngờ H2 demo không có `40001` tự nhiên rồi kết luận retry code vô dụng

Demo H2 dùng synthetic SQLSTATE để **kiểm thử retry coordinator và rollback** một cách xác định. PostgreSQL SSI có thuật toán concurrency riêng; muốn kiểm thử 40001 thật cần PostgreSQL và lịch chạy đồng thời như phần 3.

### Lỗi 14 — Kiểm tra `@Transactional(isolation=SERIALIZABLE)` ở một method đang join

Nếu outer đã mở T1 ở isolation khác, inner `REQUIRED` không nâng physical isolation. Cần đặt isolation ở boundary bắt đầu T1, hoặc tách T2 với `REQUIRES_NEW` nếu đúng semantics. Một số manager cho phép `setValidateExistingTransaction(true)` để phát hiện isolation mismatch và từ chối participation.

### Lỗi 15 — Nhầm serialization failure với optimistic-lock failure

JPA `OptimisticLockingFailureException`/`OptimisticLockException` vì `@Version` là một tín hiệu concurrency khác. Nó có thể có chính sách retry riêng, nhưng **không mặc nhiên** là PostgreSQL SQLSTATE `40001` hoặc vấn đề SERIALIZABLE. Đừng gộp hai nhóm exception chỉ vì cả hai có thể xuất hiện khi nhiều user cập nhật dữ liệu.

## 13. Quan sát và đo lường trong production

Một cơ chế retry muốn vận hành ổn định nên theo dõi:

- Tổng số transaction SERIALIZABLE bắt đầu, commit và abort.
- Số lỗi `40001`, `40P01`, phân tách theo operation và endpoint (không đưa dữ liệu nhạy cảm vào nhãn).
- Số attempt trung bình, tỷ lệ retry thành công, tỷ lệ hết ngân sách.
- Transaction duration, lock wait, DB connection pool saturation.
- Tổng latency của request, bao gồm backoff và repeated SQL.
- Các tình huống idempotency duplicate/suppressed, outbox delivery và retry phía client.
- Throughput và conflict hotspot trên bảng/hàng/predicate liên quan.

Một lưu ý: **không in toàn bộ exception SQL, query parameter nhạy cảm hoặc thông tin cá nhân** vào production logs. Dùng error code, trace id và metric labels có cardinality hợp lý.

### 13.1. Phân biệt retry thành công và giao dịch bị mất kết quả commit

`40001` báo transaction bị rollback vì serialization failure, phù hợp để retry. Một lỗi mạng sau khi gửi `COMMIT` có thể khiến client **không biết chắc** DB đã commit hay chưa. Trường hợp “outcome unknown” cần idempotency/reconciliation; retry blind có thể tạo kết quả kép.

### 13.2. Retry storm

Nếu hàng nghìn client cùng retry ngay lập tức sau conflict, số transaction đang tranh chấp có thể tăng. Bounded exponential backoff với jitter và rate limiting giúp tản tải. Một số điểm nóng quá cao nên xử lý bằng đổi mô hình dữ liệu, giảm transaction duration hoặc phân vùng workload, không chỉ tăng maxAttempts.

## 14. Kịch bản kiểm thử quan trọng

1. **Đường không có xung đột:** một SERIALIZABLE transaction bắt đầu, đọc và ghi, commit; kiểm tra dữ liệu.
2. **Một serialization failure:** inject lỗi `40001` sau một update; xác minh attempt đầu rollback và attempt sau commit một lần.
3. **Lỗi ở commit:** tạo test double hoặc integration test manager/DB để exception xuất hiện khi `commit`; kiểm tra retry coordinator vẫn bắt được.
4. **Hết attempts:** liên tục inject `40001`; xác minh method báo lỗi, không nhận là thành công và không để partial DB writes.
5. **Lỗi không retryable:** ném `IllegalArgumentException` hoặc SQL syntax error; xác minh chỉ chạy một attempt.
6. **Dữ liệu thay đổi giữa attempts:** thay đổi DB sau lần fail; xác minh lần sau **đọc lại và tính lại điều kiện**.
7. **PostgreSQL thực:** dùng hai session như ví dụ bác sĩ trực; kiểm chứng có `40001` và invariant được giữ.
8. **Sai transaction boundary:** cố tình gọi worker bằng `this.method()`/`REQUIRED` join outer; test phải phát hiện không có transaction mới đúng ý.
9. **Outbox/idempotency:** một request bị retry không tạo nhiều business records hoặc gửi side effect sai.
10. **Quá tải:** đo retry success, contention và latency tại tần suất write đồng thời giống production.

Chỉ kiểm tra `TransactionStatus.isNewTransaction()` không đủ chứng minh isolation thật; kết hợp kiểm tra `Connection.getTransactionIsolation()` (với JDBC) và concurrency tests trên đúng database. Khi dùng Spring Test có test-level `@Transactional`, chú ý transaction test có thể bao bên ngoài làm thay đổi propagation của service đang thử.

### 14.1. Test PostgreSQL ở môi trường đúng

Để có bằng chứng SSI thật, dùng PostgreSQL version ứng dụng triển khai, hai connection riêng, điều khiển lịch đọc/ghi bằng barrier và xác minh SQLSTATE `40001`. Tránh viết test race chỉ dùng `Thread.sleep` rồi mong đúng cùng một thread luôn thắng; synchronization/barrier hoặc manual two-session script có tính giải thích tốt hơn.

## 15. Những câu hỏi thường gặp

**Hỏi: `SERIALIZABLE` nghĩa là không còn anomaly, vậy vì sao vẫn có exception?**

Vì database phải chọn giữa cho commit một lịch sai và **abort một transaction** để giữ tính đúng. Exception là một cơ chế thực thi bảo đảm serializability, không phải sự phủ nhận của bảo đảm đó.

**Hỏi: Cứ retry `40001` một lần là đủ?**

Không. Contention có thể tiếp diễn; dùng retry budget và backoff. Số attempts tối ưu phụ thuộc workload và SLO.

**Hỏi: Retry phải đọc lại dữ liệu dù câu SQL ban đầu không thay đổi?**

Có, nếu các quyết định nghiệp vụ hoặc tham số query đã dựa vào snapshot cũ. PostgreSQL khuyến nghị retry **toàn bộ logic quyết định SQL và values** trong transaction mới.

**Hỏi: Có thể retry chỉ phương thức repository con đang lỗi?**

Không nên nếu repository con chỉ là một phần của transaction lớn. Retry phải bao trùm **transaction boundary thật** và các phép đọc tính toán có liên quan. Nếu repository là toàn bộ đơn vị transactional độc lập, có thể tổ chức retry ở phía ngoài đơn vị đó.

**Hỏi: Có thể bắt SQLException và `Thread.sleep` ngay trong `@Transactional` rồi chạy lại?**

Không phải cấu trúc an toàn. Transaction có thể bị đánh dấu aborted, sleep giữ tài nguyên và lại dùng snapshot cũ. Hãy thoát boundary, rollback/cleanup, rồi mới delay và tạo transaction mới.

**Hỏi: Có cần `REQUIRES_NEW` không?**

Không bắt buộc nếu retry coordinator thực sự ở ngoài mọi transaction và mỗi callback/method tạo transaction mới bằng `REQUIRED`. Dùng `REQUIRES_NEW` khiến ý định transaction riêng cho từng attempt tường minh, nhưng có chi phí khi bị gọi từ scope ngoài đang active; thiết kế tránh outer transaction ôm retry loop.

**Hỏi: `23505` có thể retry được không?**

Trong một số trường hợp cạnh tranh chọn key sau khi đọc DB, lỗi unique violation có thể liên quan tới một tình huống concurrency. Nhưng `23505` cũng có thể là input vi phạm cố định. Không retry vô điều kiện; phải phân biệt theo business flow.

**Hỏi: H2 example in ra `RETRY_40001_AFTER=1` có chứng minh PostgreSQL phát sinh lỗi thực tế không?**

Không. Ví dụ dùng một synthetic `SQLException(SQLSTATE 40001)` để kiểm tra rollback và retry. Để kiểm chứng PostgreSQL SSI phải chạy test hai session với PostgreSQL thật.

**Hỏi: Serializable có bảo đảm giao dịch bên ngoài, như gửi email, được rollback không?**

Không. Isolation chỉ áp dụng cho transaction resource do manager điều phối. Side effects ngoài đó cần outbox/idempotency/compensation.

**Hỏi: Trong reactive R2DBC có dùng cùng code `TransactionTemplate` không?**

Không. `TransactionTemplate` là API imperative. Với reactive execution cần `ReactiveTransactionManager` và `TransactionalOperator`, dùng Reactor Context, và đặt resubscription/retry ngoài reactive transaction boundary tương thích; không trộn thread-local JDBC context với reactive pipeline.

## 16. Checklist áp dụng vào một dự án Spring

Trước khi bật SERIALIZABLE cho một operation:

- Xác định invariant nào cần bảo vệ và vì sao isolation thấp hơn, constraint, atomic SQL hay optimistic lock chưa đủ.
- Kiểm tra đúng **Spring transaction manager**, datasource/persistence unit và hỗ trợ isolation của backend.
- Xác nhận method được AOP advice chặn và là **boundary bắt đầu physical transaction mới**; tránh inner `REQUIRED` join một outer khác isolation.
- Đặt tất cả SQL reads và business decisions liên quan **bên trong** phạm vi sẽ retry.
- Xây retry coordinator **bên ngoài transaction**, để mỗi attempt có begin/commit/rollback riêng.
- Nhận diện `40001` (và các mã khác có policy cụ thể) bằng cơ chế đáng tin; không retry mọi exception.
- Bắt được exception khi **COMMIT**, không chỉ khi JDBC statement lỗi.
- Áp dụng max attempts, overall deadline, bounded backoff + jitter và handling interrupt/cancellation.
- Không phát email/HTTP/messaging trực tiếp trong đoạn có thể retry; cân nhắc outbox.
- Có request id/idempotency key để xử lý client retry và “commit outcome unknown”.
- Test bằng PostgreSQL thật cho `40001`, dùng concurrency schedule/barrier; H2 synthetic test chỉ kiểm tra retry orchestration.
- Đo retry/abort rate và tác động lên pool/latency; đánh giá lại isolation hoặc dữ liệu nếu contention quá cao.

**Ghi nhớ:** `SERIALIZABLE` không hứa *mọi giao dịch đều commit*; nó hứa *các giao dịch đã commit không tạo lịch chạy thiếu tính tuần tự*. Khi DB trả serialization failure, **đóng transaction cũ, bắt đầu một transaction mới và chạy lại toàn bộ logic đọc–quyết định–ghi**; giới hạn số lần, tránh side effect kép và kiểm chứng trên DB thật.

## Tài liệu chính thức và tham khảo sâu

- [PostgreSQL — Serialization Failure Handling (SQLSTATE 40001, retry toàn bộ transaction)](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [PostgreSQL — Transaction Isolation (Serializable Snapshot Isolation)](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — SQLSTATE Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [Spring Framework 6.2 — Declarative Transaction Management, `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Programmatic Transaction Management, `TransactionTemplate`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — JDBC Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring DAO — `CannotSerializeTransactionException` (deprecated)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/CannotSerializeTransactionException.html)