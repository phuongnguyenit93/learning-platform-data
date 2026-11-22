# ACID: Tính nguyên tử, nhất quán, cô lập và bền vững của giao dịch

## 1. Giao dịch giải quyết vấn đề gì?

**Transaction (giao dịch)** là một đơn vị công việc gồm một hoặc nhiều thao tác trên dữ liệu được xử lý như một chỉnh thể. Với chuyển 200 đơn vị tiền từ tài khoản A sang B, nghiệp vụ phải đồng thời trừ 200 ở A và cộng 200 ở B. Nếu chỉ trừ được A mà không cộng được B, dữ liệu bị sai.

Một transaction thường kết thúc bằng một trong hai quyết định:

- **COMMIT**: chấp nhận toàn bộ thay đổi của transaction.
- **ROLLBACK**: hủy các thay đổi chưa commit của transaction đó theo khả năng bảo đảm của hệ quản trị cơ sở dữ liệu (DBMS).

**ACID** là bốn thuộc tính cần hiểu khi thiết kế và kiểm chứng giao dịch cơ sở dữ liệu:

| Thuộc tính | Câu hỏi nó trả lời | Ý nghĩa thực hành |
| --- | --- | --- |
| **A — Atomicity (nguyên tử)** | Nếu một bước thất bại thì sao? | Các thay đổi trong cùng transaction được commit cùng nhau hoặc rollback cùng nhau. |
| **C — Consistency (nhất quán)** | Dữ liệu sau giao dịch có hợp lệ không? | Giao dịch đúng phải chuyển cơ sở dữ liệu từ một trạng thái thỏa các bất biến/ràng buộc sang trạng thái cũng thỏa chúng. |
| **I — Isolation (cô lập)** | Các giao dịch chạy đồng thời nhìn thấy và ảnh hưởng nhau thế nào? | DBMS kiểm soát những tương tác đồng thời theo mức cô lập đã chọn; mức thấp có thể cho phép một số hiện tượng bất thường. |
| **D — Durability (bền vững)** | Đã báo commit rồi mà máy chủ gặp sự cố thì sao? | Khi commit thành công, dữ liệu được DBMS bảo tồn qua các sự cố thuộc phạm vi bảo đảm của cơ chế lưu trữ. |

ACID nói về ranh giới transaction trên **những tài nguyên thực sự tham gia transaction**. Gắn `@Transactional` cho một phương thức Java không tự biến HTTP call, email, Kafka message, bộ nhớ ứng dụng và nhiều cơ sở dữ liệu độc lập thành một giao dịch nguyên tử.

## 2. Atomicity — hoặc tất cả, hoặc không bước nào

Giả sử có bảng và dữ liệu khởi đầu trên PostgreSQL:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (1, 1000), (2, 500);
```

Chuyển 200 từ tài khoản 1 sang 2 trong **một transaction**:

```sql
BEGIN;

UPDATE accounts SET balance = balance - 200 WHERE id = 1;
UPDATE accounts SET balance = balance + 200 WHERE id = 2;

COMMIT;
```

Sau `COMMIT`, số dư lần lượt là 800 và 700; tổng vẫn là 1.500. Nếu gặp lỗi trước khi commit và transaction bị rollback, cả hai số dư trở về 1.000 và 500. Ví dụ minh họa rollback chủ động:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 200 WHERE id = 1;
-- Giả sử bước ghi có không thể hoàn tất.
ROLLBACK;
SELECT id, balance FROM accounts ORDER BY id;
```

Kết quả mong đợi trên dữ liệu khởi đầu:

```text
 id | balance
----+---------
  1 |    1000
  2 |     500
```

**Điểm dễ nhầm:** atomicity không phải “mọi câu SQL trong transaction luôn thành công”. Nó là khả năng không để lộ một **kết quả commit một phần** khi toàn transaction thất bại. Một số DBMS có cơ chế xử lý lỗi statement/savepoint khác nhau; cần hiểu trạng thái transaction thực tế sau lỗi và luôn kết thúc đúng bằng `COMMIT` hoặc `ROLLBACK`.

Không mở transaction, mỗi lệnh SQL có thể được auto-commit riêng. Khi đó bước trừ tiền thành công rồi bước cộng tiền thất bại sẽ tạo ra một trạng thái đã lưu nhưng sai nghiệp vụ. Một lời gọi phương thức Java cũng không phải ranh giới nguyên tử nếu các câu SQL sử dụng những kết nối/transaction khác nhau.

## 3. Consistency — bảo toàn các bất biến nghiệp vụ

**Invariant (bất biến)** là điều kiện phải đúng ở những trạng thái dữ liệu được chấp nhận. Ví dụ:

- `accounts.id` không trùng: `PRIMARY KEY`.
- `balance >= 0`: ràng buộc `CHECK`.
- Mọi lệnh chuyển tiền phải có tài khoản nguồn, tài khoản đích và số tiền dương.
- Với chuyển tiền nội bộ không thu phí, tổng tiền trước và sau phải bằng nhau.

Cơ sở dữ liệu có thể cưỡng chế trực tiếp nhiều quy tắc bằng `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, `CHECK`. Các quy tắc liên quan nhiều hàng, nhiều bảng hoặc trạng thái nghiệp vụ có thể đòi hỏi cập nhật có điều kiện, khóa, mức cô lập phù hợp và logic ứng dụng.

Ví dụ chỉ kiểm tra trong Java rồi cập nhật vô điều kiện là chưa đủ:

```java
// Phản ví dụ: hai request có thể cùng đọc số dư 100 và đều cho rằng
// có thể rút 80. Đọc rồi ghi không được đồng bộ có thể gây sai lệch.
long balance = loadBalance(accountId);
if (balance >= amount) {
    saveBalance(accountId, balance - amount);
}
```

Một giải pháp ở tầng SQL cho thao tác trừ tiền đơn lẻ là cập nhật có điều kiện **ngay trong câu UPDATE**:

```sql
UPDATE accounts
SET balance = balance - 80
WHERE id = 1 AND balance >= 80;
```

Ứng dụng phải kiểm tra số hàng được cập nhật: `1` nghĩa là trừ thành công; `0` nghĩa là không tìm thấy tài khoản hoặc không đủ tiền. Với phép chuyển khoản, đặt thao tác trừ và cộng vào cùng transaction.

**Consistency không đồng nghĩa “mọi business rule đều do ACID tự kiểm tra”.** Cơ sở dữ liệu biết các constraint được định nghĩa và cơ chế cô lập của nó; nhà phát triển phải mô hình hóa, kiểm tra và bảo vệ những invariant còn lại. “Consistency” trong ACID cũng không phải khái niệm “mọi replica đọc được giá trị mới ngay” của hệ thống phân tán.

## 4. Isolation — giao dịch đồng thời và những sai lệch có thể gặp

Hai transaction cùng truy cập một tập dữ liệu. Nếu không có cơ chế cô lập phù hợp, kết quả có thể phụ thuộc vào thời điểm chúng đọc/ghi. Mức cô lập **SERIALIZABLE** nhắm đến hiệu ứng tương đương một thứ tự thực thi tuần tự đối với các transaction đã commit, dù DBMS có thể thực thi chúng đồng thời. Các mức thấp hơn đánh đổi một phần bảo đảm để giảm tranh chấp hoặc tăng thông lượng.

### 4.1. Bốn hiện tượng cần nhận diện

**Dirty read (đọc dữ liệu chưa commit):** T1 cập nhật số dư 100 → 20 nhưng chưa commit; T2 đọc được 20; sau đó T1 rollback. T2 đã dựa vào một giá trị không bao giờ trở thành kết quả commit.

**Non-repeatable read (đọc lặp ra giá trị khác):** T1 đọc số dư 100; T2 cập nhật thành 120 và commit; T1 đọc lại cùng hàng trong cùng transaction và thấy 120. T1 không có một góc nhìn ổn định cho phép đọc lặp.

**Phantom read (hàng “bóng ma”):** T1 chạy `SELECT COUNT(*) FROM orders WHERE status = 'PENDING'` và được 5; T2 chèn một hàng thỏa điều kiện rồi commit; T1 chạy lại truy vấn và được 6. Tập hàng khớp điều kiện thay đổi.

**Lost update (mất cập nhật):** T1 và T2 đều đọc giá trị 100. T1 tính +10, T2 tính +20 rồi cùng ghi giá trị đã tính sẵn. Nếu không có bảo vệ phù hợp, kết quả cuối có thể là 110 hoặc 120 thay vì 130. Các DBMS, cú pháp cập nhật và mức cô lập có cách ngăn/điều khiển hiện tượng này khác nhau.

Còn có **write skew**: hai transaction đọc cùng một điều kiện tổng thể, sau đó cập nhật **hai hàng khác nhau** khiến invariant liên hàng bị vi phạm dù từng hàng không bị ghi đè. Chẳng hạn yêu cầu “luôn có ít nhất một bác sĩ trực”: hai bác sĩ đồng thời thấy người kia đang trực rồi mỗi người tự rút ca. Snapshot isolation/`REPEATABLE READ` ở một số DBMS vẫn có thể cho phép tình huống này.

### 4.2. Các mức cô lập và điều kiện thực tế

| Mức cô lập SQL | Dirty read | Non-repeatable read | Phantom read | Lưu ý |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Chuẩn SQL có thể cho phép | Có thể | Có thể | PostgreSQL xử lý như `READ COMMITTED`; không suy ra hành vi đồng nhất giữa DBMS. |
| `READ COMMITTED` | Ngăn | Có thể | Có thể | Mỗi statement có thể thấy snapshot đã commit khác nhau. |
| `REPEATABLE READ` | Ngăn | Ngăn | Phụ thuộc DBMS/cơ chế triển khai | PostgreSQL còn ngăn phantom trong mức này, nhưng vẫn có thể gặp serialization anomaly. |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn | Các transaction commit phải tương thích với một lịch tuần tự; hệ quản trị có thể từ chối transaction để giữ tính đúng đắn. |

Bảng là khái quát theo chuẩn SQL và lưu ý cụ thể của PostgreSQL, **không phải bảng cam kết cho mọi database engine**. MySQL InnoDB, PostgreSQL, SQL Server và Oracle khác nhau về locking, MVCC, phantom, snapshot, deadlock và cách triển khai từng mức.

Ví dụ quan sát trên hai kết nối PostgreSQL riêng biệt:

```sql
-- Session T1:
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT balance FROM accounts WHERE id = 1;  -- 1000

-- Session T2, trong khi T1 còn mở:
BEGIN;
UPDATE accounts SET balance = 900 WHERE id = 1;
COMMIT;

-- Quay lại Session T1:
SELECT balance FROM accounts WHERE id = 1;  -- 900
COMMIT;
```

Nếu T1 dùng `REPEATABLE READ` thay `READ COMMITTED`, lần đọc thứ hai trong T1 vẫn có thể thấy 1.000 theo snapshot của chính T1, với giả định T1 không tự sửa hàng ấy. Câu lệnh `UPDATE` ở trên là ví dụ độc lập về quan sát độ cô lập, không phải nghiệp vụ chuyển tiền.

### 4.3. Cách chọn công cụ bảo vệ dữ liệu

- **Constraint và cập nhật có điều kiện:** chặn trạng thái sai và tránh lỗ hổng kiểm tra rồi cập nhật, nhất là kiểm tra số dư.
- **Cập nhật trực tiếp trên DB:** `SET balance = balance + ?` thường an toàn hơn việc đọc giá trị về ứng dụng, cộng số rồi ghi đè; vẫn phải xét invariant và transaction bao quanh.
- **Khóa bi quan:** `SELECT ... FOR UPDATE` trên DBMS hỗ trợ khi cần khóa những bản ghi liên quan; giữ thứ tự khóa nhất quán để giảm deadlock.
- **Khóa lạc quan:** cột `version` và lệnh `UPDATE ... WHERE id = ? AND version = ?`; số hàng cập nhật bằng 0 báo xung đột, cần quyết định retry hay trả lỗi.
- **`SERIALIZABLE` khi logic phụ thuộc điều kiện liên hàng:** chấp nhận chi phí phối hợp và xử lý `serialization_failure` bằng retry **toàn bộ transaction**, không chỉ statement lỗi.

Đừng mặc định mức cô lập càng cao luôn càng tốt: cần kiểm chứng đồng thời tính đúng đắn, độ trễ, deadlock, khả năng retry và throughput.

## 5. Durability — dữ liệu sau commit phải tồn tại bền vững

Khi DBMS xác nhận `COMMIT` thành công, thay đổi đã qua cơ chế ghi bền vững của DBMS. Nhiều hệ thống dùng **write-ahead log (WAL)**: ghi thông tin phục hồi trước hoặc cùng lúc với việc xác nhận commit theo chính sách đồng bộ tương ứng; sau khi tiến trình bị dừng, DB có thể phục hồi trạng thái đã commit.

Phân biệt các mốc:

1. Lệnh `UPDATE` trả về thành công: **chưa có nghĩa** toàn transaction đã commit.
2. Ứng dụng gọi `COMMIT`: yêu cầu được gửi tới DBMS, có thể chưa nhận kết quả.
3. DBMS xác nhận commit: thay đổi được bảo đảm theo cấu hình durability/storage của DBMS.
4. Dịch vụ trả HTTP `200`: một sự kiện khác, có thể thất bại ngay cả khi DB đã commit.

Durability **không phải lời hứa dữ liệu tồn tại trước mọi loại thảm họa**. Thiết bị lưu trữ hỏng, cấu hình tắt đồng bộ, hạ tầng replica bất đồng bộ, mất cả vùng hoặc thao tác quản trị nhầm vẫn cần backup, restore, replication và chính sách phục hồi riêng.

Nếu kết nối mất đúng lúc commit, ứng dụng có thể **không biết commit đã xảy ra hay chưa**. Tự động gửi lại nghiệp vụ chuyển tiền một cách mù quáng có thể thực hiện chuyển tiền hai lần. Cần **idempotency key** có unique constraint và tra cứu trạng thái yêu cầu trước khi retry; `@Transactional` không tự đảm bảo “exactly once” giữa client và server.

## 6. ACID kết hợp trong một quy trình chuyển tiền

Với A=1.000, B=500 và yêu cầu chuyển 200:

1. Bắt đầu transaction T.
2. Kiểm tra số tiền dương, nguồn khác đích, điều kiện tài khoản.
3. Trừ 200 ở A chỉ khi A đủ số dư; kiểm tra đúng một hàng được cập nhật.
4. Cộng 200 cho B; kiểm tra đúng một hàng được cập nhật.
5. Nếu có lỗi ở bước 3 hoặc 4, rollback T; nếu mọi bước hợp lệ, commit T.
6. Sau commit, trạng thái được lưu bền vững; những transaction khác nhìn thấy thay đổi theo isolation của chính chúng.

Vai trò từng chữ: **A** giữ hai thay đổi đi cùng nhau; **C** yêu cầu số dư không âm, tài khoản hợp lệ và không tự tạo/mất tiền; **I** xử lý các chuyển khoản diễn ra đồng thời; **D** bảo tồn kết quả commit.

Một transaction chỉ bảo vệ được những thao tác thật sự thuộc nó. Nếu sau khi trừ tiền ở DB, ứng dụng gọi API ngân hàng ngoài hoặc gửi email, rollback DB **không thu hồi** yêu cầu HTTP/email đã được bên ngoài chấp nhận. Nghiệp vụ liên hệ thống cần thiết kế bổ sung như transactional outbox, idempotency, saga/compensation hoặc transaction phân tán khi hạ tầng thực sự hỗ trợ.

## 7. ACID trong Spring Framework: `@Transactional` kiểm soát điều gì?

Trong Spring transaction management thông dụng, lời gọi vào bean qua **Spring AOP proxy** được một transaction interceptor chặn. Interceptor phối hợp `PlatformTransactionManager` để tạo hoặc tham gia transaction, thực thi nghiệp vụ và commit/rollback tùy trạng thái, ngoại lệ và cấu hình. Đối với JDBC, các thao tác phải sử dụng connection gắn với transaction; với JPA, transaction manager phối hợp `EntityManager` và cơ sở dữ liệu.

```text
Caller -> Spring proxy -> TransactionInterceptor
                         -> PlatformTransactionManager
                         -> DataSource/JPA transaction
                         -> Service method -> SQL statements
                         -> commit hoặc rollback
                         -> Caller
```

Ví dụ dưới đây dùng **Java 17+, Spring Boot với JDBC (`JdbcTemplate`) và PostgreSQL**. Đây là đoạn lớp service đặt trong ứng dụng đã cấu hình `DataSource`, driver PostgreSQL và transaction manager; nó **không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`**.

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void transfer(long sourceId, long destinationId, long amount) {
        if (amount <= 0 || sourceId == destinationId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Missing source or insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, destinationId
        );
        if (credited != 1) {
            throw new IllegalStateException("Missing destination");
        }
    }
}
```

**Đọc đoạn code đúng cách:**

- `@Transactional` được áp dụng khi một đối tượng khác gọi **public method qua Spring proxy** và có transaction manager phù hợp. Mặc định `Propagation.REQUIRED`: tham gia transaction đang có hoặc bắt đầu mới nếu chưa có.
- `JdbcTemplate` sử dụng connection tham gia transaction do Spring quản lý. Trừ và cộng tiền cùng tham gia **một transaction vật lý** trong cấu hình JDBC chuẩn.
- `UPDATE ... WHERE balance >= ?` đặt điều kiện đủ tiền vào thao tác ghi để tránh khoảng trống giữa kiểm tra và cập nhật. Phải kiểm tra giá trị `debited`/`credited` (số hàng được cập nhật).
- Nếu tài khoản đích không tồn tại, `IllegalStateException` thoát khỏi phương thức: Spring rollback cả thao tác trừ đã thực hiện. Nếu cả hai lệnh thành công, Spring yêu cầu commit khi phương thức kết thúc.
- `Isolation.READ_COMMITTED` là cấu hình cho transaction **mới**; khi `REQUIRED` tham gia transaction có sẵn, đừng giả định annotation bên trong sẽ nâng mức cô lập của transaction đã mở. Mức hỗ trợ và hành vi cụ thể do transaction manager/DBMS quyết định.
- `CHECK (balance >= 0)`, khóa chính và tính nguyên tử của DB là lớp bảo vệ bổ sung. Trong ứng dụng thực tế còn phải xử lý overflow, đơn vị tiền/currency, idempotency, phân quyền, deadlock và việc nhiều giao dịch chuyển tiền theo hai chiều có thể khóa chéo nhau.

Nếu gọi `transferService.transfer(1, 2, 200)` qua bean Spring và dữ liệu ban đầu như mục 2, sau commit có A=800 và B=700. Nếu gọi `transferService.transfer(1, 999, 200)`, tài khoản 999 không tồn tại, ngoại lệ làm rollback, kết quả là A=1.000 và B=500. Các kết quả này giả định mỗi phép thử dùng lại trạng thái dữ liệu khởi đầu và không có transaction đồng thời.

### 7.1. Quy tắc rollback và những cái bẫy thường gặp

Mặc định thông dụng của Spring `@Transactional`:

| Tình huống | Kết quả mặc định |
| --- | --- |
| Phương thức trả về bình thường | Transaction được commit, trừ khi đã bị đánh dấu rollback-only hoặc commit gặp lỗi. |
| `RuntimeException` hoặc `Error` thoát khỏi phương thức | Spring đánh dấu/tiến hành rollback. |
| Checked exception (ví dụ `IOException`) thoát khỏi phương thức | Mặc định không buộc rollback, trừ khi có rollback rule/cấu hình mặc định khác. |
| Bắt exception rồi nuốt bên trong phương thức | Interceptor thấy phương thức trả về bình thường; transaction **có thể commit**. |
| Gọi phương thức annotated từ `this.method()` trong cùng bean ở proxy mode | Lời gọi nội bộ bỏ qua proxy, nên annotation trên phương thức được gọi không tự tạo transaction mới. |

Ví dụ khi checked exception cũng phải rollback:

```java
@Transactional(rollbackFor = Exception.class)
public void importAndValidate() throws Exception {
    // Thao tác với các tài nguyên tham gia cùng transaction.
    // Ném checked Exception khi nghiệp vụ cần hủy transaction.
}
```

`rollbackFor = Exception.class` là lựa chọn cho quy tắc cụ thể, không nên sao chép máy móc; điều kiện nào được rollback/commit phải phản ánh nghiệp vụ. Spring Framework các phiên bản mới cũng có cơ chế cấu hình **default rollback cho mọi exception**; kiểm tra phiên bản và cấu hình dự án trước khi suy luận từ hành vi mặc định. Nếu buộc phải bắt ngoại lệ trong transaction, thường nên ném lại ngoại lệ phù hợp hoặc chủ động đánh dấu rollback-only, thay vì log rồi tiếp tục như đã thành công.

### 7.2. Propagation có thể thay đổi ranh giới atomicity

- **`REQUIRED` (mặc định):** cùng transaction vật lý với caller nếu đã có; ngoại lệ ở đoạn bên trong có thể đánh dấu rollback-only khiến caller nhận `UnexpectedRollbackException` khi cố commit.
- **`REQUIRES_NEW`:** tạm treo transaction bên ngoài, bắt đầu transaction vật lý độc lập; bên trong có thể commit dù bên ngoài rollback. Hữu ích cho một số nghiệp vụ độc lập nhưng **không bảo đảm atomicity chung**; có thể cần thêm connection, gây cạn connection pool nếu dùng dày đặc.
- **`NESTED`:** thường ánh xạ vào JDBC savepoint khi transaction manager và driver hỗ trợ; rollback một phần về savepoint không giống transaction hoàn toàn độc lập. Không mặc định coi là dùng được trên mọi JPA/DBMS.

Chỉ định propagation cho một mục tiêu rõ ràng. Chẳng hạn ghi audit bằng `REQUIRES_NEW` có thể giữ lại log ngay cả khi chuyển tiền rollback, nhưng dữ liệu audit và dữ liệu chuyển tiền **không còn cùng quyết định commit**; phải chấp nhận và mô tả hệ quả này.

### 7.3. Ranh giới proxy, luồng và tài nguyên

- Đặt transaction ở service layer bao trùm **toàn bộ đơn vị nghiệp vụ**; gọi từ bean khác qua proxy. `private method`, self-invocation và việc tự tạo đối tượng bằng `new` thường khiến annotation không được áp dụng như kỳ vọng trong proxy mode.
- Transaction JDBC kiểu imperative thường gắn với context của luồng đang chạy. Không mặc nhiên truyền transaction sang `new Thread`, `@Async` hoặc tác vụ background. Transaction reactive sử dụng cơ chế context khác, phải theo ReactiveTransactionManager.
- `readOnly = true` thường là **hint/optimization**, không phải bảo đảm mọi câu ghi sẽ bị cấm. Nó cũng không tự chọn mức cô lập an toàn.
- Một phương thức `@Transactional` rất dài, chờ mạng hoặc chờ người dùng sẽ giữ transaction/connection/lock quá lâu. Đưa HTTP call bên ngoài ra khỏi phần giữ khóa khi thiết kế cho phép.
- Với nhiều `DataSource`/transaction manager, xác định rõ manager nào điều phối thao tác nào. Một local transaction manager không tự cung cấp atomicity xuyên nhiều DB.

## 8. Kiểm chứng ACID bằng tình huống cụ thể

| Phép thử | Điều cần quan sát | Thuộc tính liên quan |
| --- | --- | --- |
| Chuyển 200 từ A=1.000 sang B=500 thành công | A=800, B=700, tổng=1.500 | A, C, D |
| Tài khoản đích không tồn tại sau khi đã trừ nguồn | Ném exception; A vẫn 1.000, B vẫn 500 sau rollback | A, C |
| Rút lớn hơn số dư | `UPDATE` nguồn trả 0; không tài khoản nào thay đổi | C, A |
| Hai request đồng thời rút tiền từ một tài khoản | Không được để số dư âm; kết quả số hàng cập nhật/constraint đúng | I, C |
| Hai transaction đọc cùng hàng trước/sau một commit | Kết quả phù hợp với isolation thực tế | I |
| Dừng tiến trình DB sau khi commit được xác nhận rồi phục hồi | Thay đổi commit còn tồn tại theo bảo đảm/cấu hình DB | D |
| Client mất kết nối ngay lúc server commit | Không tự kết luận commit chưa xảy ra; dùng request-id để đối soát | D và idempotency ở tầng ứng dụng |

Trong kiểm thử tích hợp Spring, có thể gọi service qua bean và quan sát lại dữ liệu sau ngoại lệ. Đoạn JUnit sau minh họa ý tưởng (đặt trong `@SpringBootTest` có schema/fixture như mục 2, inject `TransferService` và `JdbcTemplate`; đây là **trích đoạn test**, không phải lớp Java độc lập):

```java
@Test
void missingDestinationRollsBackDebit() {
    assertThrows(IllegalStateException.class,
        () -> transferService.transfer(1L, 999L, 200L));

    Long after = jdbc.queryForObject(
        "SELECT balance FROM accounts WHERE id = ?",
        Long.class, 1L
    );
    assertEquals(1000L, after);
}
```

**Lưu ý test:** test method có `@Transactional` trong Spring Test thường tự rollback khi kết thúc. Để chứng minh hành vi commit/rollback thật của service, thiết kế setup/teardown và ranh giới transaction test cho rõ ràng; nếu cần, quan sát bằng kết nối/transaction độc lập và dùng kiểm thử đồng thời thật cho các race condition. Test tuần tự không thể chứng minh không có lost update hay write skew.

## 9. Giải đáp các nhầm lẫn

**“Có `@Transactional` là đã có đủ ACID?”** Không. Annotation điều phối transaction mà transaction manager hỗ trợ. Atomicity/durability chính do DBMS, persistence configuration và phạm vi tài nguyên bảo đảm; consistency cần đúng constraint/logic; isolation còn tùy mức được cấu hình.

**“Nếu method báo thành công thì toàn bộ thay đổi đã commit?”** Nếu phương thức được gọi qua proxy và bắt đầu transaction tại đây, commit thường xảy ra khi interceptor hoàn tất lời gọi. Nếu phương thức chỉ **tham gia transaction bên ngoài**, commit cuối cùng do transaction bên ngoài quyết định. `flush()` của JPA đồng bộ thay đổi xuống DB nhưng không đồng nghĩa commit.

**“`READ COMMITTED` có đủ chống mọi race?”** Không. Nó ngăn dirty read, nhưng các lần đọc có thể thấy snapshot khác, và những quy tắc đọc-kiểm tra-ghi vẫn có thể bị cạnh tranh. Dùng atomic SQL, constraint, lock, version hoặc mức cô lập cao hơn tùy invariant.

**“Serializable có nghĩa DB chạy từng transaction một?”** Không. DB có thể chạy đồng thời và hủy một transaction xung đột để kết quả các transaction đã commit tương đương thực thi tuần tự. Ứng dụng phải có chiến lược retry transaction khi gặp lỗi serialization/deadlock phù hợp.

**“Đã commit thì không cần backup?”** Không. Durability và backup/khôi phục thảm họa là hai lớp bảo đảm khác nhau. Cần chính sách phục hồi và kiểm thử khôi phục thực tế.

**“Rollback DB có hủy được event đã publish/email đã gửi?”** Không, trừ khi tài nguyên đó thật sự tham gia cùng giao thức transaction phù hợp. Để đồng bộ DB với messaging, cân nhắc transactional outbox: ghi bản ghi outbox cùng transaction DB, sau đó bộ phát sự kiện gửi đi và consumer xử lý idempotent.

## 10. Checklist thiết kế transaction trong Spring

1. Xác định **đơn vị nghiệp vụ** nào cần commit/rollback cùng nhau và tài nguyên thực sự tham gia transaction.
2. Mô tả bất biến nghiệp vụ; đặt constraint DB tối đa có thể, bổ sung atomic SQL/locking/version cho phần còn lại.
3. Đặt `@Transactional` ở public service method được gọi qua Spring proxy; xác nhận transaction manager và DataSource/JPA configuration.
4. Chọn isolation dựa trên những anomaly không được phép; quan sát engine cụ thể thay vì chỉ đọc bảng mức cô lập chung.
5. Quyết định rollback rule cho checked/unchecked exceptions; không nuốt lỗi khiến transaction commit nhầm.
6. Kiểm tra propagation, lời gọi nội bộ, `@Async` và thao tác với dịch vụ bên ngoài trước khi tin rằng mọi việc đều trong một transaction.
7. Giữ transaction ngắn, xử lý retry cho lỗi transient trên **toàn transaction** khi thích hợp, bảo đảm request idempotent.
8. Kiểm thử đường thành công, lỗi giữa chừng, cạnh tranh đồng thời và phục hồi sau commit; quan sát transaction/SQL log cùng trạng thái dữ liệu thật.

## Tài liệu tham khảo

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- PostgreSQL — Transaction Isolation: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — SET TRANSACTION: https://www.postgresql.org/docs/current/sql-set-transaction.html