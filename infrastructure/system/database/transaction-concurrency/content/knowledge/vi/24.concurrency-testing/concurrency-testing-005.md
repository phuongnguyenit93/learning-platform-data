# Kiểm thử thực thi lại sau bế tắc hoặc lỗi tuần tự hóa

Trong hệ thống có nhiều transaction chạy đồng thời, một transaction đôi khi bị DBMS từ chối dù dữ liệu đầu vào hợp lệ. Hai nguyên nhân thường gặp là **bế tắc (deadlock)** và **lỗi tuần tự hóa (serialization failure)**. Đây có thể là lỗi cạnh tranh tạm thời: nếu chạy lại toàn bộ đơn vị nghiệp vụ trong một transaction mới, giao dịch có thể thành công với trạng thái dữ liệu mới nhất.

Tuy nhiên, retry chỉ an toàn khi ứng dụng nhận diện đúng loại lỗi, kết thúc transaction cũ, bắt đầu transaction mới và tính toán lại từ dữ liệu mới. Chỉ chạy lại câu SQL cuối cùng hoặc tiếp tục dùng persistence context/snapshot cũ có thể lặp lại lỗi hoặc ghi sai dữ liệu. Nếu transaction đã tạo tác động bên ngoài như thanh toán, gửi email hay phát message, retry còn có thể nhân đôi tác động đó.

Bài này trình bày cách thiết kế và kiểm thử retry sau deadlock/serialization failure: xác định lỗi nào có thể retry, đặt ranh giới transaction đúng, dùng backoff có giới hạn, bảo vệ tính lũy đẳng và tạo lịch hai phiên có thể tái lập để chứng minh kết quả.

## 1. Deadlock và serialization failure khác nhau thế nào?

Hai lỗi đều có thể khiến transaction không commit, nhưng DBMS từ chối vì những lý do khác nhau.

**Deadlock** xảy ra khi các transaction tạo thành một chu trình chờ tài nguyên. Ví dụ, A giữ khóa hàng 1 và chờ hàng 2, trong khi B giữ khóa hàng 2 và chờ hàng 1. DBMS phát hiện chu trình và chọn một transaction làm victim để phá deadlock. Transaction victim phải được kết thúc theo quy tắc của DBMS trước khi thử lại.

**Serialization failure** xảy ra khi DBMS không thể chấp nhận lịch thực thi vì kết quả không tương đương với một thứ tự tuần tự hợp lệ theo isolation SERIALIZABLE. DBMS có thể chặn một transaction hoặc phát hiện phụ thuộc nguy hiểm rồi hủy transaction. Lỗi này không nhất thiết có một vòng chờ khóa như deadlock.

| Tiêu chí | Deadlock | Serialization failure |
|---|---|---|
| Nguyên nhân | Chu trình chờ tài nguyên | Lịch đọc/ghi không thể tuần tự hóa theo mức cô lập yêu cầu |
| Có thể xảy ra khi | Các transaction lấy khóa theo thứ tự gây vòng chờ | Các transaction có phụ thuộc đọc/ghi nguy hiểm, kể cả khi không chờ khóa lâu |
| Cách DBMS xử lý | Chọn victim để phá chu trình | Chặn hoặc hủy transaction để bảo toàn serializable semantics |
| Bằng chứng thường thấy | Deadlock graph, owner/waiter, resource và victim | Serialization error, SQLSTATE hoặc thông tin xung đột theo DBMS |
| Có thể retry? | Thường có nếu đơn vị nghiệp vụ an toàn để chạy lại | Thường có; phải chạy lại từ đầu trong transaction/snapshot mới |

Không nên gom lock timeout vào deadlock. Một transaction có thể chờ khóa quá thời hạn vì blocker chạy lâu mà không hề có chu trình. Lock timeout có thể được retry trong một số workload, nhưng cần chính sách riêng và điều tra blocker; retry liên tục có thể chỉ làm tăng tải.

## 2. Vì sao phải chạy lại toàn bộ transaction?

Giả sử giao dịch chuyển 200 từ tài khoản A sang B. Nó đọc số dư, kiểm tra điều kiện, tính phí, cập nhật hai tài khoản và ghi ledger. Nếu câu UPDATE cuối gặp deadlock, transaction có thể đã bị rollback hoặc không còn hợp lệ.

Chỉ chạy lại UPDATE cuối với số tiền đã tính từ snapshot cũ là không an toàn. Trong thời gian đó, một giao dịch khác có thể đã thay đổi số dư hoặc hạn mức. Retry đúng phải:

1. Kết thúc transaction thất bại bằng rollback hoặc theo cơ chế rollback của DBMS.
2. Bắt đầu transaction mới.
3. Đọc lại tất cả dữ liệu mà quyết định nghiệp vụ phụ thuộc.
4. Kiểm tra lại invariant và điều kiện nghiệp vụ.
5. Tính lại số tiền/phí/giới hạn.
6. Thực hiện lại toàn bộ các thay đổi database.
7. Commit transaction mới.

~~~text
Attempt 1
  BEGIN
  đọc số dư và hạn mức
  tính toán
  cập nhật tài khoản / ledger
  DEADLOCK hoặc SERIALIZATION FAILURE
  ROLLBACK

Attempt 2 (transaction mới)
  BEGIN
  đọc lại số dư và hạn mức
  tính toán lại
  cập nhật tài khoản / ledger
  COMMIT
~~~

Transaction mới cần snapshot mới. Nếu chỉ bắt lỗi rồi tiếp tục dùng cùng transaction hoặc cùng entity state, ứng dụng có thể tiếp tục với transaction đã bị đánh dấu failed, hoặc dùng dữ liệu đã cũ.

## 3. Phân loại lỗi theo DBMS

Ứng dụng cần dựa trên mã lỗi ổn định của driver/DBMS, không chỉ tìm chuỗi "deadlock" trong thông báo. Mã cụ thể có thể thay đổi theo provider, phiên bản hoặc lớp exception bọc bên ngoài.

| DBMS | Deadlock thường gặp | Serialization failure / lỗi cạnh tranh liên quan | Ghi chú |
|---|---|---|---|
| PostgreSQL | SQLSTATE 40P01 (deadlock_detected) | SQLSTATE 40001 (serialization_failure) | Sau lỗi statement trong transaction, transaction thường ở trạng thái aborted cho đến khi rollback hoặc rollback đến savepoint. |
| SQL Server | Error 1205 | Có thể gặp lỗi serialization/transaction retry tùy cơ chế và isolation; cần phân loại mã cụ thể của ứng dụng | Deadlock victim transaction bị rollback; XACT_STATE() và XACT_ABORT ảnh hưởng cách dọn transaction trong các tình huống khác. |
| MySQL/InnoDB | Error 1213 (ER_LOCK_DEADLOCK) | Lỗi serialization riêng không thường được biểu diễn bằng cùng mã; lỗi lock wait timeout là 1205 | InnoDB thường rollback toàn bộ transaction khi deadlock. Lock wait timeout mặc định thường rollback statement; innodb_rollback_on_timeout có thể thay đổi hành vi. |
| Oracle | ORA-00060 | Lỗi phụ thuộc isolation/transaction có mã riêng theo tình huống | Deadlock detection thường rollback statement gây deadlock; không nên mặc định toàn transaction đã rollback. Ứng dụng cần xử lý transaction state rõ ràng. |
| SQLite | SQLITE_BUSY/SQLITE_LOCKED trong các tình huống cạnh tranh | SQLITE_BUSY_SNAPSHOT có thể xuất hiện khi snapshot đọc không thể nâng cấp thành writer | Thường cần kết thúc transaction và bắt đầu lại nếu quyết định dựa trên snapshot cũ. |

Các mã trên là điểm khởi đầu để phân loại, không thay thế tài liệu driver/DBMS đang chạy. Ví dụ, một framework có thể bọc SQLSTATE 40001 thành exception tổng quát; ứng dụng nên dùng exception translator hoặc mã vendor để phân loại chính xác.

### Không retry mọi lỗi SQL

Thông thường không retry tự động các lỗi sau với cùng đầu vào:

- Vi phạm CHECK, NOT NULL, FOREIGN KEY hoặc dữ liệu không hợp lệ.
- Vi phạm unique key do một thực thể khác đã chiếm khóa nghiệp vụ, trừ khi nghiệp vụ định nghĩa đây là tình huống có thể chuyển thành đọc/cập nhật.
- Lỗi cú pháp SQL, thiếu cột/bảng, sai kiểu dữ liệu.
- Lỗi quyền truy cập hoặc cấu hình.
- Lỗi nghiệp vụ như hết hàng, vượt hạn mức hoặc trạng thái đơn hàng không cho phép chuyển tiếp.

Những lỗi này thường không biến mất khi chạy lại cùng transaction. Retry vô điều kiện chỉ làm tăng tải và che giấu lỗi thật.

## 4. Quy tắc của một vòng retry an toàn

Một vòng retry cần có các thuộc tính sau:

1. **Chỉ retry lỗi đã phân loại:** deadlock và serialization failure là các ứng viên phổ biến; lock timeout cần chính sách riêng.
2. **Transaction mới cho mỗi attempt:** transaction cũ phải rollback/được kết thúc hoàn toàn.
3. **Đọc và tính lại:** không tái sử dụng snapshot, giá trị đọc hoặc kết quả tính toán có thể đã lỗi thời.
4. **Giới hạn số lần thử:** tránh vòng lặp vô hạn và starvation.
5. **Backoff:** chờ một khoảng ngắn trước attempt tiếp theo để các transaction cạnh tranh không lập tức va vào nhau lần nữa.
6. **Idempotency:** cùng một yêu cầu nghiệp vụ không tạo tác động trùng khi attempt trước có thể đã tạo hiệu ứng ngoài database.
7. **Quan sát:** ghi attempt number, loại lỗi, thời gian chờ, transaction boundary và kết quả cuối.

Mã giả:

~~~text
for attempt = 1 .. MAX_ATTEMPTS:
    try:
        bắt đầu transaction mới
        đọc dữ liệu cần thiết
        kiểm tra invariant
        tính toán lại thay đổi
        ghi tất cả thay đổi trong transaction
        commit
        trả kết quả thành công

    catch error:
        rollback/kết thúc transaction hiện tại

        nếu error không thuộc nhóm retryable:
            ném lỗi cho tầng gọi

        nếu attempt == MAX_ATTEMPTS:
            ném lỗi đã phân loại

        chờ backoff có jitter

trả lỗi cuối cùng
~~~

Không đặt sleep hoặc chờ backoff bên trong transaction đang giữ khóa. Transaction phải được kết thúc trước khi chờ.

## 5. Backoff, jitter và giới hạn retry

Nếu nhiều transaction cùng gặp deadlock rồi retry ngay lập tức, chúng có thể tái tạo cùng thứ tự tranh chấp và tiếp tục thất bại. Backoff làm lệch thời điểm thử lại; jitter ngẫu nhiên giảm khả năng nhiều worker cùng thức dậy một lúc.

Một công thức thường dùng:

~~~text
cap = min(max_delay, base_delay * 2^(attempt - 1))
delay = random(0, cap)       -- full jitter
~~~

Ví dụ cấu hình ban đầu cho một API nội bộ:

| Tham số | Giá trị minh họa | Ý nghĩa |
|---|---:|---|
| maxAttempts | 3 hoặc 4 | Tổng số lần thực hiện, gồm lần đầu |
| baseDelay | 20 ms | Mức backoff ban đầu |
| maxDelay | 250 ms | Trần thời gian chờ giữa các lần thử |
| requestDeadline | 2 s | Giới hạn tổng thời gian request |

Đây chỉ là giá trị minh họa. Cần căn cứ vào latency mục tiêu, thời gian lock, timeout của connection pool và mức cạnh tranh thực tế. Một job nền có thể dùng thời hạn dài hơn API đồng bộ.

Không tăng số lần retry để che một thiết kế luôn deadlock. Nếu cùng một cặp transaction lặp lại deadlock hàng trăm lần, cần đọc graph, chuẩn hóa thứ tự lấy khóa, giảm thời gian giữ khóa hoặc điều chỉnh truy vấn/index.

## 6. Đặt retry ở ngoài ranh giới transaction

Một lỗi phổ biến là đặt vòng lặp retry bên trong một phương thức đã mở transaction. Nếu transaction đầu đã thất bại, các attempt tiếp theo vẫn có thể dùng cùng transaction hoặc cùng persistence context.

Mẫu đúng về mặt kiến trúc:

~~~text
Retry coordinator (không mở transaction bao quanh vòng lặp)
  attempt 1 -> gọi transactional worker -> transaction T1
  nếu retryable error: T1 đã kết thúc
  backoff
  attempt 2 -> gọi transactional worker -> transaction T2
  nếu thành công: trả kết quả
~~~

Mỗi lần gọi worker phải tạo một transaction mới. Trong Spring, cần chú ý proxy boundary: gọi một method @Transactional khác thông qua Spring proxy thường tạo transaction theo propagation đã cấu hình; self-invocation trong cùng object có thể không đi qua proxy như mong đợi. Có thể tách retry coordinator và transactional service thành hai bean để ranh giới rõ ràng.

### 6.1. Ví dụ Spring/JPA

Một cấu trúc minh họa:

~~~java
@Service
public class TransferRetryService {
    private final TransferTransactionService transactionService;

    public TransferRetryService(TransferTransactionService transactionService) {
        this.transactionService = transactionService;
    }

    public TransferResult transfer(TransferCommand command) {
        int maxAttempts = 3;

        for (int attempt = 1; ; attempt++) {
            try {
                return transactionService.execute(command);
            } catch (RuntimeException ex) {
                if (!isRetryableConcurrencyFailure(ex) || attempt >= maxAttempts) {
                    throw ex;
                }
                sleepWithBackoff(attempt);
            }
        }
    }
}

@Service
public class TransferTransactionService {
    @Transactional
    public TransferResult execute(TransferCommand command) {
        // Đọc lại số dư, kiểm tra hạn mức và thực hiện toàn bộ cập nhật.
        // Mỗi lần gọi qua proxy tạo transaction riêng.
        return performTransfer(command);
    }
}
~~~

Đây là cấu trúc minh họa, không phải đoạn code hoàn chỉnh để copy nguyên trạng. isRetryableConcurrencyFailure phải nhận diện cause chain, SQLSTATE hoặc vendor code của driver đang dùng. Không nên phân loại mọi DataAccessException hoặc mọi RuntimeException thành retryable.

sleepWithBackoff cần xử lý interruption đúng cách và không được chạy trong transaction. Nếu dùng Spring Retry hoặc Resilience4j, vẫn phải bảo đảm interceptor retry bao ngoài transaction interceptor hoặc mỗi lần thử đi qua một transaction boundary mới. Thứ tự advisor/interceptor có ý nghĩa.

### 6.2. Rollback-only và exception bị nuốt

Nếu code bắt exception bên trong phương thức @Transactional, không ném lại và tiếp tục, transaction có thể đã bị đánh dấu rollback-only. Khi commit, ứng dụng có thể nhận UnexpectedRollbackException hoặc lỗi tương đương. Không nên nuốt lỗi deadlock/serialization rồi chạy lại câu lệnh trong transaction đó.

Hãy để exception thoát khỏi transactional method, kết thúc transaction, rồi để retry coordinator quyết định có gọi lại hay không.

### 6.3. EF Core

Với EF Core, mỗi attempt nên dùng transaction và thường là DbContext mới hoặc context được tạo lại sau lỗi. Change tracker có thể giữ entity state cũ; tái sử dụng context sau transaction thất bại có thể khiến việc retry khó dự đoán.

Nếu dùng execution strategy có retry của EF Core, thao tác tạo transaction thủ công cần được đặt trong delegate mà execution strategy có thể thực thi lại toàn bộ đơn vị công việc. Không chỉ retry một SaveChanges() nếu các bước đọc, tính toán và nhiều lần ghi trước đó cùng tạo thành một invariant.

## 7. Kiểm thử retry sau deadlock bằng hai session

Để kiểm tra cơ chế retry, cần tạo một deadlock có chủ đích và xác nhận transaction victim được chạy lại trong transaction mới.

Dùng hai hàng tài khoản:

| account_id | balance |
|---:|---:|
| 1 | 1000.00 |
| 2 | 1000.00 |

Hai giao dịch đều cần cập nhật cả hai hàng, nhưng lấy khóa theo thứ tự khác nhau.

### Lịch tạo deadlock

**Session A — bước A1**

~~~sql
BEGIN;
UPDATE lab_account
SET balance = balance - 10
WHERE account_id = 1;
~~~

**Session B — bước B1**

~~~sql
BEGIN;
UPDATE lab_account
SET balance = balance - 20
WHERE account_id = 2;
~~~

**Session A — bước A2**

~~~sql
UPDATE lab_account
SET balance = balance + 10
WHERE account_id = 2;
~~~

A chờ khóa hàng 2 do B giữ.

**Session B — bước B2**

~~~sql
UPDATE lab_account
SET balance = balance + 20
WHERE account_id = 1;
~~~

DBMS phát hiện chu trình và chọn một victim. Ghi lại session nào nhận lỗi, mã lỗi và trạng thái transaction sau lỗi.

### Kết quả cần quan sát

- Một transaction bị chọn làm victim; không giả định A hoặc B luôn là victim.
- Transaction victim không được tiếp tục dùng snapshot/transaction cũ.
- Transaction còn lại có thể tiếp tục hoặc commit sau khi vòng chờ được phá.
- Ứng dụng retry victim bằng transaction mới và đọc lại dữ liệu.
- Transaction A chuyển 10 từ account 1 sang account 2; transaction B chuyển 20 từ account 2 sang account 1. Khi cả hai nghiệp vụ hoàn tất, trạng thái cuối phải là account 1 = 1010.00 và account 2 = 990.00; tổng tiền ban đầu 2000.00 phải không đổi.

### Không dùng hai script cố định để mô phỏng retry ứng dụng

Hai session thủ công chứng minh deadlock có thể xảy ra. Để chứng minh ứng dụng retry đúng, cần một test harness hoặc integration test điều khiển transaction service, bắt lỗi victim và gọi lại service. Một script SQL không thể tự chứng minh interceptor retry, connection pool và persistence context của ứng dụng hoạt động đúng.

## 8. Kiểm thử retry sau serialization failure

Serialization failure cần một lịch mà các transaction có phụ thuộc đọc/ghi không thể tuần tự hóa. Ví dụ invariant: trong khoa 10 luôn có ít nhất một bác sĩ trực.

Trạng thái đầu:

| doctor_id | on_call |
|---:|---|
| 1 | TRUE |
| 2 | TRUE |
| 3 | FALSE |

Hai transaction ở PostgreSQL SERIALIZABLE:

**A1 — Session A**

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT COUNT(*)
FROM lab_doctor_duty
WHERE department_id = 10 AND on_call = TRUE;
~~~

A đọc 2.

**B1 — Session B**

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT COUNT(*)
FROM lab_doctor_duty
WHERE department_id = 10 AND on_call = TRUE;
~~~

B cũng đọc 2.

**A2 và B2 — cập nhật hai hàng khác nhau**

~~~sql
-- Session A
UPDATE lab_doctor_duty
SET on_call = FALSE
WHERE doctor_id = 1;

-- Session B
UPDATE lab_doctor_duty
SET on_call = FALSE
WHERE doctor_id = 2;
~~~

Khi cả hai cố commit, PostgreSQL SSI có thể cho một transaction commit và hủy transaction còn lại với SQLSTATE 40001. Thứ tự victim phụ thuộc lịch thực tế.

### Kết quả mong đợi

- Không được commit trạng thái có 0 bác sĩ trực.
- Một transaction có thể commit; transaction còn lại nhận serialization failure.
- Retry transaction thất bại phải đọc lại số bác sĩ trực trong snapshot mới.
- Sau khi transaction đầu đã tắt một bác sĩ, transaction retry thấy chỉ còn một người trực và phải từ chối tắt người cuối cùng.
- Trạng thái cuối có ít nhất một bác sĩ on_call = TRUE.

Khi viết integration test, nên dùng barrier/latch để đồng bộ hai transaction sau bước SELECT và trước bước UPDATE/COMMIT. Không dựa vào sleep(100) vì timing phụ thuộc máy, tải và scheduler.

## 9. Thiết kế integration test có thể tái lập

Một test retry đáng tin cậy cần điều khiển được thời điểm hai transaction xen kẽ. Các thành phần thường cần có:

- Database thật hoặc container DBMS cùng engine/version với môi trường mục tiêu.
- Hai connection độc lập; không dùng chung một connection cho hai transaction.
- Fixture cố định và reset trước mỗi test.
- Barrier/latch để A và B cùng hoàn tất bước đọc trước khi ghi.
- Hook hoặc test double để quan sát attempt number và loại exception.
- Assertion trên trạng thái database cuối, không chỉ kiểm tra method trả về.
- Deadline để test không treo vô hạn khi một session bị block.

Mẫu test logic:

~~~text
Arrange:
  reset database về S0
  tạo barrier cho A và B
  cấu hình retry maxAttempts = 3

Act:
  chạy transaction A và B trên hai connection
  cho cả hai đọc cùng trạng thái
  điều khiển thứ tự ghi để tạo deadlock hoặc serialization conflict
  cho retry coordinator chạy lại transaction bị hủy

Assert:
  có ít nhất một attempt nhận lỗi retryable
  số attempt không vượt maxAttempts
  attempt tiếp theo dùng transaction mới
  invariant nghiệp vụ vẫn đúng
  kết quả nghiệp vụ chỉ được áp dụng đúng số lần
  không còn transaction/lock bị bỏ lại
~~~

### Không chỉ assert rằng retry đã xảy ra

Một test có thể chứng minh số attempt tăng từ 1 lên 2 nhưng vẫn ghi sai dữ liệu nếu retry dùng lại snapshot cũ hoặc chạy tác động ngoài hai lần. Cần kiểm tra cả:

1. Lỗi đầu tiên đúng loại.
2. Transaction cũ đã rollback/được kết thúc.
3. Transaction mới đọc dữ liệu mới.
4. Quy tắc nghiệp vụ được đánh giá lại.
5. Trạng thái cuối thỏa invariant.
6. Tác động ngoài được deduplicate hoặc không bị lặp.

## 10. Dùng barrier thay vì sleep để điều khiển interleaving

Một test dùng Thread.sleep(100) không đáng tin cậy. 100 ms có thể đủ trên máy phát triển nhưng không đủ trong CI hoặc production-like load. Nó cũng không bảo đảm transaction kia đã hoàn tất đúng bước mong muốn.

Nên dùng CountDownLatch, CyclicBarrier, Phaser hoặc primitive đồng bộ tương ứng để tạo điểm hẹn:

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrites = new CountDownLatch(1);

// Trong mỗi transaction:
readRequiredRows();
bothRead.countDown();
bothRead.await(timeout);
allowWrites.await(timeout);
performWrites();
~~~

Đoạn mã chỉ minh họa điểm đồng bộ. Một deadlock cần thứ tự khóa cụ thể; vì vậy test có thể cần thêm barrier giữa lần cập nhật tài nguyên thứ nhất và yêu cầu tài nguyên thứ hai. Mọi wait trong test phải có timeout để test thất bại rõ ràng thay vì treo.

Với PostgreSQL, có thể kết hợp hai session với pg_stat_activity/pg_locks hoặc quan sát exception SQLSTATE. Với SQL Server, có thể thu thập Extended Events xml_deadlock_report. Với MySQL, dùng SHOW ENGINE INNODB STATUS hoặc Performance Schema. Chỉ bật quan sát đủ để chứng minh lịch đã xảy ra; không cần đưa truy vấn chẩn đoán production vào mọi test.

## 11. Kiểm thử lỗi lặp lại đến khi hết giới hạn

Không chỉ kiểm thử trường hợp retry lần hai thành công. Cần kiểm thử khi mọi attempt đều gặp lỗi retryable.

Kịch bản:

1. Cấu hình maxAttempts = 3.
2. Stub transaction service luôn ném lỗi deadlock/serialization được phân loại.
3. Gọi retry coordinator.
4. Xác nhận đúng ba attempt được gọi.
5. Xác nhận lỗi cuối được trả về.
6. Xác nhận không có transaction nào còn mở và không có side effect ngoài bị lặp.

Các assertion cần có:

| Điều kiện | Kết quả mong đợi |
|---|---|
| Lần đầu lỗi retryable | Có thể thử lại |
| Lần hai lỗi retryable | Có thể thử lại nếu chưa hết giới hạn |
| Lần cuối lỗi retryable | Dừng và trả lỗi |
| Lỗi không retryable | Chỉ một attempt, trả lỗi ngay |
| Tổng thời gian vượt request deadline | Dừng retry theo deadline tổng |
| Thread bị interrupt khi backoff | Khôi phục interrupt flag hoặc truyền interruption theo quy ước framework |

Giới hạn số lần thử phải bao gồm attempt đầu tiên hay chỉ số lần retry? Hãy định nghĩa rõ. Trong bài này maxAttempts = 3 nghĩa là tối đa ba lần thực hiện tổng cộng, tức tối đa hai lần chạy lại.

## 12. Kiểm thử idempotency và side effect

Retry transaction database không tự bảo vệ email, thanh toán, message hoặc HTTP request bên ngoài. Cần kiểm thử các cửa sổ lỗi quanh commit.

### Trường hợp A: transaction rollback trước khi có side effect

Nếu toàn bộ thay đổi chỉ nằm trong database, rollback rồi chạy lại transaction mới có thể an toàn nếu logic đọc/tính lại đúng.

### Trường hợp B: side effect đã xảy ra, ACK/response bị mất

Ví dụ payment provider đã charge nhưng client timeout. Retry với idempotency key mới có thể charge lần hai. Cùng một ý định nghiệp vụ phải dùng cùng key ổn định, chẳng hạn charge:order-123.

### Trường hợp C: ghi database và publish message

Không thực hiện COMMIT database rồi publish message như hai thao tác rời mà không có phục hồi. Dùng transactional outbox để ghi thay đổi và event trong cùng transaction; publisher có thể gửi lặp, nên consumer dùng inbox/unique event ID.

### Kịch bản test idempotency

1. Gửi cùng một command hai lần với cùng idempotency key.
2. Giả lập lần đầu đã commit hiệu ứng nhưng response bị mất.
3. Gửi lại command.
4. Xác nhận provider/consumer trả lại kết quả đã lưu, không tạo hiệu ứng mới.
5. Xác nhận có đúng một bản ghi nghiệp vụ hoặc một hiệu ứng thanh toán theo key.

Không dùng một UUID mới cho mỗi lần retry nếu UUID đó là idempotency key. Token attempt có thể thay đổi; key nghiệp vụ đại diện cho cùng một ý định phải ổn định.

## 13. Transactional outbox khi retry có phát event

Nếu transaction cần ghi dữ liệu và phát event, hãy ghi outbox cùng transaction:

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id;

INSERT INTO outbox_event (event_id, aggregate_id, event_type, payload)
VALUES (:stable_event_id, :order_id, 'OrderConfirmed', :payload);

COMMIT;
~~~

Nếu transaction bị deadlock hoặc serialization failure trước commit, cả UPDATE và INSERT outbox đều không được commit. Khi retry, ứng dụng chạy lại cả hai trong transaction mới. event_id nên được tạo theo quy tắc ổn định hoặc có unique constraint để tránh tạo nhiều event nghiệp vụ cho cùng một chuyển trạng thái.

Publisher đọc outbox và phát event sau commit. Nếu publisher phát thành công rồi chết trước khi đánh dấu đã gửi, event có thể được gửi lại. Consumer cần idempotency. Đây là cách tách retry transaction database khỏi retry giao tiếp message.

## 14. Lock timeout: có nên retry không?

Lock timeout không chứng minh deadlock. Có thể chỉ có một blocker chạy lâu. Retry ngay lập tức có thể khiến request lại xếp hàng sau cùng blocker và tiêu tốn connection.

Trước khi retry lock timeout, cần xem:

- Blocker có còn hoạt động hay đang idle in transaction?
- Thời gian giữ khóa có bất thường không?
- Request có deadline đủ cho một attempt mới không?
- Có thể giảm phạm vi hoặc thời gian giữ khóa không?
- Hệ thống có đang bị quá tải khiến retry làm vấn đề nặng hơn không?

Nếu chính sách cho phép retry, hãy dùng giới hạn nhỏ, backoff và metric riêng cho lock timeout. Phân biệt mã lỗi lock timeout với deadlock victim trong classifier. Không đổi timeout lớn hơn chỉ để che một transaction bị treo.

## 15. Khác biệt transaction cần lưu ý theo DBMS

### PostgreSQL

- SQLSTATE 40P01 là deadlock detected; 40001 là serialization failure.
- Sau lỗi statement trong transaction, transaction thường ở trạng thái aborted. Các câu lệnh tiếp theo nhận lỗi cho đến khi ROLLBACK hoặc rollback savepoint.
- Với SERIALIZABLE, ứng dụng phải sẵn sàng retry toàn bộ transaction khi nhận 40001.
- REPEATABLE READ dùng snapshot; không nên giả định nó ngăn write skew.
- Trong test, dùng connection mới hoặc rollback transaction cũ trước khi retry.

### SQL Server

- Error 1205 chỉ ra transaction được chọn làm deadlock victim.
- SQL Server rollback transaction victim để phá deadlock; ứng dụng cần mở transaction mới cho lần thử tiếp theo.
- Dùng Extended Events để thu deadlock graph, tránh chỉ log chuỗi exception.
- XACT_STATE() giúp xác định transaction còn hoạt động hay không trong các nhánh xử lý lỗi; không tiếp tục commit transaction đã không còn hợp lệ.
- Nếu dùng retry execution strategy của framework, bảo đảm toàn bộ đơn vị transaction được thực thi lại trong delegate phù hợp.

### MySQL/InnoDB

- Error 1213 biểu thị deadlock; InnoDB thường rollback toàn bộ transaction victim.
- Error 1205 là lock wait timeout, không đồng nghĩa deadlock. Mặc định thường chỉ statement bị rollback; cấu hình innodb_rollback_on_timeout có thể làm rollback toàn transaction.
- Sau deadlock, bắt đầu transaction mới và đọc lại dữ liệu.
- Kiểm tra isolation level, index và next-key/gap lock khi điều tra.

### Oracle

- ORA-00060 chỉ ra deadlock detected. Oracle thường rollback statement gây deadlock, không nên giả định toàn transaction đã rollback.
- Ứng dụng phải quyết định rollback transaction hiện tại trước khi retry toàn bộ đơn vị nghiệp vụ, để không giữ các thay đổi trước đó trong một transaction dở dang.
- Không retry chỉ statement gây deadlock nếu các bước trước đó và quyết định nghiệp vụ cần được tính lại.

### SQLite

- SQLITE_BUSY và SQLITE_LOCKED thường phản ánh cạnh tranh khóa; SQLITE_BUSY_SNAPSHOT có thể xảy ra khi transaction đọc snapshot cũ cố nâng cấp thành writer.
- Nếu quyết định ghi dựa trên snapshot cũ, rollback và bắt đầu transaction mới thường là cách an toàn.
- busy_timeout chỉ điều chỉnh thời gian chờ; nó không thay thế retry logic hoặc xử lý invariant.

## 16. Kiểm thử thứ tự khóa nhất quán sau khi thêm retry

Retry giúp giao dịch phục hồi, nhưng không phải cách sửa gốc cho deadlock lặp đi lặp lại. Nếu hai luồng luôn lấy khóa theo thứ tự ngược nhau, hệ thống sẽ tiếp tục tạo victim và retry.

Một cải tiến thường dùng là chuẩn hóa thứ tự truy cập tài nguyên. Ví dụ mọi transfer đều khóa account theo account_id tăng dần:

~~~text
accounts = sort([sourceAccountId, destinationAccountId])
lock/update accounts in ascending order
apply debit and credit according to business direction
~~~

Sau khi thay đổi, kiểm thử lại với hai transaction có nguồn/đích đảo ngược. Kết quả mong đợi là không còn chu trình do thứ tự account, dù vẫn có thể có lock wait ngắn. Đừng assert rằng hệ thống không bao giờ có deadlock nếu còn nhiều bảng/index hoặc luồng khác tham gia.

Retry vẫn cần thiết cho những lỗi cạnh tranh hiếm còn lại, nhưng tỷ lệ deadlock và số attempt trung bình nên giảm sau khi loại bỏ nguyên nhân gốc.

## 17. Ma trận kiểm thử tối thiểu

Một bộ integration test nên có các trường hợp sau:

| Test case | Cách tạo tình huống | Kết quả mong đợi |
|---|---|---|
| Deadlock rồi retry thành công | Hai session lấy hai hàng theo thứ tự ngược; victim được gọi lại | Transaction mới hoàn tất, invariant giữ nguyên |
| Serialization failure rồi retry thành công | Tạo write skew dưới SERIALIZABLE | Một attempt bị hủy; retry đọc trạng thái mới và quyết định lại |
| Retry hết giới hạn | Mỗi attempt ném lỗi retryable | Dừng đúng maxAttempts, trả lỗi cuối |
| Lỗi không retryable | Ném constraint violation hoặc validation error | Chỉ một attempt, không backoff |
| Lock timeout | Giữ blocker lâu hơn timeout | Phân loại riêng, retry theo policy hoặc trả timeout |
| Retry không lặp side effect | Giả lập response mất sau hiệu ứng ngoài | Cùng idempotency key trả cùng kết quả, không nhân đôi |
| Transaction mới mỗi attempt | Ghi transaction ID hoặc connection context | Attempt sau không dùng transaction đã aborted |
| Dữ liệu được đọc lại | Thay đổi dữ liệu giữa attempt 1 và 2 | Attempt 2 tính từ trạng thái mới |
| Thứ tự khóa đã chuẩn hóa | Hai luồng cập nhật tập hàng giống nhau theo cùng thứ tự | Deadlock do thứ tự đó biến mất; lock wait vẫn có thể có |
| Deadline bị vượt | Backoff/DB call tiêu hết deadline | Dừng retry và trả lỗi có kiểm soát |

## 18. Quan sát retry trong production

Log và metric nên cho biết retry có giúp hệ thống phục hồi hay chỉ che giấu tranh chấp.

Các trường log hữu ích:

- request_id hoặc job_id để liên kết lần gọi.
- transaction_attempt và max_attempts.
- Loại lỗi đã phân loại: deadlock, serialization failure, lock timeout.
- SQLSTATE/vendor error code và tên DBMS.
- Thời gian transaction trước khi lỗi và thời gian backoff.
- Kết quả cuối: success, exhausted, non-retryable.
- Transaction ID/session ID nếu DBMS cung cấp và chính sách log cho phép.

Metric nên theo dõi:

- Tỷ lệ transaction phải retry trên tổng transaction.
- Tỷ lệ thành công ở attempt 2/3.
- Số lần retry trung bình và p95 attempt count.
- Deadlock rate, serialization failure rate và lock timeout rate riêng biệt.
- Thời gian chờ khóa và transaction duration.
- Số request hết deadline hoặc hết số lần retry.
- Duplicate suppression count của idempotency/inbox.

Tránh log payload nhạy cảm hoặc toàn bộ tham số SQL. Dùng correlation ID và template statement để nối sự kiện mà không làm lộ dữ liệu.

## 19. Những lỗi thường gặp khi kiểm thử retry

| Lỗi | Vì sao không an toàn | Cách sửa |
|---|---|---|
| Retry câu SQL cuối thay vì toàn transaction | Dùng lại dữ liệu và quyết định từ snapshot cũ | Đọc lại, tính lại và chạy toàn bộ đơn vị nghiệp vụ |
| Retry bên trong transaction đã lỗi | Transaction có thể đã aborted/rollback-only | Đặt retry coordinator bên ngoài transactional method |
| Dùng lại persistence context cũ | Entity state và version có thể stale | Tạo context mới hoặc clear/reload theo đúng ranh giới |
| Retry mọi exception | Lặp lỗi dữ liệu, quyền hoặc nghiệp vụ | Phân loại theo SQLSTATE/vendor code và cause chain |
| Không giới hạn số lần thử | Có thể gây retry storm hoặc starvation | Max attempts, deadline và backoff |
| Dùng sleep cố định trong test | Timing không tái lập | Barrier/latch và timeout rõ ràng |
| Chỉ assert method trả success | Dữ liệu cuối có thể sai hoặc side effect bị lặp | Assert invariant, row count, attempt và idempotency |
| Tạo side effect trước commit rồi retry | Có thể gửi email/charge nhiều lần | Outbox, idempotency hoặc compensation |
| Nhầm lock timeout với deadlock | Áp dụng sai policy và bỏ qua blocker lâu | Phân loại mã lỗi riêng, điều tra wait graph |
| Tăng retry để che deadlock thường xuyên | Tăng tải mà không loại bỏ chu trình | Sửa thứ tự khóa, transaction duration và query plan |

## 20. Quy trình thực hiện một bài kiểm thử retry

1. **Chuẩn bị fixture:** reset dữ liệu, ghi trạng thái đầu và xác nhận không còn transaction cũ.
2. **Ghi DBMS context:** phiên bản, engine, isolation, autocommit và cấu hình liên quan.
3. **Tạo interleaving:** dùng hai connection độc lập và barrier để tạo deadlock hoặc serialization conflict.
4. **Thu bằng chứng:** lưu mã lỗi, victim, transaction/session, statement và tài nguyên.
5. **Xác nhận cleanup:** kiểm tra transaction cũ đã rollback/kết thúc; không giữ connection ở trạng thái lỗi.
6. **Quan sát retry:** xác nhận attempt mới bắt đầu transaction mới và đọc lại dữ liệu.
7. **Kiểm tra kết quả:** assert invariant và trạng thái cuối, không chỉ assert không còn exception.
8. **Kiểm tra side effect:** dùng idempotency key/inbox/outbox để chứng minh không có tác động trùng.
9. **Kiểm tra giới hạn:** tạo lỗi lặp đến khi hết attempts và xác nhận dừng đúng deadline.
10. **Đánh giá nguyên nhân:** nếu tỷ lệ lỗi cao, sửa thứ tự truy cập tài nguyên, giảm thời gian giữ khóa hoặc xem lại truy vấn.

## 21. Phiếu ghi nhận kết quả

~~~text
Test ID:
DBMS / version / engine:
Isolation level:
Autocommit:
Fixture version:

Business operation:
Invariant before:
Invariant after:

Attempt 1:
  transaction/session:
  SQLSTATE/vendor code:
  deadlock victim or serialization error:
  transaction rolled back/ended:

Attempt 2:
  new transaction/context:
  data re-read:
  result:

Retry policy:
  maxAttempts:
  backoff/jitter:
  total deadline:

Final database state:
Side effects / idempotency result:
Observed lock/deadlock metrics:
Conclusion:
~~~

## 22. Nguyên tắc kết luận

Một bài kiểm thử retry chỉ thành công khi chứng minh được nhiều hơn việc “lần gọi thứ hai không lỗi”. Cần xác nhận transaction cũ đã kết thúc, lần thử mới dùng transaction và snapshot mới, toàn bộ quyết định nghiệp vụ được tính lại, invariant vẫn đúng và tác động ngoài không bị lặp. Deadlock và serialization failure thường là lỗi cạnh tranh có thể phục hồi, nhưng chỉ retry khi mã lỗi đã được phân loại và đơn vị nghiệp vụ có thể chạy lại an toàn.

Giữ retry ở ngoài ranh giới transaction, dùng backoff có giới hạn và quan sát attempt count. Nếu deadlock lặp lại thường xuyên, hãy sửa thứ tự truy cập tài nguyên, giảm thời gian giữ khóa hoặc xem lại truy vấn. Retry là cơ chế phục hồi cho cạnh tranh còn lại; nó không thay thế thiết kế transaction và invariant đúng.
