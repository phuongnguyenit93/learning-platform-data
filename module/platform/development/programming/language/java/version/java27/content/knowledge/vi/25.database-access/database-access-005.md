# Isolation, khóa dữ liệu và xử lý xung đột cập nhật trong Java 27

Trong ứng dụng nhiều người dùng, hai request có thể cùng đọc và cập nhật một bản ghi gần như đồng thời. Nếu mỗi request tự tính giá trị mới dựa trên dữ liệu đã đọc, kết quả cuối cùng có thể **mất cập nhật**, vi phạm số dư tối thiểu, ghi nhận hai lượt đặt hàng cho một chỗ trống hoặc trả về trạng thái không nhất quán. Không có một câu lệnh `UPDATE` riêng lẻ nào tự giải quyết được **mọi** bài toán giao dịch, nhưng cơ sở dữ liệu quan hệ và JDBC cung cấp những công cụ rõ ràng để xử lý.

Ba nhóm công cụ quan trọng:

- **Transaction isolation**: quy định giao dịch được phép quan sát ảnh hưởng của các giao dịch đồng thời như thế nào.
- **Khóa dữ liệu (pessimistic locking)**: bảo vệ một tài nguyên trước hoặc trong khi quyết định cập nhật, chẳng hạn dùng `SELECT ... FOR UPDATE` ở hệ quản trị có hỗ trợ.
- **Kiểm tra xung đột lạc quan (optimistic concurrency control)**: cho phép đọc rồi xử lý mà không giữ khóa dài, nhưng chỉ chấp nhận cập nhật nếu phiên bản/snapshot vẫn phù hợp, thường dùng `UPDATE ... WHERE version = ?`.

Bài thuộc chương **Truy cập cơ sở dữ liệu** trong module **Java 27 và các kiến thức liên quan**. Ví dụ sử dụng **JDBC chuẩn**, `java.sql.Connection`, `PreparedStatement`, `ResultSet` và các cơ chế giao dịch đang được hỗ trợ. Những câu SQL đặc thù như `FOR UPDATE` được ghi rõ khi minh họa **PostgreSQL**; không giả định mọi hệ quản trị có cú pháp và mức cô lập giống nhau. Nội dung không sử dụng API Java legacy hoặc tính năng preview.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Hiểu ACID, transaction boundary và mức isolation trong JDBC.
2. Phân biệt dirty read, non-repeatable read, phantom read, lost update và write skew.
3. Hiểu tại sao cùng một tên isolation level có thể có chi tiết thực thi khác nhau theo DBMS.
4. Dùng `setAutoCommit(false)`, `commit()`, `rollback()`, `setTransactionIsolation(...)` đúng thời điểm.
5. Dùng khóa hàng `SELECT ... FOR UPDATE` cho nghiệp vụ cần đọc rồi ra quyết định cập nhật.
6. Dùng một lệnh SQL `UPDATE` có điều kiện để tránh nhiều trường hợp lost update.
7. Thiết kế optimistic locking bằng cột `version` và kiểm tra `executeUpdate()`.
8. Nhận diện serialization failure, deadlock, timeout và xây cơ chế retry **toàn transaction** có giới hạn.
9. Phân biệt retry database transaction với retry tác động ngoài như gửi email hoặc thu tiền.
10. Chọn chiến lược dựa trên invariant, mức tranh chấp và khả năng vận hành.

## 2. Giao dịch là gì, và vì sao một request có thể cần nhiều câu SQL?

Một **transaction** là đơn vị công việc được commit hoặc rollback theo quy tắc của hệ quản trị cơ sở dữ liệu. Trong nhiều hệ quản trị quan hệ, transaction đảm nhận bốn nhóm thuộc tính **ACID**:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| Atomicity | Các thay đổi của một transaction commit cùng nhau hoặc rollback khi cần | Chuyển tiền không được chỉ trừ mà không cộng |
| Consistency | Transaction phải tôn trọng constraint và các invariant nghiệp vụ được thực thi đúng | `balance >= 0`, khóa duy nhất |
| Isolation | Hạn chế cách các transaction đồng thời quan sát/ảnh hưởng nhau | Hai request cùng đặt vé |
| Durability | Dữ liệu đã commit được bảo toàn theo hợp đồng durability của DBMS | Bản ghi không biến mất sau restart bình thường |

**ACID không có nghĩa database tự hiểu mọi luật nghiệp vụ.** Nếu không có constraint hoặc giao dịch/khóa phù hợp, nhiều transaction riêng lẻ đều có thể commit nhưng cùng nhau làm sai invariant của ứng dụng.

Ví dụ chuyển 100 đơn vị từ A sang B gồm ít nhất hai thay đổi:

```sql
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
```

Nếu hai câu này chạy dưới **hai transaction khác nhau**, việc câu thứ hai thất bại có thể khiến dữ liệu không còn đúng ý định. Cả hai cần nằm trong **một transaction** có kiểm tra tiền điều kiện và xử lý lỗi phù hợp.

## 3. Race condition tại cơ sở dữ liệu khác data race trong Java

Một `synchronized` trong JVM có thể ngăn hai thread của **cùng một process** đi vào critical section, nhưng không bảo vệ trước:

- Instance ứng dụng khác kết nối cùng database.
- Job nền hoặc tác vụ batch ở máy khác.
- Người dùng chạy SQL qua admin tool.
- Service khác cùng sửa các hàng dữ liệu.

Vì vậy, quy tắc dữ liệu chia sẻ giữa nhiều tiến trình nên được bảo vệ tại **database transaction, constraint hoặc cơ chế điều phối được thiết kế rõ**.

Ngược lại, chọn `SERIALIZABLE` trong database **không tự làm các object Java mutable trở nên thread-safe**. Đây là hai phạm vi đồng thời khác nhau.

## 4. Các hiện tượng bất thường (anomalies) cần nhận diện

### 4.1. Dirty read

Transaction T1 sửa giá trị nhưng chưa commit. T2 đọc giá trị đó; sau đó T1 rollback.

```text
T1: BEGIN -- UPDATE price=200 -------- ROLLBACK
T2:           SELECT price -> 200
```

T2 đã đọc dữ liệu chưa từng trở thành trạng thái commit. Đây là **dirty read**. Không phải mọi DBMS cho phép hiện tượng này, ngay cả khi yêu cầu level `READ_UNCOMMITTED`.

### 4.2. Non-repeatable read

T1 đọc một hàng hai lần; giữa hai lần, T2 cập nhật/commit nên T1 có thể thấy hai giá trị khác nhau.

```text
T1: BEGIN -- SELECT balance -> 100 ----- SELECT balance -> 80
T2:                UPDATE balance=80 -- COMMIT
```

Trường hợp này quan trọng khi nghiệp vụ giả định một lần đọc đầu transaction vẫn đúng cho một quyết định ở cuối transaction.

### 4.3. Phantom read

T1 chạy cùng một truy vấn theo điều kiện hai lần; T2 chèn/xóa/sửa hàng làm tập kết quả thay đổi.

```text
T1: SELECT COUNT(*) WHERE status='OPEN' -> 5
T2: INSERT INTO orders(status) VALUES ('OPEN'); COMMIT
T1: SELECT COUNT(*) WHERE status='OPEN' -> 6
```

Khác với non-repeatable read trên **cùng hàng**, phantom liên quan đến **tập hàng thỏa predicate**.

### 4.4. Lost update

Hai transaction cùng đọc số dư 100, mỗi transaction tính số dư mới bằng cách riêng rồi ghi đè kết quả.

```text
T1: READ 100 -------- UPDATE balance=110 -- COMMIT
T2:      READ 100 --------------- UPDATE balance=120 -- COMMIT
                                  Kết quả: 120 thay vì 130
```

Tùy DBMS/isolation, một transaction có thể bị chặn hoặc báo xung đột thay vì cả hai commit. Nhưng thuật toán **đọc–tính–ghi mà không bảo vệ xung đột** không nên được xem là an toàn chỉ vì ứng dụng thử nghiệm đôi khi chạy đúng.

### 4.5. Write skew

Hai transaction đọc cùng một điều kiện liên quan **nhiều hàng**, sau đó mỗi bên sửa **một hàng khác nhau**. Cả hai riêng lẻ dựa trên snapshot hợp lệ nhưng tổng trạng thái sau commit lại vi phạm invariant.

Ví dụ cần ít nhất một bác sĩ trực:

```text
Ban đầu: doctor A on_call=true, doctor B on_call=true

T1 đọc A+B: có 2 người trực, nên tắt A.
T2 đọc A+B: có 2 người trực, nên tắt B.

Nếu cả hai cập nhật hàng khác nhau và đều commit:
A=false, B=false -> không còn người trực.
```

Đây là minh họa quan trọng cho việc **snapshot isolation/REPEATABLE READ không phải lúc nào cũng tương đương SERIALIZABLE**. Chỉ khóa một hàng được sửa riêng lẻ có thể chưa bảo vệ invariant trên cả tập hàng.

### 4.6. Serialization anomaly

Kết quả của các transaction đồng thời không tương đương với bất kỳ thứ tự thực thi tuần tự hợp lệ nào, theo định nghĩa serializability. Write skew là một ví dụ nổi bật trong nhiều thiết kế.

**Không phải mọi anomaly đều được mô tả đủ bằng ba tên dirty/non-repeatable/phantom.** Khi chọn isolation phải kiểm tra cả lost update, write skew, predicate locking hoặc SSI theo hệ quản trị thực tế.

## 5. Bốn isolation level chuẩn trong JDBC

`java.sql.Connection` định nghĩa các hằng:

| Mức | Hằng JDBC | Mục tiêu tổng quát |
|---|---|---|
| Read uncommitted | `TRANSACTION_READ_UNCOMMITTED` | Cho phép mô hình cô lập yếu, có thể dirty read ở một số DBMS |
| Read committed | `TRANSACTION_READ_COMMITTED` | Không đọc dữ liệu chưa commit; mỗi statement có thể nhìn snapshot mới |
| Repeatable read | `TRANSACTION_REPEATABLE_READ` | Tăng ổn định khi đọc trong transaction; chi tiết tùy DBMS |
| Serializable | `TRANSACTION_SERIALIZABLE` | Hướng tới kết quả tương đương thực thi tuần tự |

Bảng hiện tượng SQL thường được dùng để giới thiệu các mức:

| Level khái niệm | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| READ UNCOMMITTED | Có thể | Có thể | Có thể |
| READ COMMITTED | Ngăn | Có thể | Có thể |
| REPEATABLE READ | Ngăn | Ngăn theo định nghĩa truyền thống | Có thể theo mô hình chuẩn thông dụng |
| SERIALIZABLE | Ngăn | Ngăn | Ngăn |

**Bảng là mô hình lý thuyết, không phải lời hứa chi tiết của mọi driver/DBMS.** Ví dụ PostgreSQL coi `READ UNCOMMITTED` tương đương hành vi `READ COMMITTED`; PostgreSQL `REPEATABLE READ` có semantics snapshot mạnh hơn bảng tối thiểu, nhưng vẫn có thể gặp write skew. Những hệ quản trị khác có lock-based hoặc MVCC implementation khác nhau.

### 5.1. Không được suy isolation chỉ từ tên

Cần kiểm tra đồng thời:

- Isolation level được cấu hình và **thực sự được DBMS chấp nhận**.
- Quy tắc snapshot/read tại từng level.
- Các dạng lock khi `SELECT`, `UPDATE` và index/range scan.
- Transaction có thể chờ hay bị abort khi đụng xung đột.
- Có cần retry sau serialization failure hay không.

### 5.2. JDBC không tự cung cấp isolation engine

JDBC là một **API điều khiển** connection/transaction. Việc phát hiện write skew, tạo row lock, dùng MVCC và phân loại deadlock thuộc về database engine/driver. Vì vậy một ví dụ Java có thể đúng cách dùng JDBC nhưng vẫn cần ghi rõ giả định DBMS để kết luận về mức cô lập.

## 6. Transaction boundary trong JDBC

Mặc định, kết nối JDBC thường bắt đầu ở chế độ **auto-commit**: mỗi statement độc lập được commit khi hoàn tất theo hợp đồng JDBC. Nếu nghiệp vụ cần nhiều câu SQL trong cùng transaction, phải tắt auto-commit trước khi thực hiện chúng.

Ví dụ tối giản:

```java
import java.sql.Connection;
import java.sql.SQLException;

static void performTransaction(Connection connection) throws SQLException {
    // Nên cấu hình isolation trước khi transaction bắt đầu.
    connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
    connection.setAutoCommit(false);

    try {
        // Thực hiện các PreparedStatement cùng connection.
        performStepOne(connection);
        performStepTwo(connection);

        connection.commit();
    } catch (SQLException | RuntimeException exception) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            exception.addSuppressed(rollbackFailure);
        }
        throw exception;
    }
}
```

`performStepOne` và `performStepTwo` là phương thức ứng dụng tự định nghĩa; đây là **khung minh họa**. Nếu connection đến từ pool, cần tuân thủ contract của pool về reset transaction state; không dùng cùng một `Connection` đồng thời cho nhiều giao dịch khác nhau.

### 6.1. Thứ tự cấu hình

Nên xác định `setTransactionIsolation(...)` **trước** khi transaction bắt đầu. Thay đổi isolation giữa transaction có thể có hành vi phụ thuộc implementation hoặc không được phép theo driver/DBMS.

### 6.2. Đừng quên commit/rollback

Nếu method trả về giữa chừng mà chưa rollback/commit, transaction có thể tiếp tục giữ lock hoặc snapshot. Với connection pool, đó là lỗi vận hành nghiêm trọng. Hãy đặt transaction boundary ở nơi có **một chủ sở hữu rõ ràng**, rollback mọi nhánh lỗi, và tránh giữ transaction mở khi chờ API bên ngoài.

### 6.3. SQL exception không phải lúc nào cũng tự rollback toàn bộ

Một statement có thể thất bại nhưng tình trạng transaction sau lỗi phụ thuộc DBMS và loại lỗi. Có hệ quản trị đánh dấu transaction là aborted và yêu cầu rollback; có hệ quản trị cho phép xử lý lỗi trong phạm vi thích hợp. **Khi không thể tiếp tục an toàn, rollback rõ ràng**, không dựa vào một lời gọi close tùy ý để thay thế logic lỗi.

## 7. Kiểm tra khả năng hỗ trợ mức isolation

JDBC cung cấp các API:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    boolean supported = meta.supportsTransactionIsolationLevel(
            Connection.TRANSACTION_SERIALIZABLE
    );

    System.out.println("Serializable supported: " + supported);
    System.out.println("Current isolation: " +
            connection.getTransactionIsolation());
}
```

`dataSource` minh họa một đối tượng `javax.sql.DataSource` do ứng dụng tạo/cấu hình.

Lưu ý: metadata có thể cho biết mức được hỗ trợ nhưng **không mô tả đầy đủ semantics thực tế** của từng engine. Một driver có thể chuyển một yêu cầu sang mức tương đương gần nhất theo chính sách của DBMS, hoặc từ chối. Hãy đọc tài liệu database và xác minh trạng thái connection sau khi cấu hình.

### 7.1. Read-only không có nghĩa là isolation mạnh

`connection.setReadOnly(true)` là **hint hoặc chế độ** dành cho kết nối theo driver/DBMS, không tự biến transaction thành snapshot nhất quán hay bảo đảm không có ghi. Nếu cần transaction read-only với semantics cụ thể, hãy dựa vào contract của engine và kiểm tra hành vi thực tế.

## 8. READ COMMITTED: lựa chọn phổ biến, nhưng cần bảo vệ read–modify–write

Trong PostgreSQL, `READ COMMITTED` là mức mặc định phổ biến: mỗi statement lấy snapshot phù hợp tại thời điểm bắt đầu statement. Một lần `SELECT` sau có thể nhìn commit mới từ transaction khác.

Ví dụ:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM accounts WHERE id = 1;
-- Transaction khác có thể COMMIT cập nhật id=1 ở giữa.

SELECT balance FROM accounts WHERE id = 1;
COMMIT;
```

Hai lần `SELECT` có thể trả số dư khác nhau. Nếu code đọc số dư, tự cộng một lượng rồi ghi bằng:

```sql
UPDATE accounts
SET balance = 150000
WHERE id = 1;
```

nó có thể ghi đè kết quả cập nhật của người khác vì statement cuối **không kiểm tra** giá trị cũ hay phiên bản.

Cách sửa không nhất thiết phải tăng isolation toàn hệ thống: với số đếm/số dư cộng dồn, một câu `UPDATE` biểu diễn phép biến đổi ngay trong database thường đơn giản hơn; với workflow cần đọc rồi quyết định nhiều bước, dùng pessimistic lock, optimistic version hoặc serializable transaction.

## 9. REPEATABLE READ, MVCC và snapshot isolation

**MVCC (Multi-Version Concurrency Control)** là kỹ thuật quản lý nhiều phiên bản dữ liệu để việc đọc/ghi có thể đồng thời mà không luôn chặn nhau như một mô hình khóa thô.

Ở một số hệ quản trị (ví dụ PostgreSQL), `REPEATABLE READ` sử dụng transaction-level snapshot: các lần đọc thông thường trong transaction nhìn một snapshot nhất quán hơn so với `READ COMMITTED`.

Điều đó **không đồng nghĩa mọi invariant đều an toàn**:

- Hai transaction có thể cùng nhìn điều kiện trên nhiều hàng.
- Mỗi transaction ghi một hàng khác nhau.
- Nếu không có xung đột trực tiếp bị engine phát hiện ở level đó, chúng có thể tạo **write skew**.

Tương tự, phiên bản mới được commit bởi transaction khác có thể **không hiển thị ngay** cho một transaction đang giữ snapshot cũ, dù nó đã chờ lâu.

### 9.1. MVCC không có nghĩa "không dùng lock"

Trong nhiều DBMS MVCC, `UPDATE`/`DELETE` vẫn có thể đụng row-level conflict, và `SELECT FOR UPDATE` vẫn có locking semantics. Việc dùng snapshot không tự loại bỏ deadlock hoặc yêu cầu retry.

### 9.2. Isolation mạnh có thể phát sinh lỗi cạnh tranh thay vì âm thầm commit

Ví dụ trong PostgreSQL, một transaction `REPEATABLE READ` cố cập nhật hàng đã được transaction đồng thời thay đổi có thể thất bại do concurrent update/serialization. Đây là **tín hiệu cần xử lý**, không phải lý do để bỏ qua exception rồi trả thành công.

## 10. SERIALIZABLE: điều kiện đúng và chi phí

`SERIALIZABLE` hướng đến hành vi **tương đương với một thứ tự thực thi tuần tự** của các transaction thành công. Nó hữu ích khi invariant phức tạp trải trên nhiều hàng và không dễ bảo vệ bằng một update có điều kiện hoặc một tập row lock cố định.

Trong PostgreSQL, serializable isolation dùng cơ chế theo dõi phụ thuộc và có thể **abort một transaction** khi phát hiện lịch thực thi không thể bảo đảm serializability. Tác vụ ứng dụng phải **retry transaction từ đầu** trong những lỗi được phân loại là retryable.

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Đọc các hàng để quyết định có đủ người trực.
-- Thực hiện các thay đổi hợp lệ theo snapshot.
-- COMMIT có thể thất bại với serialization failure.

COMMIT;
```

**Điểm quan trọng:**

- Serializable không có nghĩa tất cả giao dịch đều chạy lần lượt trên một global mutex.
- Serializable có thể tăng chi phí theo dõi phụ thuộc, tranh chấp và số lần retry.
- Không được thay cơ chế kiểm tra constraint/validation bằng giả định "đã serializable thì mọi dữ liệu đều hợp lệ".
- Khi transaction bị abort, **không retry riêng câu SQL cuối cùng**. Cần đọc lại dữ liệu và quyết định lại trong **transaction mới**.

## 11. Pessimistic locking: khóa trước khi cập nhật

**Khóa bi quan** giả định khả năng xung đột đủ đáng kể để cần đặt quyền truy cập phù hợp lên những hàng liên quan trước khi quyết định cập nhật.

Trong PostgreSQL, câu:

```sql
SELECT balance
FROM accounts
WHERE id = 1
FOR UPDATE;
```

được dùng **bên trong một transaction** để yêu cầu row-level lock phù hợp. Những transaction khác cần khóa ghi xung đột lên hàng đó có thể phải chờ đến khi transaction hiện tại commit/rollback.

### 11.1. Vì sao SELECT trước UPDATE thường chưa đủ?

Không khóa:

```text
T1: SELECT balance=100
T2: SELECT balance=100
T1: UPDATE balance=70   -- Trừ 30
T2: UPDATE balance=50   -- Trừ 50 từ ảnh chụp cũ
```

Nếu cả hai commit, tổng trừ có thể sai: hai phép trừ 30 và 50 đáng ra cho 20.

Có locking thích hợp:

```text
T1: BEGIN; SELECT ... FOR UPDATE;  -- giữ lock
T2: BEGIN; SELECT ... FOR UPDATE;  -- có thể phải chờ
T1: kiểm tra, UPDATE, COMMIT
T2: tiếp tục theo chính sách isolation/engine, đọc/xử lý tình trạng mới
```

Tùy mức isolation và DBMS, T2 có thể đọc phiên bản cập nhật hoặc gặp serialization/concurrency error cần retry. **Không đưa ra một kết luận phổ quát cho mọi isolation level chỉ từ cú pháp FOR UPDATE.**

### 11.2. Khi nào locking có ý nghĩa?

- Chuyển tiền giữa hai tài khoản.
- Đặt chỗ với lượng hàng còn lại và quy tắc giới hạn.
- Claim một công việc từ bảng queue (tùy mô hình và SQL dialect).
- Workflow cần đọc một hàng, kiểm tra ràng buộc, sau đó cập nhật trong cùng transaction.

### 11.3. Giới hạn của row lock

Khóa một hàng **không nhất thiết bảo vệ predicate trên toàn bộ tập hàng**, nhất là khi giao dịch có thể thêm các hàng mới thỏa điều kiện. Nếu invariant là "số bác sĩ trực phải ít nhất một người", cần xác định **tập dữ liệu phải phối hợp**; có thể khóa tất cả hàng liên quan, dùng constraint thích hợp, cấu trúc điều phối riêng hoặc SERIALIZABLE.

## 12. Ví dụ PostgreSQL: schema tài khoản và điều kiện cần bảo vệ

Để các ví dụ Java phía sau có đầu vào cụ thể, giả sử bạn có database PostgreSQL dùng schema:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);

INSERT INTO accounts (id, balance, version)
VALUES
    (1, 100000, 0),
    (2, 50000, 0);
```

**Đây là SQL chuẩn bị dữ liệu học tập**, chỉ chạy trên database thử nghiệm. Không chạy `CREATE TABLE`/`INSERT` trên database production đã có bảng hoặc dữ liệu thật.

### 12.1. Vì sao cần cả CHECK và application logic?

- `CHECK (balance >= 0)` là **hàng rào bảo vệ cuối cùng** ở database.
- Application cần kiểm tra số dư để tạo thông báo nghiệp vụ rõ ràng và tránh thử update chắc chắn không hợp lệ.
- `version` giúp phát hiện cập nhật dựa trên snapshot cũ.
- `PRIMARY KEY` bảo đảm ID là duy nhất.

Constraint không thay thế toàn bộ transaction isolation, nhưng giúp giữ invariant **ngay cả khi có code khác cập nhật database**.

### 12.2. JDBC driver không được cung cấp sẵn cho mọi DBMS

JDK có API `java.sql`, nhưng để kết nối PostgreSQL bạn cần **PostgreSQL JDBC driver** tương thích, cùng database chạy được và thông tin truy cập.

Ví dụ JDBC URL:

```text
jdbc:postgresql://localhost:5432/demo
```

Khi chạy bài học, cung cấp driver JAR từ dependency hợp lệ trên class path, hoặc dùng hệ thống build quản lý dependency. Không hardcode password vào source; ví dụ Java đọc `JDBC_URL`, `JDBC_USER` và `JDBC_PASSWORD` từ môi trường.

## 13. Ví dụ hoàn chỉnh: chuyển tiền bằng SELECT FOR UPDATE

Ví dụ sau dùng **PostgreSQL**. Nó khóa hai hàng tài khoản **theo thứ tự ID tăng dần** trước khi kiểm tra và cập nhật, giảm nguy cơ deadlock khi có nhiều lệnh chuyển tiền ngược chiều.

Lưu thành `JdbcPessimisticTransferDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcPessimisticTransferDemo {

    private static long lockAndReadBalance(
            Connection connection,
            long accountId
    ) throws SQLException {

        String sql = """
                SELECT balance
                FROM accounts
                WHERE id = ?
                FOR UPDATE
                """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {

            statement.setLong(1, accountId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                            "Account not found: " + accountId
                    );
                }
                return rs.getLong("balance");
            }
        }
    }

    private static void updateBalance(
            Connection connection,
            long accountId,
            long balance
    ) throws SQLException {

        String sql = """
                UPDATE accounts
                SET balance = ?,
                    version = version + 1
                WHERE id = ?
                """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {

            statement.setLong(1, balance);
            statement.setLong(2, accountId);

            if (statement.executeUpdate() != 1) {
                throw new SQLException(
                        "Account update did not affect one row"
                );
            }
        }
    }

    static void transfer(
            String url,
            String user,
            String password,
            long fromId,
            long toId,
            long amount
    ) throws SQLException {

        if (fromId == toId || amount <= 0) {
            throw new IllegalArgumentException(
                    "Distinct accounts and positive amount required"
            );
        }

        try (Connection connection =
                DriverManager.getConnection(url, user, password)) {

            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED
            );
            connection.setAutoCommit(false);

            try {
                long firstId = Math.min(fromId, toId);
                long secondId = Math.max(fromId, toId);

                long firstBalance =
                        lockAndReadBalance(connection, firstId);
                long secondBalance =
                        lockAndReadBalance(connection, secondId);

                long senderBalance = fromId == firstId
                        ? firstBalance
                        : secondBalance;

                long receiverBalance = toId == firstId
                        ? firstBalance
                        : secondBalance;

                if (senderBalance < amount) {
                    throw new IllegalArgumentException(
                            "Insufficient balance"
                    );
                }

                long newSender =
                        Math.subtractExact(senderBalance, amount);
                long newReceiver =
                        Math.addExact(receiverBalance, amount);

                updateBalance(connection, fromId, newSender);
                updateBalance(connection, toId, newReceiver);

                connection.commit();
            } catch (SQLException | RuntimeException exception) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    exception.addSuppressed(rollbackFailure);
                }
                throw exception;
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        if (args.length != 3) {
            System.err.println(
                    "Usage: java JdbcPessimisticTransferDemo "
                    + "<fromId> <toId> <amount>"
            );
            return;
        }

        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = requiredEnv("JDBC_PASSWORD");

        transfer(
                url,
                user,
                password,
                Long.parseLong(args[0]),
                Long.parseLong(args[1]),
                Long.parseLong(args[2])
        );

        System.out.println("Transfer committed");
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);

        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing environment variable: " + key
            );
        }

        return value;
    }
}
```

### 13.1. Cách chạy trong môi trường học tập

Chuẩn bị PostgreSQL và chạy schema ở mục 12, thêm JDBC driver vào **runtime class path**. Biên dịch:

```bash
javac JdbcPessimisticTransferDemo.java
```

Trong PowerShell, nếu môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD` đã được cấu hình và JAR driver có tại đường dẫn bạn chọn, chạy ví dụ:

```powershell
java -cp ".;path\to\postgresql-driver.jar" JdbcPessimisticTransferDemo 1 2 1000
```

Trên shell POSIX, dấu phân cách class path thường là dấu hai chấm:

```bash
java -cp ".:path/to/postgresql-driver.jar" JdbcPessimisticTransferDemo 1 2 1000
```

Nếu thành công, chương trình in:

```text
Transfer committed
```

Ban đầu A=100000 và B=50000, sau một giao dịch chuyển 1000 từ ID=1 sang ID=2 thành công, số dư lần lượt là **99000** và **51000**; cột version của cả hai tăng một đơn vị.

### 13.2. Vì sao thứ tự khóa quan trọng?

Nếu T1 khóa A rồi chờ B, trong khi T2 khóa B rồi chờ A, có thể hình thành vòng deadlock. Thứ tự ID tăng dần khiến tất cả đường code dùng **cùng thứ tự** đối với hai hàng này.

Điều đó **giảm** nguy cơ deadlock, nhưng không bảo đảm loại bỏ mọi deadlock trong hệ thống: những transaction khác có thể còn khóa bảng/row bổ sung, index hoặc đi theo thứ tự khác.

### 13.3. Vì sao code vẫn cần rollback?

- Không đủ tiền.
- Không tìm thấy ID.
- `Math.addExact` tràn số.
- `UPDATE` không tác động đúng một hàng.
- Database trả lỗi khóa, deadlock hoặc mạng.

Trong tất cả các tình huống đó, các thay đổi chưa commit không được công bố như một giao dịch thành công. Đoạn `catch` rollback rồi ném lại lỗi, để bên gọi quyết định có retry/hiển thị thông báo hay không.

### 13.4. Giới hạn ví dụ

Ứng dụng tài chính thật còn cần **idempotency key, audit trail, quyền thao tác, transaction log, kiểm toán, xử lý mất kết nối lúc commit và cách chống chuyển tiền lặp**. Mẫu này chỉ minh họa khóa và cập nhật nguyên tử ở phạm vi hai hàng, không phải hệ thống thanh toán hoàn chỉnh.

## 14. Một câu UPDATE có điều kiện: đôi khi tốt hơn SELECT FOR UPDATE

Nếu nghiệp vụ chỉ cần một thay đổi trên một hàng, có thể để database thực hiện phép cập nhật trực tiếp:

```sql
UPDATE accounts
SET balance = balance - 1000,
    version = version + 1
WHERE id = 1
  AND balance >= 1000;
```

Sau đó kiểm tra số hàng bị ảnh hưởng:

- **1 hàng:** cập nhật thành công.
- **0 hàng:** tài khoản không tồn tại hoặc tiền điều kiện `balance >= 1000` không đạt.

Một câu `UPDATE` như vậy biểu diễn phép read–modify–write trên hàng **bên trong một statement** dưới cơ chế đồng thời của DBMS, thay vì lấy giá trị cũ vào Java rồi gửi lại literal mới không có điều kiện.

Trong JDBC:

```java
String sql = """
        UPDATE accounts
        SET balance = balance - ?,
            version = version + 1
        WHERE id = ?
          AND balance >= ?
        """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, amount);
    statement.setLong(2, accountId);
    statement.setLong(3, amount);

    int affected = statement.executeUpdate();

    if (affected != 1) {
        // Không đủ điều kiện hoặc tài khoản không tồn tại.
    }
}
```

Trong snippet, `connection` là JDBC connection đã có và `amount` phải được kiểm tra **dương** trước khi dùng. Với một thao tác autocommit đơn lẻ, DBMS commit theo quy tắc kết nối. Nếu cần nhiều thay đổi phải nhất quán cùng nhau, hãy đặt các lệnh vào một transaction như mục 13.

### 14.1. Không kiểm tra bằng SELECT rồi mới UPDATE khi không cần

Đoạn sau có cửa sổ race nếu không có bảo vệ phù hợp:

```java
// Minh họa anti-pattern:
// long current = selectBalance(connection, id);
// if (current >= amount) {
//     updateBalance(connection, id, current - amount);
// }
```

Nếu chỉ cần giảm có điều kiện, `UPDATE ... WHERE balance >= ?` thường rõ và ít round-trip hơn.

### 14.2. Trường hợp cần logic ngoài một hàng

Nếu cần kiểm tra nhiều hàng, cập nhật các bảng liên quan hoặc có một invariant phức tạp, một câu update có điều kiện trên **một hàng** chưa chắc đủ. Khi đó cần transaction + locking/optimistic version/serializable theo bài toán.

## 15. Optimistic locking: kiểm tra phiên bản thay vì giữ khóa dài

**Khóa lạc quan** phù hợp khi xung đột không thường xuyên hoặc công việc đọc/tính toán có thể diễn ra trước khi quyết định commit, miễn là cuối cùng có một bước xác nhận snapshot vẫn còn hợp lệ.

Một pattern phổ biến:

1. Đọc `balance` và `version`.
2. Tính `newBalance` ở phía Java.
3. Gửi:

```sql
UPDATE accounts
SET balance = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
```

4. Nếu ảnh hưởng **1 hàng**, update thắng cuộc.
5. Nếu ảnh hưởng **0 hàng**, dữ liệu đã đổi hoặc hàng không còn tồn tại. Cần lấy snapshot mới và quyết định lại theo nghiệp vụ, **không im lặng coi là thành công**.

### 15.1. Vì sao version column hiệu quả?

Giả sử hai client cùng đọc:

```text
id=1, balance=100000, version=7
```

Client A cập nhật với `WHERE version=7`, database tăng thành 8. Client B vẫn cố update với `version=7` thì không còn hàng thỏa điều kiện; `executeUpdate()` trả 0.

Thay vì ghi đè kết quả của A, B nhận **tín hiệu conflict**.

### 15.2. Version không tự kiểm tra mọi quy tắc nghiệp vụ

Ngay cả với optimistic version, Java phải kiểm tra số dư không âm, overflow, quyền thao tác và những ràng buộc xuyên nhiều hàng. Cần constraint database làm hàng rào bảo vệ cuối.

### 15.3. Không nhầm optimistic locking với SQL transaction-free

Một câu `UPDATE ... WHERE version=?` vẫn là statement transaction theo database. Nếu thao tác gồm nhiều câu SQL/bảng phải thành công cùng nhau, chúng vẫn phải thuộc một transaction có commit/rollback rõ ràng.

## 16. Ví dụ hoàn chỉnh: optimistic update + retry xung đột phiên bản

File `JdbcOptimisticBalanceDemo.java` dùng cùng schema PostgreSQL ở mục 12. Nó thử cập nhật một số dư dựa trên `version`. Mỗi lần retry sẽ **mở một transaction mới**, đọc lại snapshot và tính lại giá trị.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JdbcOptimisticBalanceDemo {

    private static final int MAX_ATTEMPTS = 5;

    record Snapshot(long balance, long version) {
    }

    private static Snapshot readSnapshot(
            Connection connection,
            long accountId
    ) throws SQLException {

        String sql = """
                SELECT balance, version
                FROM accounts
                WHERE id = ?
                """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {

            statement.setLong(1, accountId);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                            "Account not found: " + accountId
                    );
                }

                return new Snapshot(
                        rs.getLong("balance"),
                        rs.getLong("version")
                );
            }
        }
    }

    private static int updateIfVersionMatches(
            Connection connection,
            long accountId,
            long newBalance,
            long expectedVersion
    ) throws SQLException {

        String sql = """
                UPDATE accounts
                SET balance = ?,
                    version = version + 1
                WHERE id = ?
                  AND version = ?
                """;

        try (PreparedStatement statement =
                connection.prepareStatement(sql)) {

            statement.setLong(1, newBalance);
            statement.setLong(2, accountId);
            statement.setLong(3, expectedVersion);

            return statement.executeUpdate();
        }
    }

    static void changeBalance(
            String url,
            String user,
            String password,
            long accountId,
            long delta
    ) throws SQLException {

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {

            try (Connection connection =
                    DriverManager.getConnection(url, user, password)) {

                connection.setTransactionIsolation(
                        Connection.TRANSACTION_READ_COMMITTED
                );
                connection.setAutoCommit(false);

                try {
                    Snapshot snapshot =
                            readSnapshot(connection, accountId);

                    long newBalance =
                            Math.addExact(snapshot.balance(), delta);

                    if (newBalance < 0) {
                        throw new IllegalArgumentException(
                                "Insufficient balance"
                        );
                    }

                    int updated = updateIfVersionMatches(
                            connection,
                            accountId,
                            newBalance,
                            snapshot.version()
                    );

                    if (updated == 1) {
                        connection.commit();
                        return;
                    }

                    // updated == 0: snapshot đã cũ, retry từ đầu.
                    connection.rollback();

                } catch (SQLException | RuntimeException exception) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackFailure) {
                        exception.addSuppressed(rollbackFailure);
                    }
                    throw exception;
                }
            }
        }

        throw new SQLException(
                "Optimistic conflict after " + MAX_ATTEMPTS + " attempts"
        );
    }

    public static void main(String[] args) throws SQLException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java JdbcOptimisticBalanceDemo "
                    + "<accountId> <delta>"
            );
            return;
        }

        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = requiredEnv("JDBC_PASSWORD");

        changeBalance(
                url,
                user,
                password,
                Long.parseLong(args[0]),
                Long.parseLong(args[1])
        );

        System.out.println("Update committed");
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);

        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing environment variable: " + key
            );
        }

        return value;
    }
}
```

Biên dịch:

```bash
javac JdbcOptimisticBalanceDemo.java
```

Chạy trong PowerShell sau khi cấu hình môi trường/driver:

```powershell
java -cp ".;path\to\postgresql-driver.jar" JdbcOptimisticBalanceDemo 1 500
```

Nếu thành công:

```text
Update committed
```

### 16.1. Vì sao mỗi lần thử phải có transaction mới?

Khi `UPDATE` ảnh hưởng 0 hàng, transaction hiện tại đã làm quyết định dựa trên snapshot không còn phù hợp. Code rollback, đóng connection rồi mở connection mới ở lần thử sau, **đọc lại dữ liệu** và tính toán lại.

Mẫu này xử lý **xung đột phiên bản có cập nhật trả 0**. Nó **chưa** tự xử lý các loại lỗi SQL retryable như deadlock/serialization failure hoặc mất kết nối: các lỗi đó được ném cho caller. Trong hệ thống thực tế, cần bộ retry có phân loại SQLState, giới hạn thời gian và backoff như các mục tiếp theo.

### 16.2. Side effect không được nằm trong đoạn có thể retry

Nếu tính số dư xong mà gọi HTTP thu tiền ngay trong mỗi attempt, một request có thể thu tiền **nhiều lần** khi conflict hoặc khi mất kết nối sau commit. Hãy tách quyết định database khỏi side effect và sử dụng cơ chế idempotency/outbox phù hợp.

### 16.3. Ưu điểm và giới hạn

Ưu điểm: không giữ row lock qua một khoảng thời gian đọc/tính toán dài, và cập nhật rõ ràng khi snapshot còn hợp lệ.

Giới hạn: dưới tranh chấp cao có thể phát sinh nhiều attempt thất bại; row-level locks vẫn có thể được database sử dụng khi thực hiện `UPDATE`; optimistic concurrency **không có nghĩa database không dùng bất kỳ lock nào**.

## 17. Chọn pessimistic hay optimistic locking?

| Tình huống | Pessimistic | Optimistic |
|---|---|---|
| Conflict rất hiếm, nhiều thao tác đọc | Có thể tốn lock không cần thiết | Thường phù hợp |
| Xung đột cao trên cùng hàng | Có thể giảm retry nghiệp vụ | Có thể nhiều attempt thất bại |
| Cần giữ invariant giữa nhiều hàng | Khóa đúng tập hàng, hoặc serializable | Version trên một hàng có thể chưa đủ |
| User mở màn hình chỉnh sửa trong vài phút | Không nên giữ transaction/lock suốt thời gian người dùng suy nghĩ | Version phù hợp hơn |
| Chuyển tiền giữa hai hàng trong DB | Khóa theo thứ tự, cập nhật cùng transaction | Có thể triển khai nhưng cần xử lý conflict/rollback toàn bộ |
| Cập nhật số đếm đơn giản | Có thể quá phức tạp | Thường không cần snapshot; dùng `UPDATE count=count+1` |
| Logic nhiều câu SQL phức tạp | Cần xác định thứ tự lock/transaction | Cần đảm bảo mọi cập nhật có điều kiện hoặc serializable |
| Thời gian phản hồi cần dự đoán | Có thể bị lock wait | Có thể cần retry/backoff |

Không chọn theo khẩu hiệu "optimistic luôn nhanh" hoặc "locking luôn an toàn hơn". Hãy bắt đầu từ **invariant, phạm vi dữ liệu, mức contention, cách sử dụng transaction và đặc tính DBMS**.

## 18. Deadlock: hai transaction chờ nhau

Ví dụ:

```text
T1: LOCK account 1
T2: LOCK account 2
T1: chờ LOCK account 2
T2: chờ LOCK account 1
=> vòng chờ deadlock
```

Nhiều database có cơ chế phát hiện deadlock và chọn một transaction làm victim để abort. Trong PostgreSQL, lỗi deadlock có SQLSTATE `40P01`; serialization failure thường có SQLSTATE `40001`.

### 18.1. Giảm rủi ro deadlock

- Khóa các tài nguyên **theo cùng thứ tự toàn ứng dụng**, ví dụ ID tăng dần.
- Giữ transaction ngắn, tránh network call khi giữ lock.
- Dùng index phù hợp để truy vấn chạm đúng những hàng cần xử lý.
- Không trộn lẫn thứ tự khóa qua nhiều service/DAO mà không có quy ước.
- Cho phép retry có giới hạn đối với lỗi deadlock được phân loại đúng.

### 18.2. Deadlock vẫn có thể xảy ra khi đã sắp thứ tự

Một transaction có thể khóa cả bảng/hàng qua trigger, index maintenance, FK hoặc đường code khác. Quy tắc thứ tự làm **giảm** rủi ro, không phải bằng chứng không còn deadlock tuyệt đối.

## 19. Lock wait timeout, NOWAIT và SKIP LOCKED

Một transaction có thể chờ lâu vì hàng đang bị giữ lock. Trong PostgreSQL, có thể dùng biến thể:

```sql
SELECT id
FROM jobs
WHERE status = 'PENDING'
ORDER BY id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` bỏ qua những hàng không thể lấy row lock ngay theo cơ chế của hệ quản trị. Nó hữu ích trong **một số kiểu worker queue** có nhiều consumer tranh claim job.

### 19.1. Không dùng SKIP LOCKED bừa bãi cho dữ liệu giao dịch

Nếu chuyển tiền cần tài khoản ID=1 đang bị khóa, **bỏ qua hàng đó** không có nghĩa tài khoản không tồn tại hoặc không có tiền. Với nghiệp vụ cần trạng thái đầy đủ và nhất quán, `SKIP LOCKED` có thể cho góc nhìn thiếu hàng.

### 19.2. NOWAIT

Với PostgreSQL:

```sql
SELECT balance
FROM accounts
WHERE id = 1
FOR UPDATE NOWAIT;
```

Thay vì chờ row lock đang bị giữ, truy vấn có thể lỗi ngay khi không thể lấy khóa cần thiết. App cần phân biệt **tài nguyên đang bận** với **không tìm thấy dữ liệu** và quyết định retry hoặc trả phản hồi hợp lý.

### 19.3. Query timeout và transaction timeout

JDBC có `Statement.setQueryTimeout(seconds)`; khả năng thực thi và phạm vi tác dụng tùy driver. Database thường cũng có thiết lập lock timeout/statement timeout. **Không giả định query timeout tương đương hủy sạch toàn bộ transaction**. Sau timeout, cần kiểm tra transaction state và rollback nếu không thể tiếp tục an toàn.

## 20. Retry transaction: phân loại lỗi và làm lại toàn bộ quyết định

Một số lỗi cạnh tranh là **transient**: chúng có thể hết nếu transaction được thử lại trên trạng thái mới. Nhưng không phải mọi `SQLException` đều nên retry.

Ví dụ chính sách khái niệm:

| Tình huống | Có nên retry? | Điều kiện |
|---|---|---|
| Optimistic version mismatch (update 0) | Có thể | Đọc snapshot mới, giới hạn attempt |
| Serialization failure | Thường có thể | Retry toàn transaction, theo contract DBMS |
| Deadlock victim | Thường có thể | Retry transaction trong giới hạn |
| Unique constraint violation | Tùy nghiệp vụ | Có thể là conflict thật cần báo caller |
| Sai password hoặc quyền DB | Không | Cấu hình/authorization không tự hết |
| SQL syntax error | Không | Cần sửa code |
| Không đủ tiền | Thường không | Là kết quả nghiệp vụ, không phải transient SQL error |
| Mất kết nối **sau khi có thể đã commit** | Cần đặc biệt cẩn thận | Trạng thái commit có thể không xác định; dùng idempotency/reconciliation |

### 20.1. SQLState và JDBC exception

`SQLException.getSQLState()` cung cấp mã theo DBMS/driver. Với PostgreSQL, thường:

- `40001`: serialization failure.
- `40P01`: deadlock detected.

`SQLTransactionRollbackException` và `SQLTransientException` là các kiểu Java có thể hỗ trợ phân loại lỗi trong một số driver, nhưng **đừng giả định mọi driver dùng cùng subclass hoặc SQLState**. Luôn tham chiếu tài liệu DBMS đang vận hành.

Ví dụ hàm kiểm tra dành riêng PostgreSQL:

```java
import java.sql.SQLException;

static boolean isRetryablePostgres(SQLException exception) {
    String sqlState = exception.getSQLState();
    return "40001".equals(sqlState)
            || "40P01".equals(sqlState);
}
```

Đoạn trên chưa kiểm tra các exception lồng/chained; trong code production có thể cần duyệt `getNextException()` hoặc exception cause theo chính sách.

### 20.2. Retry đúng phạm vi

Mỗi attempt cần làm lại:

1. Mở transaction mới.
2. Đọc trạng thái dùng để quyết định.
3. Áp dụng business validation.
4. Thực hiện mọi câu SQL phụ thuộc vào quyết định.
5. Commit.
6. Nếu gặp lỗi retryable: rollback và thử lại với snapshot mới.

Không thể chỉ retry `COMMIT` hoặc câu `UPDATE` cuối sau khi transaction đã bị abort vì các quyết định trước đó dựa vào snapshot cũ.

### 20.3. Retry có giới hạn và backoff

Ví dụ chính sách:

```text
Tối đa 3-5 attempts
Giới hạn deadline tổng
Backoff tăng dần với chút jitter
Ghi metrics conflict/retry
Trả lỗi quá tải khi không thể phục hồi
```

Không retry vô hạn: ở contention cao, một vòng retry không giới hạn có thể làm database càng quá tải. Chọn số attempt và backoff dựa trên độ trễ SLO và mức tải thực.

## 21. Idempotency và lỗi không rõ kết quả commit

Một tình huống khó: ứng dụng gửi `COMMIT`, database commit thành công nhưng kết nối bị ngắt **trước khi ứng dụng nhận phản hồi**.

App thấy lỗi mạng, nhưng không chắc transaction đã commit hay chưa. Nếu tự động làm lại thao tác chuyển tiền mà không có danh tính giao dịch, có thể ghi tiền **hai lần**.

### 21.1. Idempotency key

Mỗi lệnh nghiệp vụ có thể có một khóa duy nhất do caller cung cấp. Ví dụ thiết kế bảng:

```sql
CREATE TABLE transfer_requests (
    request_id VARCHAR(100) PRIMARY KEY,
    from_id BIGINT NOT NULL,
    to_id BIGINT NOT NULL,
    amount BIGINT NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL
);
```

Một transaction có thể ghi nhận `request_id` cùng thay đổi số dư theo hợp đồng. Lần gọi lại với cùng key cần phân biệt:

- Yêu cầu đã hoàn tất: trả kết quả đã ghi nhận.
- Yêu cầu đang xử lý: chờ/đọc trạng thái theo quy tắc.
- Key trùng nhưng payload khác: báo lỗi thay vì thực hiện nội dung mới.

**Một PRIMARY KEY đơn lẻ chưa tạo thành giao thức idempotency hoàn chỉnh.** Bạn còn phải xác định thứ tự ghi request/result, rollback, giao dịch đang chạy, request lỗi, và cách phục hồi sau crash.

### 21.2. External side effect và transactional outbox

Giao dịch SQL không tự bao trùm email, HTTP call hoặc hệ thống message bên ngoài. Một mẫu thiết kế phổ biến là **transactional outbox**: ghi business data và một outbox event trong cùng database transaction, rồi một worker riêng đọc/publish event. Consumer nên có idempotency vì event có thể được gửi lại.

Đây là kiến trúc hỗ trợ tính nhất quán giữa dữ liệu và phát sự kiện; **không phải bảo đảm exactly-once delivery tự động**.

## 22. SAVEPOINT không phải transaction độc lập

JDBC có `Savepoint`:

```java
import java.sql.Connection;
import java.sql.Savepoint;

connection.setAutoCommit(false);

Savepoint savepoint = connection.setSavepoint();

try {
    // Thực hiện một nhóm statement.
} catch (Exception exception) {
    connection.rollback(savepoint);
}
```

Đây là **khung minh họa** trong một transaction đã bắt đầu. Savepoint cho phép rollback một phần trong các trường hợp DBMS hỗ trợ, nhưng:

- Không tạo transaction độc lập có thể commit riêng.
- Không thay thế xử lý outer transaction.
- Không bảo đảm mọi loại lỗi cho phép tiếp tục transaction tùy ý.
- Không thay thế yêu cầu retry toàn transaction khi serialization failure/deadlock khiến transaction không còn dùng được.

Nếu cần xác minh hỗ trợ, dùng `DatabaseMetaData.supportsSavepoints()` và xem hành vi engine.

## 23. Giữ transaction ngắn, tránh giữ khóa khi gọi dịch vụ ngoài

Một anti-pattern:

```text
BEGIN
SELECT ... FOR UPDATE
Gọi HTTP bên ngoài (2 giây)
Chờ người dùng xác nhận (nhiều giây)
UPDATE ...
COMMIT
```

Hàng bị khóa trong lúc chờ các hệ thống không kiểm soát được, làm tăng lock contention và latency. Transaction càng dài, nguy cơ deadlock, timeout hoặc conflict càng lớn.

Một thiết kế bền hơn có thể gồm:

1. Xác thực trước những dữ liệu không cần khóa.
2. Gọi dịch vụ ngoài trước hoặc sau transaction theo kiến trúc saga/outbox/idempotency đã chọn.
3. Trong transaction, chỉ thực hiện các câu đọc/ghi cần giữ invariant.
4. Commit nhanh rồi xử lý bước hậu giao dịch với cơ chế khôi phục.

**Không được đơn giản chuyển HTTP call ra ngoài transaction nếu việc đó phá tính đúng đắn nghiệp vụ.** Cần xác định quy trình đảm bảo nhất quán giữa các hệ thống, nhất là thanh toán.

## 24. Connection pool, virtual threads và concurrency ở tầng DB

Trong Java hiện hành, virtual threads giúp phục vụ nhiều tác vụ blocking ở phía ứng dụng. Nhưng database vẫn có:

- Giới hạn số connection.
- Số transaction đang hoạt động.
- Giới hạn lock, CPU, I/O.
- Chi phí mỗi truy vấn và mỗi snapshot.
- Khả năng bị nghẽn ở những hàng "hot".

**Nhiều virtual threads không có nghĩa nên mở hàng nghìn JDBC connection.** Nên dùng connection pool có giới hạn, admission/backpressure và query/transaction timeout phù hợp.

### 24.1. Không chia sẻ một Connection cho nhiều transaction đồng thời

`Connection` biểu diễn trạng thái session/transaction. Để tránh tác vụ A vô tình commit/rollback công việc của tác vụ B, không truyền cùng một connection mutable cho các thread đang chạy transaction độc lập.

Mỗi đơn vị công việc thường **mượn một connection từ pool**, dùng nó trong phạm vi transaction, rồi trả về pool. Cơ chế reset isolation, auto-commit và trạng thái session cần theo contract của pool.

### 24.2. Không thay isolation cho mọi request theo cảm tính

Tăng tất cả transaction lên `SERIALIZABLE` có thể làm tăng abort/retry; giảm tất cả xuống `READ_COMMITTED` có thể làm sai invariant nếu code đang dựa vào snapshot mạnh hơn. Hãy xác định isolation **theo workflow** và kiểm thử dưới contention.

## 25. Observability: giám sát xung đột và khóa

Các chỉ số quan trọng:

| Chỉ số | Cần hiểu điều gì |
|---|---|
| Lock wait time | Transaction phải chờ nhau bao lâu |
| Deadlock count | Có vòng chờ bị DBMS phát hiện hay không |
| Serialization failures | Lịch đồng thời bị DBMS từ chối |
| Optimistic version conflicts | Bao nhiêu cập nhật bị snapshot cũ |
| Transaction duration | Lock/snapshot tồn tại bao lâu |
| Connection pool saturation | Có thiếu connection để xử lý request |
| Query latency p95/p99 | Độ trễ đuôi dưới tải |
| Retry rate/attempts | Transaction có đang bị retry quá nhiều |
| Rows affected | Cập nhật kỳ vọng 1 hàng có thực sự là 1 |
| Constraint violations | Ứng dụng có thường xuyên vi phạm invariant cuối cùng |

Cần log transaction/request ID phù hợp nhưng không in thông tin xác thực, số dư cá nhân hay dữ liệu nhạy cảm mà không có kiểm soát. Xác định correlation ID và nguyên nhân rollback giúp điều tra mà không phải phỏng đoán từ thứ tự timestamp.

## 26. Bảng quyết định nhanh

| Nhu cầu | Giải pháp nên cân nhắc | Cảnh báo |
|---|---|---|
| Tăng số đếm trên một hàng | `UPDATE count=count+1` | Kiểm tra overflow/ràng buộc |
| Trừ số dư có kiểm tra | `UPDATE ... WHERE balance >= ?` | Kiểm tra rows affected |
| Đọc rồi sửa một hàng có tranh chấp cao | `SELECT FOR UPDATE` trong transaction | Lock wait/deadlock |
| Màn hình edit lâu, xung đột ít | Optimistic version | Xử lý 0 rows và UI conflict |
| Invariant liên quan nhiều hàng | Khóa tập hàng phù hợp hoặc SERIALIZABLE | Phân tích write skew và predicate |
| Transaction bị abort do serialization | Retry toàn transaction | Bounded attempts, backoff, idempotency |
| Cập nhật tài khoản ở hai hàng | Một transaction với thứ tự khóa nhất quán | Không giữ lock khi gọi HTTP |
| Đọc snapshot báo cáo nhiều câu SQL | Isolation có snapshot phù hợp DBMS | Read committed có thể cho kết quả khác giữa câu |
| Worker queue với nhiều consumer | `SKIP LOCKED` nếu engine/thiết kế phù hợp | Không dùng cho dữ liệu cần đọc đầy đủ |
| Nhiều virtual threads truy cập DB | Bounded connection pool | Không tăng connection vô hạn |

## 27. Các lỗi và hiểu lầm thường gặp

| Hiểu lầm | Điều đúng |
|---|---|
| `synchronized` trong Java bảo vệ mọi instance ứng dụng | Không ngăn process/service khác cập nhật DB |
| Đã bật auto-commit thì hai câu SQL tự là một transaction | Thường mỗi statement là một transaction riêng |
| `READ COMMITTED` tự ngăn mọi lost update | Phải xét read–modify–write và semantics DBMS |
| `REPEATABLE READ` luôn tương đương SERIALIZABLE | Có thể xảy ra write skew trong nhiều hệ MVCC |
| `SERIALIZABLE` nghĩa database không bao giờ abort | Serialization failure là một cách DB bảo toàn tính đúng đắn |
| DB dùng MVCC nên không có lock | Ghi/khóa hàng vẫn có thể xung đột |
| `SELECT FOR UPDATE` dùng giống nhau trên mọi DB | Syntax/semantics phụ thuộc dialect và isolation |
| Khóa một hàng bảo vệ mọi predicate nhiều hàng | Write skew/phantom vẫn cần phân tích |
| `executeUpdate() == 0` luôn là lỗi JDBC | Có thể là conflict/không đủ điều kiện nghiệp vụ |
| Cột `version` tự sửa dữ liệu sai | Nó phát hiện snapshot cũ; vẫn cần validation/constraint |
| Optimistic locking không dùng row lock nào | Database vẫn có lock khi thực thi `UPDATE` |
| Retry chỉ riêng câu UPDATE thất bại là đủ | Nhiều lỗi cần retry **toàn transaction** |
| Bắt mọi `SQLException` rồi retry mãi | Có lỗi cấu hình, SQL hoặc nghiệp vụ không transient |
| Gọi `COMMIT` lỗi nghĩa chắc chắn không commit | Mất kết nối có thể khiến outcome không rõ |
| Có idempotency key trong request nghĩa exactly-once | Cần giao thức lưu kết quả và phục hồi rõ |
| `SKIP LOCKED` luôn trả đầy đủ tập dữ liệu | Nó có thể bỏ qua hàng đang khóa |
| Query timeout tự rollback và phục hồi connection | Phụ thuộc driver/DBMS, cần kiểm tra trạng thái |
| Virtual threads loại bỏ giới hạn DB connections | Database vẫn có pool và tài nguyên hữu hạn |
| Giữ transaction mở khi chờ HTTP không sao | Tăng lock wait, timeout, deadlock risk |

## 28. Bài tập thực hành

### Bài 1. Mô phỏng lost update

Tạo bảng `counters(id, value)` với một hàng giá trị ban đầu 0. Viết hai transaction: cùng `SELECT value`, cộng 1 ở Java, rồi `UPDATE value=?`. Chạy đồng thời dưới isolation thích hợp để quan sát khả năng mất cập nhật. Sau đó sửa thành `UPDATE counters SET value=value+1 WHERE id=?`.

### Bài 2. Các hiện tượng isolation

Vẽ timeline hai transaction minh họa dirty read, non-repeatable read và phantom read. Xác định level tối thiểu có mục tiêu ngăn mỗi hiện tượng theo bảng lý thuyết, sau đó tìm hiểu mức thực thi cụ thể của DBMS bạn dùng.

### Bài 3. JDBC transaction

Viết một method chuyển tiền sử dụng `Connection.setAutoCommit(false)`, hai `PreparedStatement` và `commit`/`rollback`. Giải thích tình huống câu update thứ hai lỗi và vì sao không được để câu đầu commit riêng.

### Bài 4. Pessimistic lock

Dùng PostgreSQL và `SELECT ... FOR UPDATE` để khóa một account trước khi trừ tiền. Mở hai session, giữ transaction T1 chưa commit rồi thử update từ T2. Mô tả lock wait và sự khác nhau giữa commit/rollback.

### Bài 5. Atomic conditional update

Viết `withdraw(accountId, amount)` bằng **một câu SQL** có điều kiện `balance >= ?`. Kiểm tra `executeUpdate()` và xử lý trường hợp 0 hàng. Thử nhiều client rút cùng một tài khoản.

### Bài 6. Optimistic version

Tạo bảng `documents(id, content, version)`. Hai client cùng đọc version 4 và sửa content khác nhau. Sử dụng `UPDATE ... WHERE version=?`; giải thích tại sao chỉ một update thành công, rồi đề xuất UI cho conflict (thông báo hoặc merge).

### Bài 7. Write skew

Thiết kế bảng bác sĩ trực và invariant "ít nhất một bác sĩ trực". Dùng hai transaction cùng đọc số bác sĩ rồi mỗi bên tắt trạng thái của một người. Phân tích khi nào write skew có thể xảy ra. So sánh giải pháp khóa tập hàng với `SERIALIZABLE`.

### Bài 8. Deadlock và lock ordering

Tạo hai transaction chuyển tiền ngược chiều với thứ tự khóa đối nghịch. Quan sát lỗi deadlock trong database thử nghiệm. Sau đó sửa toàn bộ code để khóa hai account theo ID tăng dần; giải thích giới hạn của biện pháp này.

### Bài 9. Retry transaction

Viết wrapper retry tối đa ba lần đối với PostgreSQL SQLSTATE `40001` và `40P01`, mỗi lần dùng **connection/transaction mới**. Không retry đối với lỗi syntax hoặc không đủ số dư. Thêm backoff nhỏ và tổng deadline.

### Bài 10. Idempotency

Thiết kế bảng `transfer_requests` có unique request ID. Mô tả cách xử lý nếu một client gửi lại yêu cầu vì mất response sau commit, và cách ngăn payload khác sử dụng cùng key. Giải thích tại sao retry HTTP không đủ để bảo đảm exactly-once.

### Bài 11. Cô lập nhiều tầng

Một ứng dụng sử dụng Java virtual threads và connection pool tối đa 20 connection, phục vụ 1000 request đồng thời. Chỉ ra bottleneck có thể ở pool, database lock và external API. Đề xuất timeout, admission control và metrics cần theo dõi.

### Bài 12. Lựa chọn giải pháp

Với bốn tình huống: tăng view count, edit profile qua biểu mẫu lâu, đặt vé chỉ còn một ghế, điều phối queue nhiều worker, hãy chọn atomic SQL, optimistic version, pessimistic lock hoặc SKIP LOCKED phù hợp. Nêu invariant và rủi ro còn lại.

## 29. Tóm tắt

**Isolation** quyết định cách transaction nhìn và phối hợp với các transaction đồng thời. Bốn mức JDBC cung cấp tên gọi chuẩn, nhưng cần hiểu semantics thực tế của DBMS, đặc biệt với MVCC, `REPEATABLE READ`, `SERIALIZABLE` và các loại anomaly như **lost update** hay **write skew**.

**Pessimistic locking** như PostgreSQL `SELECT ... FOR UPDATE` thích hợp khi phải khóa hàng trước lúc ra quyết định; hãy giữ transaction ngắn, khóa tài nguyên theo thứ tự nhất quán và xử lý deadlock. **Optimistic locking** dùng `version` cùng `UPDATE ... WHERE version=?` để phát hiện snapshot đã cũ; khi conflict phải đọc lại và quyết định lại, không ghi đè âm thầm.

Nếu chỉ cần phép tăng/giảm có điều kiện trên **một hàng**, một statement `UPDATE` biểu diễn trực tiếp phép toán thường đơn giản và an toàn hơn luồng `SELECT` rồi ghi giá trị tính ở Java. Với invariant trên **nhiều hàng**, cần phân tích chiến lược khóa hoặc dùng isolation mạnh và cơ chế retry.

Cuối cùng, **retry phải có giới hạn và đúng phạm vi transaction**, đồng thời phân biệt serialization/deadlock với lỗi nghiệp vụ. Mất kết nối sau `COMMIT` có thể tạo kết quả không rõ ràng; hãy thiết kế **idempotency**, reconciliation và outbox nếu cần phối hợp với hệ thống ngoài. Mục tiêu của Java 27 JDBC không chỉ là "SQL chạy được", mà là bảo toàn invariant dữ liệu trong thực tế nhiều request, nhiều thread và nhiều instance.

## Tài liệu tham khảo

- [Java SE 27 API — java.sql.Connection](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/Connection.html)
- [Java SE 27 API — java.sql.PreparedStatement](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/PreparedStatement.html)
- [Java SE 27 API — java.sql.SQLException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLException.html)
- [Java SE 27 API — java.sql.SQLTransactionRollbackException](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html)
- [Java SE 27 API — java.sql.DatabaseMetaData](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/java/sql/DatabaseMetaData.html)
- [Java SE 27 API — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.sql/javax/sql/DataSource.html)
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — SELECT / FOR UPDATE](https://www.postgresql.org/docs/current/sql-select.html)
- [PostgreSQL — Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html)
