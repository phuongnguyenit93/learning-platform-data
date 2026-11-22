# Dùng nhiều kết nối thật thay vì mô phỏng nhiều luồng trên một giao dịch

Kiểm thử đồng thời cơ sở dữ liệu phải tạo ra các transaction độc lập cùng truy cập database trong một khoảng thời gian có giao nhau. Việc chỉ tạo nhiều Java thread nhưng để tất cả dùng chung một JDBC `Connection` không mô phỏng được nhiều transaction độc lập. Database nhìn thấy một session với một transaction context; các câu lệnh có thể bị trộn trong cùng transaction hoặc bị driver tuần tự hóa.

Muốn kiểm tra blocking, lost update, optimistic locking, deadlock hoặc isolation level, hãy dùng **nhiều connection/session độc lập**, mỗi connection sở hữu transaction riêng. Các thread có thể giúp tạo overlap, nhưng chính các session và transaction độc lập mới tạo nên cuộc cạnh tranh ở database.

Một mô hình kiểm thử điển hình:

```text
Test runner
   |
   +---- Worker A ---- Connection A ---- Transaction A ----+
   |                                                       |
   +---- Worker B ---- Connection B ---- Transaction B ----+--> Database
   |                                                       |
   +---- Worker C ---- Connection C ---- Transaction C ----+
```

Mỗi worker mượn connection riêng từ `DataSource`, mở transaction riêng, thực hiện các bước được đồng bộ bằng barrier/latch, rồi commit hoặc rollback. Pool phải cấp đủ connection đồng thời; nếu pool chỉ có một connection, các worker có thể phải xếp hàng trước khi đến database và bài test sẽ không tạo được concurrency như dự kiến.

## 1. Thread không đồng nghĩa với transaction

Thread là đơn vị thực thi trong ứng dụng. Connection là một phiên giao tiếp với database. Transaction là đơn vị công việc được database quản lý. Ba khái niệm liên quan nhưng không thay thế cho nhau.

| Cách chạy | Database nhìn thấy gì? | Có phù hợp để kiểm tra hai transaction cạnh tranh? |
|---|---|---|
| Hai thread dùng chung một `Connection` | Một session/connection; các thao tác có thể nằm trong cùng transaction | Không. Không tạo ra hai transaction độc lập. |
| Một thread lần lượt mở hai connection nhưng chỉ chạy một transaction tại một thời điểm | Hai session khác nhau nhưng không nhất thiết có thời gian thực thi chồng lấn | Có thể kiểm tra trạng thái session, nhưng chưa đủ để tái hiện concurrency thực sự nếu không giữ transaction mở và điều phối lịch. |
| Hai thread, mỗi thread mượn một connection và mở transaction riêng | Hai session và hai transaction độc lập, có thể cùng hoạt động | Có. Đây là cách thông dụng để kiểm tra cạnh tranh. |
| Hai client SQL riêng biệt, mỗi client giữ transaction riêng | Hai session độc lập do người kiểm thử điều khiển | Có. Rất hữu ích để quan sát thủ công blocking và lock. |
| Nhiều thread gọi repository nhưng mọi lời gọi tham gia cùng transaction context | Có thể vẫn chỉ là một transaction hoặc context không an toàn | Không thể giả định đây là nhiều transaction; phải xác minh cách framework quản lý context. |

Ví dụ sai:

```java
Connection shared = dataSource.getConnection();
shared.setAutoCommit(false);

executor.submit(() -> updateAccount(shared, 10));
executor.submit(() -> updateAccount(shared, 20));
```

Hai task đang cùng dùng một connection. JDBC `Connection` nói chung không được thiết kế để nhiều thread đồng thời điều khiển cùng trạng thái transaction. Một task có thể commit hoặc rollback công việc của task kia; statement có thể xen kẽ ngoài dự kiến. Driver cũng có thể tuần tự hóa thao tác trên connection, khiến bài test không tạo được tình huống mà người viết nghĩ rằng mình đang kiểm tra.

Thiết kế đúng là chia sẻ `DataSource` hoặc connection pool thread-safe, rồi để mỗi task tự mượn và đóng connection của mình:

```java
executor.submit(() -> {
    try (Connection connection = dataSource.getConnection()) {
        // Transaction riêng của worker này.
    }
});
```

## 2. Xác nhận mỗi worker thực sự có một session riêng

Không nên chỉ suy luận từ số thread. Hãy lấy session/connection ID từ database ngay sau khi mượn connection.

| Hệ quản trị | Truy vấn xem session ID |
|---|---|
| PostgreSQL | `SELECT pg_backend_pid();` |
| MySQL | `SELECT CONNECTION_ID();` |
| SQL Server | `SELECT @@SPID;` |

Ví dụ PostgreSQL:

```sql
SELECT pg_backend_pid();
```

Nếu Worker A và Worker B đang đồng thời giữ connection, chúng phải thấy hai backend PID khác nhau. Với MySQL, so sánh `CONNECTION_ID()`; với SQL Server, so sánh `@@SPID`.

Một pool có thể tái sử dụng cùng connection vật lý cho các request chạy lần lượt. Điều đó bình thường. Yêu cầu của bài test là khi các worker cần đồng thời giữ transaction, mỗi worker phải có một connection được cấp riêng và session ID phải khác nhau.

Hãy ghi session ID cùng tên worker, transaction ID nếu engine cung cấp, isolation level, thời điểm bắt đầu và câu SQL đang chạy. Thông tin này giúp phân biệt “hai thread trong ứng dụng” với “hai session thực sự đang chờ nhau trong database”.

## 3. Chuẩn bị môi trường kiểm thử đúng

Trước khi tạo concurrency, cần bảo đảm môi trường có thể thực sự chạy nhiều transaction cùng lúc.

### Pool có đủ connection

Nếu có hai worker cần đồng thời giữ transaction, pool phải cho phép ít nhất hai connection được mượn cùng lúc. Nếu có bốn worker cùng chờ barrier sau khi mở transaction, pool cần ít nhất bốn connection cộng thêm connection dành cho test runner/observer nếu cần.

Ví dụ, pool size bằng `1`:

```text
Worker A mượn connection duy nhất và chờ barrier
Worker B chờ mượn connection
Worker C chờ mượn connection

Barrier đợi A, B, C cùng sẵn sàng
Nhưng B và C không thể lấy connection để tới barrier
=> Test treo hoặc timeout trước khi database thấy concurrency.
```

Đây là lỗi ở tầng pool, không phải deadlock database. Khi điều tra test bị treo, kiểm tra cả số connection active/idle và số thread đang chờ pool.

### Dùng đúng hệ quản trị và engine

Hành vi transaction phụ thuộc engine, phiên bản, isolation level, cấu hình MVCC/row versioning, index và driver. H2 hoặc một database giả lập có thể không tái hiện đúng khóa, deadlock, gap lock hoặc serialization failure của PostgreSQL, MySQL InnoDB hay SQL Server.

Với kiểm thử tích hợp về concurrency, nên chạy trên cùng hệ quản trị và phiên bản gần với production. Có thể dùng Testcontainers để khởi chạy database thật trong CI, hoặc một database kiểm thử riêng được quản lý. Nếu dùng H2 cho unit test nhanh, không lấy kết quả đó làm bằng chứng rằng hành vi khóa của production đã được xác nhận.

### Thiết lập isolation level tường minh

Không dựa vào giá trị mặc định của driver hoặc database. Mỗi worker nên đặt isolation level cần kiểm tra hoặc xác minh nó đã được cấu hình đúng.

Với JDBC:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
connection.setAutoCommit(false);
```

Thứ tự cấu hình và việc thay đổi isolation level trong connection đã có transaction phụ thuộc driver/database. Thực hiện trước câu SQL đầu tiên của transaction và kiểm tra lỗi nếu engine không hỗ trợ mức yêu cầu.

### Fixture phải được commit trước khi worker bắt đầu

Tạo dữ liệu ban đầu trong transaction riêng và commit trước khi các worker chạy. Nếu test setup giữ dữ liệu chưa commit trong một transaction của test thread, các connection worker khác có thể không nhìn thấy fixture đó.

Với dữ liệu dùng chung, dùng khóa test riêng hoặc ID duy nhất để các test chạy song song không ghi đè fixture của nhau.

## 4. Điều phối concurrency bằng barrier và latch

Một bài test đồng thời cần kiểm soát thời điểm các worker đi qua những điểm quan trọng. Không nên dùng `Thread.sleep(100)` để giả định worker kia đã đọc xong hoặc đã lấy khóa.

Các công cụ đồng bộ hữu ích trong Java:

- `CountDownLatch`: một hoặc nhiều worker báo đã đến một điểm; thread điều phối đợi đủ tín hiệu.
- `CyclicBarrier`: một nhóm worker chờ nhau tại cùng một điểm rồi cùng tiếp tục.
- `Phaser`: điều phối nhiều pha giữa nhiều worker khi test có nhiều giai đoạn.
- `Semaphore`: giới hạn số worker được đi vào một vùng kiểm thử.
- `Future.get(timeout, unit)`: chờ kết quả có giới hạn thời gian và phát hiện task không kết thúc.

Barrier nên đặt tại ranh giới nghiệp vụ muốn kiểm tra. Ví dụ, để tái hiện lost update, mỗi transaction đọc xong giá trị cũ rồi mới được phép tiếp tục ghi. Đặt barrier sau `SELECT` bảo đảm cả hai đã quan sát dữ liệu trước khi bất kỳ worker nào thực hiện `UPDATE`.

Ngược lại, nếu đang kiểm tra `SELECT ... FOR UPDATE`, worker thứ hai có thể bị chặn ngay tại câu SELECT. Không đặt barrier yêu cầu cả hai worker vượt qua locking read; worker thứ hai không thể tới barrier cho đến khi worker đầu nhả khóa. Thay vào đó, dùng latch để worker A báo đã lấy khóa, rồi cho B bắt đầu yêu cầu khóa và quan sát trạng thái chờ.

## 5. Thí nghiệm hai connection: tái hiện lost update

Giả sử bảng thử nghiệm:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO accounts (id, balance)
VALUES (1, 100.00);
```

Hai transaction cùng đọc `balance = 100`. Worker A cộng `10`; Worker B trừ `20`. Nếu cả hai tính giá trị tuyệt đối trong ứng dụng rồi ghi lại, một cập nhật có thể ghi đè cập nhật kia.

Lịch mong muốn:

```text
Worker A / Connection A             Worker B / Connection B
-----------------------             -----------------------
BEGIN                               BEGIN
SELECT balance -> 100               SELECT balance -> 100
          \                         /
           \---- barrier ----------/
UPDATE balance = 110                UPDATE balance = 80
COMMIT                              COMMIT
```

Vì hai lần đọc đều xảy ra trước hai lần ghi, giá trị cuối thường là `110` hoặc `80` tùy transaction ghi sau cùng; giá trị đúng nếu cả hai phép cộng/trừ được áp dụng là `90`. Test này cho thấy nhiều thread dùng chung connection sẽ không tái hiện được hai transaction độc lập như thế nào.

### Java integration test minh họa

Đoạn code dưới đây là khung kiểm thử JDBC. Mỗi task mượn một connection riêng và dùng một transaction riêng:

```java
ExecutorService workers = Executors.newFixedThreadPool(2);
CyclicBarrier bothRead = new CyclicBarrier(2);

Callable<Void> addTen = () -> {
    updateFromSnapshot(dataSource, bothRead, new BigDecimal("10.00"));
    return null;
};

Callable<Void> subtractTwenty = () -> {
    updateFromSnapshot(dataSource, bothRead, new BigDecimal("-20.00"));
    return null;
};

try {
    Future<Void> a = workers.submit(addTen);
    Future<Void> b = workers.submit(subtractTwenty);

    a.get(10, TimeUnit.SECONDS);
    b.get(10, TimeUnit.SECONDS);
} finally {
    workers.shutdownNow();
}
```

Hàm worker:

```java
static void updateFromSnapshot(
        DataSource dataSource,
        CyclicBarrier bothRead,
        BigDecimal delta) throws Exception {

    try (Connection connection = dataSource.getConnection()) {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_READ_COMMITTED);
        connection.setAutoCommit(false);

        try {
            BigDecimal observed;
            try (PreparedStatement select = connection.prepareStatement(
                    "SELECT balance FROM accounts WHERE id = 1")) {
                try (ResultSet rs = select.executeQuery()) {
                    if (!rs.next()) {
                        throw new IllegalStateException("Missing test account");
                    }
                    observed = rs.getBigDecimal(1);
                }
            }

            // Cả hai transaction phải đọc xong trước khi bất kỳ bên nào ghi.
            bothRead.await(5, TimeUnit.SECONDS);

            BigDecimal newBalance = observed.add(delta);
            try (PreparedStatement update = connection.prepareStatement(
                    "UPDATE accounts SET balance = ? WHERE id = 1")) {
                update.setBigDecimal(1, newBalance);
                if (update.executeUpdate() != 1) {
                    throw new IllegalStateException("Account was not updated");
                }
            }

            connection.commit();
        } catch (Exception ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    }
}
```

Đây là ví dụ minh họa cho một database hỗ trợ `READ COMMITTED` với hành vi cập nhật hàng thông thường. Cần bổ sung import, fixture setup/cleanup và cấu hình pool trong test thực tế. Nếu một worker lỗi trước barrier, barrier có timeout để task còn lại không treo vô hạn; test phải báo lỗi thay vì bỏ qua worker đó.

Sau khi cả hai hoàn tất, đọc giá trị bằng một connection mới. Nếu kết quả là `110` hoặc `80`, test đã tái hiện lost update theo lịch được điều khiển. Không khẳng định một giá trị thắng cụ thể vì thứ tự hai câu UPDATE sau barrier không được cố định.

## 6. So sánh với cập nhật nguyên tử trên nhiều connection

Thay vì đọc giá trị về ứng dụng rồi ghi số tuyệt đối, có thể biểu diễn ý định bằng phép cập nhật tương đối:

```sql
UPDATE accounts
SET balance = balance + :delta
WHERE id = 1;
```

Hai transaction thực hiện lần lượt với `delta = +10` và `delta = -20`. Database đồng bộ các cập nhật ghi trên cùng hàng và áp dụng từng phép cộng/trừ lên giá trị hiện tại. Kết quả cuối là `90.00` nếu cả hai commit thành công.

Một test đối chiếu nên chạy cùng lịch đồng bộ nhưng thay câu cập nhật bằng:

```java
try (PreparedStatement update = connection.prepareStatement(
        "UPDATE accounts SET balance = balance + ? WHERE id = 1")) {
    update.setBigDecimal(1, delta);
    update.executeUpdate();
}
```

Kết quả mong đợi là cả hai thao tác đều được áp dụng, không phụ thuộc worker nào ghi trước. Nếu nghiệp vụ có điều kiện như số dư không được âm, thêm điều kiện nguyên tử:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :id
  AND balance >= :amount;
```

Kiểm tra row count để biết phép trừ có thành công. Một câu lệnh nguyên tử vẫn có thể chờ khóa; điểm khác là phép tính được thực hiện trên giá trị hiện tại tại database thay vì một giá trị cũ đã tính trước ở ứng dụng.

## 7. Thí nghiệm optimistic locking với hai transaction độc lập

Chuẩn bị bảng có version:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    content VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO documents (id, content, version)
VALUES (1, 'original', 1);
```

Hai worker đọc `version = 1`, sau đó đồng bộ tại barrier. Mỗi worker cập nhật với điều kiện version:

```sql
UPDATE documents
SET content = :newContent,
    version = version + 1
WHERE id = 1
  AND version = 1;
```

Kết quả mong đợi:

- Một worker cập nhật đúng một hàng và commit.
- Worker còn lại cập nhật `0` hàng vì version không còn bằng `1`.
- Version cuối là `2`, không phải `3`.
- Nội dung của worker thắng được giữ lại.

Đây là bài test phù hợp để xác nhận optimistic locking thực sự được kiểm tra ở database. Nếu hai worker dùng chung connection/transaction, điều kiện version có thể được thực hiện tuần tự trong một context và không tái hiện cuộc đua hai client cùng đọc version cũ.

## 8. Thí nghiệm blocking với SELECT FOR UPDATE

Để kiểm tra khóa bi quan, không cần hai worker cùng vượt qua locking read. Mục tiêu là chứng minh transaction B phải chờ khi A đang giữ khóa.

Lịch thử:

```text
Worker A / Connection A             Worker B / Connection B
-----------------------             -----------------------
BEGIN                               (chưa chạy)
SELECT ... FOR UPDATE
đã lấy khóa, báo latch
                                    BEGIN
                                    UPDATE cùng hàng
                                    -> chờ khóa của A
Test quan sát B đang chờ
COMMIT
                                    B tiếp tục và commit
```

Mẫu điều phối:

1. Worker A mở transaction, chạy `SELECT ... FOR UPDATE` và báo `lockAcquired` sau khi câu lệnh trả về.
2. Test runner đợi latch đó với timeout.
3. Test runner khởi động worker B trên connection riêng; B chạy `UPDATE` cùng hàng.
4. Test runner kiểm tra B chưa hoàn tất và database báo B đang chờ tài nguyên của A.
5. Test runner yêu cầu A commit hoặc rollback.
6. Xác nhận B tiếp tục trong thời gian giới hạn.

Không chỉ dùng `Future.isDone() == false` để kết luận B đang chờ khóa. B có thể đang chờ connection pool, thread scheduler hoặc một barrier khác. Hãy đối chiếu session ID, wait event hoặc lock metadata ở database.

Nếu kiểm tra blocking bằng timeout, cần thiết kế sao cho test runner luôn giải phóng A trong `finally`. Nếu assertion thất bại mà A vẫn giữ transaction, các test tiếp theo có thể bị chặn và làm rò rỉ connection.

## 9. Thí nghiệm deadlock với hai connection

Deadlock cần một chu trình chờ. Một lịch điều khiển được có thể dùng hai hàng A và B:

```text
Worker A / Connection A             Worker B / Connection B
-----------------------             -----------------------
BEGIN                               BEGIN
lock row A                          lock row B
signal firstLockA                   signal firstLockB
wait until both hold first lock     wait until both hold first lock
request lock row B                  request lock row A
               \                   /
                \---- cycle ------/
```

Hai transaction giữ khóa đầu tiên rồi cùng yêu cầu khóa thứ hai. Database phát hiện deadlock và rollback một victim. Worker bị chọn làm victim phải nhận lỗi; worker còn lại có thể tiếp tục sau khi khóa được giải phóng.

Khi viết test, barrier nên nằm sau khi mỗi worker lấy được khóa đầu tiên. Sau barrier, cả hai mới yêu cầu khóa thứ hai. Không đặt barrier sau yêu cầu khóa thứ hai vì một worker có thể đã bị chặn và không bao giờ tới barrier.

Deadlock victim không nhất thiết luôn là Worker A hoặc Worker B. Đừng assert cứng danh tính victim trừ khi engine có hợp đồng ổn định cho lựa chọn đó. Hãy assert rằng có một transaction thất bại vì deadlock, transaction còn lại có thể hoàn tất, và dữ liệu cuối vẫn thỏa bất biến.

## 10. Kiểm thử bằng hai cửa sổ SQL thủ công

Để học hoặc điều tra một tình huống cụ thể, hai SQL client riêng biệt thường dễ quan sát hơn code test.

### Bài thử đọc snapshot

**Phiên A:**

```sql
BEGIN;
UPDATE accounts SET balance = 900 WHERE id = 1;
-- Dừng ở đây, chưa commit.
```

**Phiên B:**

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1;
```

Ghi nhận B trả phiên bản cũ, chờ hay nhận lỗi. Sau đó commit hoặc rollback A và quan sát lại B theo isolation level đang dùng.

### Bài thử locking read

Reset dữ liệu rồi thực hiện:

**Phiên A:**

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- Giữ transaction mở.
```

**Phiên B:**

```sql
BEGIN;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
-- Quan sát có phải đang chờ không.
```

Quay lại A và commit. B sẽ tiếp tục nếu engine hỗ trợ cú pháp và khóa như dự kiến.

Các câu lệnh trên là ví dụ PostgreSQL/MySQL-style; SQL Server dùng locking hints như `UPDLOCK` thay cho `FOR UPDATE`. Luôn dùng cú pháp và semantics đúng với hệ quản trị đang kiểm thử.

## 11. Spring test: mỗi worker cần transaction context riêng

Trong Spring imperative, transaction thường được gắn với thread hiện tại thông qua transaction manager và proxy. Nếu hai worker chạy trên hai thread và gọi một service `@Transactional` qua proxy, mỗi worker có thể nhận transaction riêng.

Ví dụ cấu trúc:

```java
@Service
public class AccountWorker {
    private final AccountRepository repository;

    public AccountWorker(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public BigDecimal readBalance(long accountId) {
        return repository.findBalance(accountId);
    }
}
```

Trong integration test, gọi bean `AccountWorker` từ từng task executor. Mỗi lời gọi phải đi qua proxy Spring để transaction advice được áp dụng.

Các điểm cần lưu ý:

- Không gọi method `@Transactional` bằng self-invocation rồi giả định proxy đã tạo transaction.
- Không truyền JDBC `Connection` hoặc `EntityManager` từ thread test sang worker khác.
- Không giả định transaction của test thread tự truyền sang `ExecutorService`.
- Nếu test method có `@Transactional`, dữ liệu fixture chưa commit có thể không nhìn thấy từ worker connection khác.
- Nếu worker commit thật, rollback tự động của test method không hoàn tác các commit độc lập đó; cần cleanup tường minh.
- Nếu worker cần barrier, giữ transaction mở trong lúc chờ chỉ ở test có kiểm soát và với timeout ngắn; không dùng mẫu này trong production flow.

Một cấu trúc an toàn là tạo fixture và commit trước, chạy các worker với transaction riêng, đợi tất cả `Future`, rồi dùng transaction cleanup riêng để xóa dữ liệu test.

### Không dùng một transaction bao quanh toàn bộ test nếu cần nhiều session

Một test `@Transactional` ở thread chính có thể khiến người viết nghĩ toàn bộ thao tác đều thuộc cùng transaction. Nhưng worker thread không tự tham gia transaction đó. Điều này có thể gây hai kiểu lỗi:

1. Worker không nhìn thấy dữ liệu fixture chưa commit của test thread.
2. Worker commit dữ liệu riêng, trong khi test framework chỉ rollback transaction của thread chính, để lại dữ liệu test trong database.

Với test concurrency, thường nên quản lý fixture và cleanup rõ ràng thay vì dựa vào rollback tự động của một transaction test bao trùm.

## 12. Tránh false positive do connection pool

Một test có thể “pass” nhưng không hề tạo concurrency thật nếu pool chỉ cấp một connection hoặc connection được trả lại trước khi transaction kết thúc.

Các tình huống cần tránh:

- Pool maximum size bằng `1` trong khi test cần hai transaction đồng thời.
- Mỗi worker đóng connection ngay sau câu `SELECT`, rồi mở connection mới cho `UPDATE`; transaction boundary bị chia cắt.
- Repository tự lấy connection khác thay vì dùng connection của transaction hiện tại.
- Connection bị giữ ở thread chính trong khi worker chờ pool.
- Test dùng mock DataSource hoặc repository fake nên không có database session thực.
- Hai thread gọi cùng một connection và driver tuần tự hóa các statement.

Để phát hiện, log connection/session ID ngay trong transaction. Có thể thêm assertion rằng hai worker đã đồng thời giữ hai connection khác nhau trước khi qua barrier. Theo dõi pool metrics để xác nhận `active` tăng ít nhất bằng số worker cần concurrency và `pending` không tăng vì pool quá nhỏ.

Nếu test cần một observer connection để đọc lock metadata, tính thêm connection đó vào pool size. Observer không nên dùng chung connection đang bị block để truy vấn trạng thái chờ của chính nó.

## 13. Timeout và cleanup trong test concurrency

Test concurrency có thể treo nếu barrier không đủ participant, worker bị chặn vô hạn hoặc transaction không được kết thúc. Mọi bước chờ nên có timeout.

Các giới hạn hữu ích:

- Timeout khi chờ barrier/latch.
- Timeout khi lấy connection từ pool.
- Lock timeout hoặc statement timeout trong database test.
- Timeout khi gọi `Future.get`.
- Overall timeout cho toàn bộ test.

Khi timeout hoặc assertion thất bại:

1. Hủy task nếu có thể.
2. Rollback transaction còn mở trong từng worker.
3. Đóng statement/result set/connection trong `finally` hoặc try-with-resources.
4. Reset barrier nếu dùng `CyclicBarrier` có thể bị broken.
5. Thu thập session ID, SQL, lock wait và pool metrics trước khi teardown nếu có thể.
6. Cleanup fixture sau khi tất cả worker đã kết thúc hoặc được xác nhận đã dừng.

Không chỉ gọi `shutdownNow()` rồi giả định database transaction đã rollback ngay lập tức. Interrupt không phải mọi JDBC driver đều xử lý giống nhau. Cần query/statement timeout, connection close và transaction cleanup phù hợp với driver.

## 14. Xác minh database thực sự thấy hai transaction

Ngoài log ở ứng dụng, hãy dùng công cụ của database để quan sát session và lock.

| Hệ quản trị | Thông tin hữu ích |
|---|---|
| PostgreSQL | `pg_stat_activity`, `pg_locks`, `pg_blocking_pids(pid)`, `wait_event_type`, backend PID. |
| MySQL InnoDB | `performance_schema.threads`, `data_locks`, `data_lock_waits`, `SHOW ENGINE INNODB STATUS`, `CONNECTION_ID()`. |
| SQL Server | `sys.dm_exec_sessions`, `sys.dm_exec_requests`, `sys.dm_tran_locks`, `blocking_session_id`, `@@SPID`, Extended Events deadlock graph. |

Ví dụ PostgreSQL:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids,
       xact_start,
       query
FROM pg_stat_activity
WHERE datname = current_database();
```

Trong lúc test, cần nhìn thấy hai PID khác nhau. Nếu đang thử blocking, một PID có thể ở trạng thái active nhưng `wait_event_type = 'Lock'`, và `pg_blocking_pids` chỉ ra PID giữ khóa.

Không suy luận mọi wait event là lock. Worker có thể chờ I/O, CPU, connection pool hoặc network. Kết hợp thông tin database với thread dump, pool metrics và trace của ứng dụng để tìm đúng tầng đang chờ.

## 15. Chọn công cụ đồng bộ theo tình huống

| Mục tiêu test | Điểm đồng bộ phù hợp | Lưu ý |
|---|---|---|
| Hai transaction cùng đọc một version trước khi ghi | `CyclicBarrier` sau SELECT | Bảo đảm cả hai đã đọc cùng trạng thái cũ. |
| Kiểm tra một transaction giữ khóa và transaction khác bị chặn | `CountDownLatch` sau khi A lấy khóa | Không đợi B vượt qua câu lệnh đang bị block. |
| Tạo deadlock hai hàng | Barrier sau khi mỗi worker lấy khóa đầu tiên | Sau barrier, mỗi bên yêu cầu khóa còn lại. |
| Chạy N worker claim N job | `CountDownLatch` hoặc `Phaser` trước lúc claim | Pool phải có đủ connection; kiểm tra mỗi job chỉ được claim một lần. |
| Kiểm tra giới hạn pool | Semaphore/latch và pool metrics | Phân biệt pool wait với database lock wait. |
| Kiểm tra timeout | Future timeout và database lock/query timeout | Đảm bảo cleanup transaction khi hết hạn. |

Barrier/latch chỉ điều phối thread trong test process. Nó không chứng minh database đã cấp khóa hoặc đã bắt đầu thực thi statement. Khi cần xác nhận điều kiện ở database, hãy kết hợp wait metadata, session state hoặc một tín hiệu được ghi từ chính transaction.

## 16. Các test nên có trong bộ kiểm thử concurrency

Một bộ kiểm thử thực tế nên kiểm tra nhiều tình huống khác nhau bằng connection thật:

### Lost update

Hai transaction đọc cùng giá trị rồi ghi giá trị tuyệt đối. Xác nhận test tái hiện được kết quả mất cập nhật; sau đó kiểm tra phương án sửa như atomic update hoặc optimistic version.

### Optimistic locking

Hai transaction cùng đọc một version. Sau barrier, cả hai cập nhật với `WHERE version = expected`. Xác nhận chỉ một cập nhật thành công và transaction còn lại nhận conflict.

### Pessimistic blocking

Transaction A lấy `FOR UPDATE` hoặc locking hint tương đương. Transaction B cập nhật cùng hàng. Xác nhận B chờ cho đến khi A commit/rollback hoặc nhận timeout được cấu hình.

### Deadlock

Hai transaction khóa hai hàng theo thứ tự ngược nhau. Xác nhận database chọn một victim, transaction còn lại hoàn tất, ứng dụng xử lý lỗi và dữ liệu cuối vẫn thỏa bất biến.

### Unique constraint race

Hai connection cùng insert một khóa duy nhất. Xác nhận chỉ một insert commit và bên còn lại xử lý duplicate theo nghiệp vụ.

### Write skew hoặc bất biến liên hàng

Hai transaction cùng đọc tập dữ liệu rồi ghi các hàng khác nhau. Xác nhận constraint, khóa điều phối hoặc Serializable ngăn trạng thái vi phạm quy tắc nghiệp vụ.

### Pool saturation

Giữ nhiều connection trong transaction có kiểm soát và xác nhận acquisition timeout/queue behavior. Test phải giải phóng mọi connection ngay cả khi assertion thất bại.

Mỗi test nên xác nhận cả kết quả SQL, trạng thái cuối của dữ liệu và lỗi quan sát được. Chỉ xác nhận một exception được ném ra mà không kiểm tra dữ liệu cuối là chưa đủ.

## 17. Những lỗi thường gặp khi mô phỏng concurrency

- **Nhiều thread dùng chung một connection:** không tạo ra nhiều transaction độc lập và có thể làm transaction bị trộn.
- **Dùng một pool connection cho nhiều worker:** worker khác không thể vào database; barrier có thể treo trước khi concurrency bắt đầu.
- **Chỉ tạo nhiều thread nhưng không có overlap:** các transaction có thể chạy lần lượt nên race condition không xuất hiện.
- **Dùng `sleep` để đoán thứ tự:** kết quả phụ thuộc scheduler và máy chạy test, dễ flaky.
- **Đặt barrier sau một locking read có thể block:** worker thứ hai không bao giờ tới barrier.
- **Không đặt timeout:** một deadlock hoặc barrier thiếu participant có thể làm CI treo vô hạn.
- **Test trên H2 rồi kết luận cho production engine:** semantics khóa và MVCC có thể khác.
- **Để fixture chưa commit trong test transaction:** connection worker không nhìn thấy dữ liệu setup.
- **Tin rằng rollback của test thread xóa commit từ worker:** transaction độc lập đã commit không bị rollback cùng test transaction.
- **Không log session ID:** khó chứng minh có bao nhiêu database session thực sự tham gia.
- **Chỉ kiểm tra thread state:** thread đang WAITING có thể chờ pool hoặc latch, không nhất thiết chờ database lock.
- **Không cleanup sau timeout:** connection/transaction còn mở có thể làm hỏng các test tiếp theo.

## 18. Quy trình thiết kế một bài test đồng thời đáng tin cậy

Trước khi viết test, hãy xác định rõ:

1. Bất thường hoặc hành vi nào cần tái hiện: lost update, blocking, deadlock, version conflict, phantom hay write skew?
2. Cần bao nhiêu transaction độc lập và chúng truy cập cùng hàng, index hay predicate nào?
3. Mỗi worker sẽ mượn connection ở đâu và có giữ connection đến hết transaction không?
4. Pool có đủ connection cho toàn bộ worker và observer không?
5. Isolation level và autocommit có được thiết lập/xác minh tường minh không?
6. Barrier/latch đặt ở thời điểm nào để tạo đúng lịch mong muốn?
7. Có timeout cho mọi wait, query và future không?
8. Làm thế nào xác nhận session ID khác nhau và database thực sự có blocking/lock conflict?
9. Kết quả đúng được xác định bằng row count, exception, trạng thái cuối hay invariant nào?
10. Transaction được rollback/commit và connection được trả về pool trong mọi nhánh không?
11. Fixture có được commit trước khi worker chạy và cleanup sau khi tất cả worker kết thúc không?
12. Test chạy trên đúng database engine/phiên bản mà ứng dụng sử dụng không?

Một bài test concurrency tốt có thể lặp lại lịch quan trọng, chứng minh database đã nhận các transaction độc lập và xác nhận trạng thái cuối. Nó không chỉ cho thấy nhiều thread đã được tạo ra.

## 19. Kết luận

Để kiểm thử database concurrency, cần nhiều session và transaction độc lập. Mỗi worker nên mượn connection riêng từ một `DataSource`/pool, mở transaction riêng, tham gia lịch đồng bộ có kiểm soát và kết thúc transaction trước khi trả connection. Chia sẻ một JDBC connection giữa nhiều thread chỉ tạo ra sự cạnh tranh trong ứng dụng quanh một session; nó không mô phỏng hai client database độc lập.

Dùng barrier/latch để buộc các transaction gặp nhau tại đúng điểm cần kiểm tra, chẳng hạn sau khi cùng đọc một version hoặc sau khi một transaction đã lấy khóa. Dùng timeout để test không treo, xác nhận session ID và wait metadata ở database, bảo đảm pool có đủ connection, commit fixture trước khi chạy và cleanup mọi transaction/connection sau cùng. Chạy trên đúng engine và isolation level của hệ thống thực tế để kết quả có ý nghĩa. Khi đáp ứng các điều kiện đó, test mới có thể cung cấp bằng chứng đáng tin cậy về lost update, optimistic/pessimistic locking, deadlock và các bất thường tương tranh.
