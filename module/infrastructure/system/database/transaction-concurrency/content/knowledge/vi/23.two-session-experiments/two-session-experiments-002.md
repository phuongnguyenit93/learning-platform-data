# Điều khiển thứ tự thao tác của hai phiên bằng mốc đồng bộ

Khi nghiên cứu xử lý đồng thời, chỉ mở hai connection rồi chạy một loạt câu SQL thường chưa đủ để tái hiện một lịch giao dịch cụ thể. Scheduler của hệ điều hành, tốc độ database, connection pool và tải nền có thể làm thứ tự câu lệnh thay đổi giữa các lần chạy. Một test có thể tình cờ tạo được race condition hôm nay nhưng không tái hiện được vào ngày mai.

Để kiểm soát thí nghiệm, cần đặt **mốc đồng bộ (synchronization point)** tại những thời điểm quan trọng. Mỗi phiên dừng ở một mốc cho đến khi phiên kia hoàn thành bước cần thiết. Nhờ vậy, người kiểm thử có thể chủ động tạo lịch như “cả hai cùng đọc trước khi bên nào ghi”, “A giữ khóa rồi B yêu cầu cùng hàng”, hoặc “A và B giữ hai hàng khác nhau rồi yêu cầu khóa chéo”.

Mốc đồng bộ thuộc về test harness hoặc cách điều khiển thí nghiệm. Nó không thay đổi isolation level và cũng không thay thế khóa của DBMS. Mục đích của nó là làm cho thứ tự thao tác có thể lặp lại, quan sát và giải thích.

## 1. Hai phiên, hai transaction và một lịch thực thi

Một phiên (session) thường là một connection độc lập tới database. Mỗi phiên có thể mở transaction riêng, thực hiện câu lệnh và commit hoặc rollback độc lập.

Ví dụ:

- Session A dùng connection A và transaction A.
- Session B dùng connection B và transaction B.
- Cả hai cùng truy cập một bảng hoặc cùng một nhóm dữ liệu.

Một lịch thực thi (schedule) mô tả thứ tự các thao tác của hai transaction. Ví dụ:

~~~text
A: BEGIN
A: SELECT balance
B: BEGIN
B: SELECT balance
A: UPDATE balance
A: COMMIT
B: UPDATE balance
B: COMMIT
~~~

Lịch này khác với lịch:

~~~text
A: BEGIN
A: SELECT balance
A: UPDATE balance
A: COMMIT
B: BEGIN
B: SELECT balance
B: UPDATE balance
B: COMMIT
~~~

Trong lịch đầu, hai transaction cùng đọc trạng thái trước khi một bên ghi. Trong lịch sau, B đọc sau khi A đã commit. Kết quả có thể khác nhau, đặc biệt nếu ứng dụng đọc giá trị rồi tính toán ở phía client.

Để kiểm tra một vấn đề concurrency, trước tiên hãy viết lịch thao tác mong muốn. Sau đó đặt mốc đồng bộ để bảo đảm các bước diễn ra theo lịch đó.

## 2. Mốc đồng bộ là gì?

Mốc đồng bộ là một điểm trong test mà một luồng phải chờ tín hiệu trước khi đi tiếp. Tín hiệu có thể đến từ luồng khác, test controller hoặc một thao tác điều phối bên ngoài.

Một test hai phiên có thể cần các mốc:

| Mốc | Ý nghĩa |
|---|---|
| **A_READ_DONE** | Session A đã đọc xong dữ liệu cần kiểm tra |
| **B_READ_DONE** | Session B đã đọc xong dữ liệu cần kiểm tra |
| **BOTH_READ** | Cả hai đã đọc xong; cho phép bước ghi bắt đầu |
| **A_COMMITTED** | Transaction A đã commit thành công |
| **A_HOLDS_LOCK** | A đã thực hiện thao tác lấy khóa và đang giữ khóa |
| **B_WAITING** | B đã gửi thao tác và đang chờ khóa |
| **RELEASE_B** | Test controller cho phép B tiếp tục sau một bước cụ thể |

Các tên trên là nhãn logic trong test, không phải lệnh SQL chuẩn. Mỗi mốc cần gắn với một sự kiện có thể xác nhận, chẳng hạn một CountDownLatch được mở, một Future hoàn tất hoặc trạng thái chờ khóa quan sát được từ DBMS.

### Mốc đồng bộ khác sleep

Dùng sleep(500) chỉ làm luồng tạm dừng trong khoảng thời gian ước lượng. Nó không chứng minh rằng phiên kia đã đọc xong, đã lấy khóa hay đã commit.

Ví dụ:

~~~java
Thread.sleep(500);
executeUpdate();
~~~

Máy nhanh có thể hoàn thành bước trước 500 ms; máy chậm có thể chưa bắt đầu. Test phụ thuộc vào tốc độ và tải môi trường nên dễ chập chờn.

Mốc đồng bộ chờ một điều kiện cụ thể:

~~~java
bothSessionsRead.await(timeout, unit);
executeUpdate();
~~~

Khi await hoàn tất, test biết cả hai luồng đã đi tới điểm đã quy định. Vẫn cần timeout để test không treo vô hạn nếu một phiên lỗi hoặc không bao giờ gửi tín hiệu.

## 3. Ba cách điều khiển thứ tự thường dùng

### Điều khiển thủ công bằng hai cửa sổ SQL

Mở hai session độc lập trong hai tab/cửa sổ SQL client. Người kiểm thử chạy từng nhóm câu lệnh theo các mốc đã đánh số và chỉ chuyển sang bước tiếp theo khi phiên còn lại đã đạt mốc tương ứng.

Cách này phù hợp để học và quan sát trực tiếp:

1. Chạy phần chuẩn bị dữ liệu.
2. Chạy Session A đến A_READ_DONE, rồi tạm dừng.
3. Chạy Session B đến B_READ_DONE, rồi tạm dừng.
4. Tiếp tục Session A hoặc B theo lịch.
5. Ghi nhận câu lệnh nào chờ, câu lệnh nào commit hoặc lỗi.
6. Đọc trạng thái cuối bằng session thứ ba hoặc sau khi cả hai transaction kết thúc.

Ưu điểm là dễ nhìn thấy transaction và kết quả. Nhược điểm là thao tác bằng tay khó chạy hàng trăm lần và khó tích hợp vào CI.

### Đồng bộ trong test harness

Khi viết test tự động, dùng các primitive như:

- **CountDownLatch**: một hoặc nhiều luồng báo đã tới mốc; luồng khác chờ đủ tín hiệu.
- **CyclicBarrier**: nhiều luồng cùng chờ rồi được giải phóng tại một điểm.
- **Phaser**: điều phối nhiều pha khi test có nhiều bước đồng bộ.
- **Semaphore**: giới hạn số luồng được phép đi qua một vùng.
- **CompletableFuture**: báo một kết quả hoặc lỗi bất đồng bộ cho luồng phụ thuộc.

Với lịch hai phiên có nhiều pha, CountDownLatch kết hợp CompletableFuture thường đủ rõ ràng. Barrier chỉ bảo đảm các luồng đã đến cùng một điểm; nó không quyết định luồng nào chạy trước sau khi barrier mở. Nếu cần thứ tự cụ thể, hãy thêm một gate riêng cho pha kế tiếp.

### Đồng bộ qua database hoặc công cụ điều phối

Nếu hai session chạy ở hai process hoặc hai máy khác nhau, test harness có thể dùng một control table, advisory lock, message channel hoặc một service điều phối để gửi tín hiệu.

Cách này hữu ích khi không thể chia sẻ bộ nhớ giữa hai test worker. Tuy nhiên, cơ chế điều phối không nên vô tình trở thành tài nguyên đang được kiểm thử. Nếu dùng cùng database, cần tách bảng điều khiển khỏi dữ liệu nghiệp vụ và tránh để khóa điều phối làm thay đổi lịch khóa mục tiêu.

Không dùng một hàng control chung trong chính transaction đang kiểm tra nếu thao tác đó làm phát sinh thêm lock contention ngoài dự kiến.

## 4. Thực nghiệm thủ công: hai session cùng đọc một giá trị cũ

Giả sử bảng tài khoản có một hàng với số dư ban đầu là 100:

~~~sql
CREATE TABLE IF NOT EXISTS concurrency_demo_accounts (
    account_id BIGINT PRIMARY KEY,
    balance INT NOT NULL
);

INSERT INTO concurrency_demo_accounts (account_id, balance)
VALUES (1, 100)
ON CONFLICT (account_id) DO UPDATE
SET balance = EXCLUDED.balance;
~~~

Ví dụ này dùng cú pháp PostgreSQL để chuẩn bị dữ liệu. Mục tiêu là tạo lịch trong đó A và B đều đọc balance = 100 trước khi bên nào cập nhật.

### Session A — mốc A_READ_DONE

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM concurrency_demo_accounts
WHERE account_id = 1;

-- Mốc A_READ_DONE: ghi nhận giá trị 100.
-- Tạm dừng, chưa UPDATE và chưa COMMIT.
~~~

### Session B — mốc B_READ_DONE

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM concurrency_demo_accounts
WHERE account_id = 1;

-- Mốc B_READ_DONE: cũng ghi nhận giá trị 100.
-- Tạm dừng, chưa UPDATE và chưa COMMIT.
~~~

Khi cả hai session đều đã đọc xong, tiếp tục Session A:

~~~sql
UPDATE concurrency_demo_accounts
SET balance = 110
WHERE account_id = 1;

COMMIT;
~~~

Sau khi A commit, tiếp tục Session B:

~~~sql
UPDATE concurrency_demo_accounts
SET balance = 120
WHERE account_id = 1;

COMMIT;
~~~

Đọc kết quả:

~~~sql
SELECT balance
FROM concurrency_demo_accounts
WHERE account_id = 1;
~~~

Kết quả là 120. B đã ghi một giá trị tuyệt đối được tính từ lần đọc cũ. Thay đổi của A bị ghi đè. Đây là lost update ở tầng logic ứng dụng.

Điểm cần quan sát: DBMS không thể tự biết rằng giá trị 120 của B có nghĩa là “cộng thêm 20 vào số dư hiện tại”. SQL đã yêu cầu gán đúng 120.

### Lặp lại với phép cập nhật nguyên tử

Đặt lại balance về 100, rồi cho cả hai session cùng đọc trước khi ghi như trên. Thay câu UPDATE của A và B bằng:

~~~sql
-- Session A
UPDATE concurrency_demo_accounts
SET balance = balance + 10
WHERE account_id = 1;
COMMIT;
~~~

~~~sql
-- Session B, chỉ chạy sau khi A commit
UPDATE concurrency_demo_accounts
SET balance = balance + 20
WHERE account_id = 1;
COMMIT;
~~~

Kết quả là 130. Mỗi câu lệnh biểu diễn ý định cộng vào giá trị hiện tại trong DBMS, thay vì gửi lại một kết quả tuyệt đối đã tính từ snapshot cũ.

Mốc BOTH_READ rất quan trọng: nếu B chỉ đọc sau khi A commit, test không còn chứng minh được cả hai đã dùng cùng trạng thái đầu vào.

## 5. Thực nghiệm điều khiển lock wait

Một lịch khác kiểm tra cách DBMS điều phối hai writer cùng cập nhật một hàng.

Đặt lại số dư:

~~~sql
UPDATE concurrency_demo_accounts
SET balance = 100
WHERE account_id = 1;
~~~

### Session A — mốc A_HOLDS_LOCK

~~~sql
BEGIN;

UPDATE concurrency_demo_accounts
SET balance = balance + 10
WHERE account_id = 1;

-- A đã cập nhật hàng và giữ khóa ghi.
-- Chưa COMMIT.
~~~

### Session B — mốc B_WAITING

Chạy ở session B:

~~~sql
BEGIN;

UPDATE concurrency_demo_accounts
SET balance = balance + 20
WHERE account_id = 1;

-- Câu lệnh phải chờ A nhả khóa trong tình huống này.
~~~

Khi B đang chờ, quay lại A:

~~~sql
COMMIT;
~~~

B tiếp tục sau khi A commit. Sau đó commit B:

~~~sql
COMMIT;
~~~

Kết quả cuối là 130.

Để xác nhận B thực sự đang chờ, không nên đoán bằng cách đợi một khoảng thời gian cố định. Với PostgreSQL, có thể quan sát session đang chờ khóa bằng một truy vấn chẩn đoán:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock';
~~~

Quyền quan sát phụ thuộc role và cấu hình. Có thể cần lọc theo application_name hoặc PID của session test. Với MySQL, SQL Server và Oracle, dùng view/công cụ theo dõi lock tương ứng.

Mốc B_WAITING chỉ được xem là đạt khi DBMS xác nhận câu lệnh đang chờ đúng tài nguyên. Việc thread B đã bắt đầu gọi JDBC không chứng minh request đã đến DBMS hoặc đang đợi khóa.

## 6. Thực nghiệm snapshot conflict bằng hai phiên

Ở một số isolation level, transaction đọc snapshot ổn định có thể bị hủy nếu nó cố ghi một hàng đã được transaction khác thay đổi sau snapshot.

Ví dụ sau mô tả PostgreSQL REPEATABLE READ.

Đặt lại balance về 100.

### Session A — tạo snapshot

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM concurrency_demo_accounts
WHERE account_id = 1;

-- Snapshot của A đã được thiết lập.
-- Giữ transaction mở.
~~~

### Session B — cập nhật và commit

~~~sql
BEGIN;

UPDATE concurrency_demo_accounts
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;
~~~

### Session A — thử ghi trên hàng đã thay đổi

~~~sql
UPDATE concurrency_demo_accounts
SET balance = balance + 20
WHERE account_id = 1;
~~~

Trong PostgreSQL, A nhận serialization failure (thường SQLSTATE 40001) vì hàng đã bị transaction B thay đổi sau snapshot của A. A phải rollback:

~~~sql
ROLLBACK;
~~~

Mốc đồng bộ cần đặt sau câu SELECT đầu tiên của A, vì đó là thao tác thiết lập snapshot cho tình huống này. Chỉ gửi BEGIN rồi cho B cập nhật chưa chắc đã tạo đúng lịch nếu snapshot của A chưa được lấy.

Cú pháp và thời điểm lấy snapshot khác nhau giữa các DBMS. Khi tái hiện trên hệ quản trị khác, hãy xác định câu lệnh nào thực sự tạo read view hoặc snapshot theo isolation level đang dùng.

## 7. Thực nghiệm deadlock theo lịch có chủ đích

Để tạo deadlock, hai session cần giữ hai tài nguyên khác nhau rồi yêu cầu khóa chéo.

Chuẩn bị hai hàng:

~~~sql
CREATE TABLE IF NOT EXISTS concurrency_demo_rows (
    id INT PRIMARY KEY,
    value INT NOT NULL
);

INSERT INTO concurrency_demo_rows (id, value)
VALUES (1, 100), (2, 200)
ON CONFLICT (id) DO UPDATE
SET value = EXCLUDED.value;
~~~

### Session A — giữ hàng 1

~~~sql
BEGIN;

UPDATE concurrency_demo_rows
SET value = value + 1
WHERE id = 1;

-- Mốc A_HOLDS_ROW_1.
-- Chưa COMMIT.
~~~

### Session B — giữ hàng 2

~~~sql
BEGIN;

UPDATE concurrency_demo_rows
SET value = value + 1
WHERE id = 2;

-- Mốc B_HOLDS_ROW_2.
-- Chưa COMMIT.
~~~

Sau khi cả hai đã giữ khóa:

Session A yêu cầu hàng 2:

~~~sql
UPDATE concurrency_demo_rows
SET value = value + 1
WHERE id = 2;

-- A chờ B.
~~~

Xác nhận A đang chờ bằng công cụ quan sát lock. Sau đó Session B yêu cầu hàng 1:

~~~sql
UPDATE concurrency_demo_rows
SET value = value + 1
WHERE id = 1;

-- B tạo vòng chờ A -> B -> A.
~~~

DBMS phát hiện deadlock và chọn một transaction làm victim. Transaction bị hủy nhận lỗi; transaction còn lại có thể tiếp tục khi khóa được giải phóng.

Không nên dùng sleep để giả định A đã bắt đầu chờ trước khi B yêu cầu khóa chéo. Dùng trạng thái lock của DBMS làm mốc xác nhận. Sau thí nghiệm, rollback session còn lại nếu nó vẫn mở transaction và khôi phục dữ liệu ban đầu.

## 8. Dùng CountDownLatch để điều khiển hai phiên trong Java

Trong test tự động, mỗi task cần lấy một JDBC connection riêng. Không chia sẻ cùng một Connection giữa hai thread vì JDBC connection không phải công cụ đồng bộ thread và hai luồng sẽ không còn là hai session độc lập.

Ví dụ sau là khung minh họa cho lịch lost update. Hai task cùng đọc trước, A commit trước, rồi B ghi giá trị tuyệt đối đã tính từ lần đọc cũ.

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CompletableFuture<Void> aCommitted = new CompletableFuture<>();

ExecutorService pool = Executors.newFixedThreadPool(2);

Future<?> taskA = pool.submit(() -> {
    try (Connection a = dataSource.getConnection()) {
        a.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        a.setAutoCommit(false);

        int oldValue = readBalance(a, 1);

        bothRead.countDown();
        awaitWithTimeout(bothRead);

        updateBalance(a, 1, oldValue + 10);
        a.commit();

        aCommitted.complete(null);
    } catch (Throwable error) {
        aCommitted.completeExceptionally(error);
        throw new RuntimeException(error);
    }
});

Future<?> taskB = pool.submit(() -> {
    try (Connection b = dataSource.getConnection()) {
        b.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        b.setAutoCommit(false);

        int oldValue = readBalance(b, 1);

        bothRead.countDown();
        awaitWithTimeout(bothRead);

        aCommitted.join();

        updateBalance(b, 1, oldValue + 20);
        b.commit();
    } catch (Throwable error) {
        throw new RuntimeException(error);
    }
});
~~~

Đây là khung minh họa; các hàm readBalance, updateBalance và awaitWithTimeout cần được cài đặt cho test. Trong code thật, hãy đặt biến connection ngoài phạm vi xử lý lỗi để phần catch/finally có thể rollback trước khi đóng connection. Mỗi task phải rollback transaction chưa commit khi gặp lỗi.

Các điểm đồng bộ:

- bothRead bảo đảm A và B đều đã đọc xong trước khi A cập nhật.
- aCommitted bảo đảm B chỉ ghi sau khi A commit thành công.
- Nếu A lỗi, future hoàn tất exceptional để B không tiếp tục với giả định sai.
- Mọi await và Future.get cần timeout hữu hạn.
- Sau test, đợi cả hai task hoàn tất, đọc kết quả bằng connection mới và đóng executor.

Với lịch này, cả hai có thể đọc cùng giá trị ban đầu nhưng thao tác ghi được sắp xếp có chủ đích. Test có thể xác nhận lost update và sau đó chạy lại với phép cộng nguyên tử để so sánh.

### Khi nào dùng CyclicBarrier?

CyclicBarrier phù hợp khi nhiều thread phải cùng tới một pha rồi mới tiếp tục. Ví dụ, hai session đều hoàn thành SELECT và cùng chờ barrier trước bước UPDATE.

Nhưng sau khi barrier mở, scheduler quyết định thread nào chạy trước. Nếu test cần A commit trước B, phải thêm một gate khác như CountDownLatch hoặc CompletableFuture. Barrier đồng bộ điểm bắt đầu của pha; nó không áp đặt thứ tự hoàn thành của pha.

### Khi nào dùng Phaser?

Phaser hữu ích khi test có nhiều pha và số participant có thể thay đổi:

1. Cả hai session đã bắt đầu transaction.
2. Cả hai đã đọc dữ liệu.
3. A đã cập nhật.
4. B đã gửi thao tác cạnh tranh.
5. A đã commit.
6. B đã hoàn tất.

Mỗi phase là một mốc. Tuy nhiên, hãy giữ số pha tối thiểu cần thiết; một test có quá nhiều gate sẽ khó đọc và dễ deadlock chính test harness.

## 9. Không để test harness tạo ra một deadlock giả

Test đồng thời có thể tự treo nếu một thread chờ latch mà thread còn lại đã lỗi trước khi gửi tín hiệu.

Ví dụ:

~~~text
Thread A:
  đọc dữ liệu
  lỗi trước countDown()

Thread B:
  await() mãi mãi
~~~

Để tránh tình huống này:

- Dùng timeout cho mọi await, Future.get, barrier và thao tác chờ.
- Nếu một task lỗi, hoàn tất future/gate tương ứng ở trạng thái lỗi.
- Khi timeout, hủy task còn lại và đóng connection.
- Trong finally, rollback transaction chưa hoàn tất.
- Dùng ExecutorService.shutdownNow() sau khi đã thu thập kết quả.
- Giữ exception gốc và thêm lỗi rollback/cleanup làm suppressed exception nếu cần.
- Không bỏ qua InterruptedException; khôi phục interrupt flag hoặc truyền lỗi theo quy ước test.

Timeout trong test harness là giới hạn an toàn để phát hiện test bị kẹt. Nó không phải công cụ tạo thứ tự. Không dùng một timeout ngắn để hy vọng một query đã chờ khóa; hãy xác nhận trạng thái bằng DBMS.

## 10. Connection độc lập là điều kiện bắt buộc

Một thí nghiệm hai phiên cần hai database session thực sự độc lập. Nếu hai thread cùng dùng một connection:

- Transaction có thể bị chia sẻ ngoài ý muốn.
- Một thread có thể commit transaction của thread kia.
- JDBC driver có thể không hỗ trợ thao tác đồng thời trên cùng connection.
- Test không còn đại diện cho hai transaction độc lập.

Với connection pool, hãy kiểm tra pool có thể cấp ít nhất hai connection cùng lúc. Nếu pool chỉ có một connection, task thứ hai có thể chờ lấy connection và test không bao giờ tạo được concurrency mong muốn.

Nên ghi lại session identifier để xác nhận:

- PostgreSQL: pg_backend_pid().
- MySQL: CONNECTION_ID().
- SQL Server: @@SPID.
- Oracle: SYS_CONTEXT('USERENV', 'SID').

Câu truy vấn lấy session id có thể chạy trong từng connection trước khi bắt đầu thí nghiệm. Ghi id vào log cùng tên task A/B để dễ đối chiếu.

## 11. Snapshot được thiết lập ở thời điểm nào?

Một lỗi trong test hai phiên là đặt barrier sai vị trí. Transaction đã BEGIN chưa chắc đã lấy snapshot mà test muốn kiểm tra.

Thời điểm snapshot phụ thuộc DBMS và isolation level:

- PostgreSQL READ COMMITTED lấy snapshot mới cho từng statement. REPEATABLE READ và SERIALIZABLE sử dụng snapshot ổn định theo transaction, được thiết lập khi transaction thực hiện statement đầu tiên cần snapshot.
- MySQL InnoDB REPEATABLE READ tạo read view cho consistent read theo quy tắc của engine; locking read và DML có semantics current read riêng.
- SQL Server SNAPSHOT dùng snapshot transaction; RCSI dùng row version theo statement ở READ COMMITTED.
- Oracle READ COMMITTED cung cấp statement-level consistency; SERIALIZABLE dùng transaction-level snapshot.

Do đó, nếu test write skew hoặc snapshot conflict, hãy đặt mốc sau câu SELECT thực sự thiết lập snapshot. Nếu chỉ đồng bộ sau BEGIN, hai transaction có thể chưa nhìn thấy cùng trạng thái.

Không suy luận hành vi snapshot chỉ từ tên isolation level. Chạy trên đúng DBMS, phiên bản và cấu hình đang dùng.

## 12. Các kịch bản nên điều khiển bằng mốc đồng bộ

| Kịch bản | Mốc quan trọng | Kết quả cần quan sát |
|---|---|---|
| Lost update | Cả hai đọc xong trước khi A ghi | Giá trị tuyệt đối của B có thể ghi đè A |
| Atomic increment | Cả hai đã sẵn sàng, sau đó thực hiện hai UPDATE biểu thức | Cả hai lượng tăng đều được áp dụng |
| Lock wait | A giữ khóa; B đã vào trạng thái chờ | B tiếp tục sau khi A commit/rollback |
| Snapshot conflict | B đã commit sau snapshot của A; A mới thử ghi | DBMS có thể hủy A tùy isolation |
| Write skew | Cả hai đọc cùng predicate trước khi ghi hai hàng khác nhau | Mức cô lập có thể cho phép hoặc ngăn bất biến bị phá |
| Deadlock | A giữ hàng 1, B giữ hàng 2, sau đó yêu cầu chéo | DBMS phát hiện chu trình và chọn victim |
| Phantom | A đã đọc predicate; B chèn hàng thỏa predicate | Khác biệt theo range/predicate locking và isolation |
| Commit/rollback race | Một phiên giữ transaction trong khi phiên kia đọc/ghi | Xác nhận trạng thái quan sát và thời điểm thay đổi |

Một kịch bản nên chỉ thay đổi một yếu tố mỗi lần: isolation level, loại câu UPDATE, thứ tự thao tác hoặc index. Nếu đổi nhiều yếu tố cùng lúc, khó biết yếu tố nào làm kết quả thay đổi.

## 13. Ghi lại lịch thực thi như một trace

Sau mỗi lần chạy, ghi lại một bảng trace:

| Thứ tự | Session | Transaction | Mốc | Thao tác | Kết quả |
|---:|---|---|---|---|---|
| 1 | A | TA | A_BEGIN | BEGIN | Thành công |
| 2 | A | TA | A_READ_DONE | SELECT balance | 100 |
| 3 | B | TB | B_BEGIN | BEGIN | Thành công |
| 4 | B | TB | B_READ_DONE | SELECT balance | 100 |
| 5 | A | TA | A_WRITE | UPDATE balance = 110 | Thành công |
| 6 | A | TA | A_COMMITTED | COMMIT | Thành công |
| 7 | B | TB | B_WRITE | UPDATE balance = 120 | Thành công |
| 8 | B | TB | B_COMMITTED | COMMIT | Thành công |

Trace giúp giải thích kết quả và tái hiện chính xác lịch. Nên ghi:

- Timestamp log để hỗ trợ chẩn đoán, nhưng không dùng nó làm cơ chế đồng bộ.
- Session id và transaction/test id.
- Tên mốc đồng bộ.
- SQL operation hoặc tên bước.
- Isolation level.
- Giá trị đọc được và số hàng bị ảnh hưởng.
- Thời gian chờ lock nếu có.
- Commit, rollback hoặc mã lỗi.
- Trạng thái dữ liệu cuối.

Thứ tự sự kiện trong trace nên được ghi bởi test controller hoặc sequence cục bộ của test. Wall clock có thể lệch giữa máy và không đủ để chứng minh thứ tự nhân quả.

## 14. Reset dữ liệu và cô lập các lần chạy

Test concurrency phải có dữ liệu ban đầu xác định. Nếu lần chạy trước để lại balance 130, lần sau không thể giả định nó bắt đầu từ 100.

Một quy trình test:

1. Tạo dữ liệu với test id riêng hoặc reset các hàng mục tiêu.
2. Xác nhận trạng thái ban đầu bằng connection mới.
3. Mở hai connection độc lập.
4. Chạy lịch đã định.
5. Thu kết quả commit/abort và lỗi.
6. Chờ mọi transaction kết thúc.
7. Đọc trạng thái cuối bằng connection mới.
8. Kiểm tra invariant và kết quả mong đợi.
9. Dọn dữ liệu test sau khi không còn transaction nào giữ khóa.

Không chạy cleanup trong lúc một session vẫn còn transaction mở. Câu DELETE hoặc TRUNCATE có thể bị chặn, hoặc cleanup làm thay đổi lịch đang kiểm thử.

Trong CI, dùng schema/database riêng hoặc dữ liệu có test id duy nhất để các test chạy song song không tranh chấp dữ liệu của nhau.

## 15. Isolation level phải được đặt rõ ràng cho từng phiên

Không dựa vào cấu hình mặc định của connection pool. Hai connection có thể nhận isolation level từ cấu hình session hoặc framework khác nhau.

Trước thí nghiệm, ghi lại isolation level của từng session. Nếu dùng JDBC:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
connection.setAutoCommit(false);
~~~

Nếu thay đổi isolation level bằng SQL, thực hiện trước các statement cần snapshot và theo cú pháp DBMS. Một số DBMS không cho đổi isolation sau khi transaction đã bắt đầu hoặc đã thực hiện query.

Khi test nhiều mức cô lập, chạy cùng một lịch trên từng mức và reset dữ liệu giữa các lần chạy. Ghi rõ DBMS/version/configuration cùng kết quả vì cùng tên isolation level không có nghĩa hành vi giống nhau giữa các engine.

## 16. Các lỗi thường gặp khi điều khiển thứ tự

### Dùng sleep thay cho mốc

Một khoảng sleep không chứng minh phiên kia đã đến bước mong muốn. Dùng latch/barrier hoặc xác nhận trạng thái lock/snapshot qua DBMS.

### Dùng chung một connection

Hai thread không còn là hai session độc lập. Mỗi transaction cần connection riêng.

### Đặt barrier sau BEGIN nhưng trước lần đọc đầu tiên

Snapshot có thể chưa được thiết lập. Đặt mốc sau statement đọc cần thiết.

### Cho rằng barrier quyết định thread chạy trước

Barrier chỉ giải phóng các participant cùng lúc. Dùng gate bổ sung nếu cần thứ tự A commit trước B.

### Không đặt timeout

Nếu một task lỗi trước khi gửi tín hiệu, task còn lại có thể chờ vô hạn. Mọi điểm chờ phải có timeout và đường cleanup.

### Không rollback sau lỗi

Một transaction có thể còn mở hoặc bị đánh dấu lỗi. Phải rollback và đóng connection trước khi reset dữ liệu.

### Không xác nhận B thật sự đang chờ khóa

Thread đã gọi executeUpdate chưa chắc DBMS đã nhận và đặt nó vào lock wait. Quan sát trạng thái session/lock để xác nhận.

### Dùng test database khác production

Khác DBMS hoặc phiên bản có thể khác snapshot timing, locking semantics, deadlock detection và error code. Test concurrency quan trọng phải chạy trên đúng engine/configuration.

### Chỉ kiểm tra exception mà không kiểm tra dữ liệu cuối

Một transaction bị hủy chưa đủ chứng minh invariant được bảo vệ. Phải đọc trạng thái cuối và xác nhận kết quả nghiệp vụ.

## 17. Quy trình thiết kế thí nghiệm hai phiên

1. **Xác định câu hỏi**: cần chứng minh lost update, lock wait, snapshot conflict, write skew, phantom hay deadlock?
2. **Chuẩn bị dữ liệu ban đầu**: đặt giá trị và hàng liên quan ở trạng thái xác định.
3. **Viết lịch mong muốn**: ghi thứ tự BEGIN, SELECT, UPDATE, COMMIT/ROLLBACK của A và B.
4. **Đánh dấu các mốc**: xác định sau thao tác nào một phiên phải chờ phiên kia.
5. **Chọn cơ chế đồng bộ**: điều khiển thủ công, latch/barrier/phaser hoặc tín hiệu qua control plane.
6. **Mở connection độc lập**: xác nhận session id và isolation level.
7. **Chạy từng pha**: chỉ mở gate khi điều kiện mốc đã được xác nhận.
8. **Quan sát DBMS**: lock wait, blocking session, snapshot error và deadlock graph nếu có.
9. **Thu kết quả**: commit/abort, số hàng ảnh hưởng, mã lỗi và trace.
10. **Kiểm tra trạng thái cuối**: đọc bằng connection mới và xác nhận invariant.
11. **Cleanup**: rollback transaction còn mở, đóng connection và reset fixture.
12. **Lặp lại có kiểm soát**: thay một yếu tố mỗi lần để so sánh isolation level hoặc cách cập nhật.

## 18. Checklist cho một test concurrency có thể tái hiện

- [ ] Có hai connection/database session độc lập.
- [ ] Dữ liệu ban đầu được tạo hoặc reset xác định.
- [ ] Isolation level của từng session được đặt và ghi nhận rõ.
- [ ] Snapshot được thiết lập trước mốc đọc nếu kịch bản yêu cầu.
- [ ] Mỗi mốc đồng bộ tương ứng với một sự kiện có thể xác nhận.
- [ ] Không dùng sleep cố định làm bằng chứng về thứ tự.
- [ ] Có timeout cho mọi latch, barrier và thao tác chờ.
- [ ] Có đường truyền lỗi giữa các task để tránh chờ vô hạn.
- [ ] Xác nhận lock wait bằng công cụ DBMS khi cần.
- [ ] Ghi lại trace theo session và transaction.
- [ ] Kiểm tra commit/rollback và trạng thái dữ liệu cuối.
- [ ] Rollback, đóng connection và dọn fixture sau test.
- [ ] Chạy trên đúng DBMS/version/configuration cần chứng minh.

Điều khiển thứ tự bằng mốc đồng bộ biến một race condition khó đoán thành một lịch giao dịch có thể tái hiện. Khi cả hai phiên được dừng đúng thời điểm, người kiểm thử có thể chứng minh chúng đã cùng đọc một trạng thái, một writer đang giữ khóa, hoặc một transaction đã thiết lập snapshot trước khi transaction khác commit. Dùng latch/barrier cho test harness, công cụ lock của DBMS để xác nhận trạng thái thật, và trace để ghi lại thứ tự nhân quả. Kết quả chỉ đáng tin khi được kiểm tra bằng hai session độc lập, transaction được cleanup đúng cách và trạng thái cuối vẫn được đối chiếu với bất biến nghiệp vụ.
