# ORA-08177 và thử lại giao dịch SERIALIZABLE

Oracle Database hỗ trợ mức cô lập giao dịch **SERIALIZABLE**. Ở mức này, các câu truy vấn trong cùng một transaction đọc từ một snapshot nhất quán ở cấp transaction. Những thay đổi được transaction khác commit sau thời điểm snapshot được tạo không xuất hiện trong các câu đọc tiếp theo của transaction hiện tại.

Đổi lại, nếu transaction SERIALIZABLE muốn cập nhật một hàng đã bị transaction khác thay đổi và commit sau khi snapshot của nó bắt đầu, Oracle có thể từ chối thao tác với lỗi:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Đây là lỗi xung đột đồng thời có thể thử lại. Cách xử lý thường đúng là **rollback toàn bộ transaction, bắt đầu transaction mới, đọc lại dữ liệu và thực hiện lại toàn bộ nghiệp vụ**. Chỉ chạy lại câu SQL vừa lỗi là không đủ, vì các quyết định trước đó có thể dựa trên snapshot cũ.

Bài học trình bày cách SERIALIZABLE hoạt động trong Oracle, điều kiện thường dẫn đến ORA-08177, phạm vi rollback của câu lệnh và transaction, cách thử lại có giới hạn trong ứng dụng, cũng như các trường hợp nên dùng READ COMMITTED, khóa tường minh hoặc constraint thay cho việc tăng mức cô lập.

## 1. Nhắc lại mức cô lập giao dịch trong Oracle

Oracle thường dùng **READ COMMITTED** làm mức cô lập mặc định. Ở mức này, mỗi câu lệnh đọc có một snapshot nhất quán tại thời điểm câu lệnh bắt đầu. Một câu SELECT tiếp theo trong cùng transaction có thể nhìn thấy dữ liệu mới hơn nếu transaction khác đã commit ở giữa hai câu SELECT.

Với **SERIALIZABLE**, các câu lệnh trong cùng transaction đọc từ một snapshot ở cấp transaction. Những thay đổi được transaction khác commit sau thời điểm snapshot được tạo không xuất hiện trong snapshot của transaction hiện tại.

| Đặc điểm | READ COMMITTED | SERIALIZABLE |
|---|---|---|
| Snapshot đọc | Theo từng câu lệnh | Theo transaction |
| Hai SELECT trong cùng transaction | Có thể thấy hai trạng thái đã commit khác nhau | Cùng nhìn snapshot của transaction, cộng thay đổi của chính transaction |
| Thay đổi đã commit sau khi transaction bắt đầu | Có thể thấy ở câu SELECT tiếp theo | Không xuất hiện trong snapshot hiện tại |
| Xung đột khi ghi hàng đã bị transaction khác sửa sau snapshot | Thường chờ khóa rồi tiếp tục theo quy tắc READ COMMITTED | Có thể nhận ORA-08177 |
| Chi phí ứng dụng | Thường ít phải retry serialization conflict hơn | Cần có chiến lược xử lý serialization failure |

Không nên chọn SERIALIZABLE chỉ vì tên của nó nghe có vẻ an toàn hơn. Chọn isolation level dựa trên yêu cầu nhất quán, cách cập nhật dữ liệu và khả năng xử lý retry của ứng dụng.

## 2. SERIALIZABLE tạo snapshot ở cấp transaction

Để chọn SERIALIZABLE cho transaction hiện tại, có thể dùng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

Lệnh này phải được thực hiện ở đầu transaction, trước các câu lệnh SQL khác thuộc transaction. Nếu đã có câu lệnh bắt đầu transaction, không thể tùy tiện đổi isolation level giữa chừng.

Ví dụ:

~~~sql
COMMIT;

SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Các câu SELECT tiếp theo trong transaction vẫn đọc cùng snapshot.
~~~

Sau khi transaction kết thúc bằng COMMIT hoặc ROLLBACK, transaction tiếp theo có thể bắt đầu với isolation level được cấu hình cho nó.

### 2.1 Thay đổi của chính transaction vẫn được nhìn thấy

Snapshot của SERIALIZABLE không khiến transaction bị mù với chính các thay đổi của nó. Transaction nhìn thấy:

- Dữ liệu đã commit trước khi snapshot được tạo.
- Các thay đổi mà chính transaction hiện tại đã thực hiện.

Transaction không nhìn thấy thay đổi mới được transaction khác commit sau thời điểm snapshot.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM accounts
WHERE account_id = 101;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

SELECT balance
FROM accounts
WHERE account_id = 101;
~~~

SELECT thứ hai nhìn thấy số dư sau UPDATE của chính transaction hiện tại, dù snapshot đọc ban đầu được giữ ổn định.

### 2.2 SERIALIZABLE không khóa mọi hàng được đọc

Một hiểu nhầm phổ biến là SERIALIZABLE sẽ khóa tất cả hàng mà transaction SELECT. Trong Oracle, truy vấn đọc thông thường dùng read consistency và không tự động đặt khóa hàng chỉ vì isolation level là SERIALIZABLE.

Transaction khác vẫn có thể cập nhật và commit một hàng mà transaction hiện tại đã đọc. Xung đột được phát hiện khi transaction hiện tại cố sửa dữ liệu đã bị thay đổi sau snapshot; lúc đó Oracle có thể trả ORA-08177.

Điều này khác với cách nghĩ “đã SELECT thì hàng bị khóa”. Nếu nghiệp vụ cần khóa hàng để tuần tự hóa thao tác, phải dùng cơ chế khóa tường minh như SELECT ... FOR UPDATE hoặc một thiết kế khóa chung phù hợp.

## 3. ORA-08177 xuất hiện khi nào?

Thông điệp:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Tình huống điển hình:

1. Transaction A bắt đầu ở mức SERIALIZABLE và đọc một hàng.
2. Transaction B sửa chính hàng đó rồi COMMIT.
3. Transaction A cố UPDATE hoặc DELETE hàng theo snapshot cũ.
4. Oracle phát hiện hàng đã được transaction khác thay đổi sau khi snapshot của A bắt đầu và từ chối câu lệnh A bằng ORA-08177.

Oracle không thể cho A ghi đè một phiên bản dữ liệu mà A chưa nhìn thấy theo snapshot của transaction. Từ chối câu lệnh giúp tránh việc A tiếp tục dựa trên trạng thái cũ và tạo ra kết quả không phù hợp với isolation level đã chọn.

### 3.1 Lỗi thường liên quan tới xung đột ghi trên cùng hàng

Ví dụ hai transaction cùng cập nhật số dư tài khoản 101:

- A đọc số dư 1.000 ở snapshot của A.
- B cập nhật số dư thành 1.200 và COMMIT.
- A muốn cập nhật dựa trên số dư 1.000.

Ở SERIALIZABLE, A không được âm thầm ghi đè phiên bản mới mà B đã commit. A có thể nhận ORA-08177.

### 3.2 Không phải mọi xung đột đều là ORA-08177

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| ORA-08177 | Transaction SERIALIZABLE không thể tiếp tục thao tác ghi theo snapshot của nó |
| ORA-00060 | Deadlock: các session chờ khóa theo vòng lặp |
| ORA-00054 | Không lấy được resource lock theo yêu cầu NOWAIT hoặc timeout |
| ORA-00001 | Vi phạm unique constraint hoặc unique index |
| ORA-30006 | Hết thời gian chờ khi chờ khóa trong một số thao tác |

Không nên xử lý mọi lỗi SQL bằng cùng một chính sách retry. ORA-08177 là serialization conflict; lỗi unique có thể là dữ liệu trùng thực sự; deadlock cần điều tra thứ tự lấy khóa và có thể có chính sách retry riêng.

### 3.3 ORA-08177 không nhất thiết có nghĩa toàn transaction đã tự rollback

Oracle áp dụng statement-level atomicity cho câu lệnh DML bị lỗi: các thay đổi của chính câu lệnh thất bại được hoàn tác. Những câu DML thành công trước đó trong transaction có thể vẫn còn pending.

Về mặt kỹ thuật, transaction chưa chắc đã tự động bị rollback toàn bộ ngay khi nhận ORA-08177. Tuy nhiên, với chiến lược retry đúng, ứng dụng nên rollback toàn transaction và chạy lại nghiệp vụ từ đầu. Tiếp tục transaction cũ có thể khiến logic dựa trên snapshot cũ vẫn được dùng.

## 4. Thí nghiệm hai session tạo ORA-08177

Thực hiện trong schema thử nghiệm. Tạo một bảng và một hàng ban đầu:

~~~sql
CREATE TABLE lab_serializable_account (
    account_id NUMBER PRIMARY KEY,
    balance    NUMBER(14,2) NOT NULL
);

INSERT INTO lab_serializable_account VALUES (101, 1000);
COMMIT;
~~~

Mở hai session SQL riêng, gọi là Session A và Session B.

### 4.1 Session A: bắt đầu SERIALIZABLE và đọc hàng

Chạy trong Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A đọc được số dư 1.000. Snapshot của transaction A đã được thiết lập.

### 4.2 Session B: cập nhật và COMMIT

Trong Session B, isolation level mặc định READ COMMITTED:

~~~sql
UPDATE lab_serializable_account
SET balance = balance + 200
WHERE account_id = 101;

COMMIT;
~~~

Số dư đã commit thành 1.200.

### 4.3 Quay lại Session A: đọc rồi thử cập nhật

Chạy SELECT lại trong Session A:

~~~sql
SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A vẫn thấy số dư 1.000 vì nó đọc snapshot của transaction A.

Tiếp tục:

~~~sql
UPDATE lab_serializable_account
SET balance = balance - 100
WHERE account_id = 101;
~~~

Oracle có thể trả:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Session A đã cố ghi vào hàng mà Session B sửa và commit sau snapshot của A.

### 4.4 Rollback và kiểm tra trạng thái đã commit

Trong Session A:

~~~sql
ROLLBACK;
~~~

Sau đó bắt đầu một transaction mới và đọc lại:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT account_id, balance
FROM lab_serializable_account
WHERE account_id = 101;
~~~

Session A thấy số dư 1.200. Transaction mới có snapshot mới, bao gồm thay đổi đã commit của B.

## 5. Vì sao phải thử lại toàn bộ transaction?

Giả sử nghiệp vụ đặt hàng gồm:

1. Đọc giá sản phẩm và số lượng tồn.
2. Tính tổng tiền.
3. Kiểm tra hạn mức khách hàng.
4. Giảm tồn kho.
5. Ghi đơn hàng và chi tiết đơn hàng.
6. Ghi nhận thanh toán.

Nếu bước 5 gặp ORA-08177, chỉ chạy lại INSERT đơn hàng là nguy hiểm. Các quyết định ở bước 1–3 có thể dựa trên snapshot cũ; số lượng tồn, giá hoặc hạn mức đã thay đổi trong transaction khác.

Quy trình retry đúng:

~~~text
BEGIN TRANSACTION SERIALIZABLE
    Đọc dữ liệu đầu vào
    Kiểm tra quy tắc nghiệp vụ
    Tính toán lại
    Thực hiện toàn bộ DML
    COMMIT

Nếu gặp ORA-08177:
    ROLLBACK toàn bộ transaction
    Chờ một khoảng ngắn
    Bắt đầu transaction SERIALIZABLE mới
    Đọc lại dữ liệu
    Kiểm tra lại quy tắc
    Thực hiện lại toàn bộ nghiệp vụ
~~~

Transaction mới nhận snapshot mới. Chỉ rollback tới savepoint rồi chạy lại câu lệnh cuối không giải quyết được vấn đề snapshot cũ.

### 5.1 Retry không có nghĩa chạy lại cùng dữ liệu đã đọc

Mỗi lần retry phải đọc lại dữ liệu cần thiết và tính lại quyết định nghiệp vụ:

- Giá có thể đã thay đổi.
- Tồn kho có thể đã giảm.
- Hạn mức có thể đã được sử dụng.
- Trạng thái đơn hàng có thể đã thay đổi.
- Một hàng có thể đã bị xóa hoặc thay thế.

Nếu ứng dụng chỉ phát lại DML với các giá trị đã tính ở lần đầu, nó có thể lặp lại quyết định không còn đúng.

### 5.2 Khi retry không còn hợp lệ về nghiệp vụ

Một transaction có thể thất bại vì dữ liệu mới khiến điều kiện nghiệp vụ không còn đúng. Ví dụ sau khi retry, tồn kho không còn đủ. Đây không còn là lỗi serialization cần retry tiếp; ứng dụng phải trả kết quả nghiệp vụ như “không đủ hàng”.

Phân biệt:

- ORA-08177: xung đột snapshot, có thể thử lại transaction.
- Kiểm tra nghiệp vụ thất bại sau khi đọc snapshot mới: dừng retry và trả kết quả tương ứng.
- Lỗi kết nối hoặc kết quả COMMIT không xác định: cần xử lý riêng vì ứng dụng có thể không biết server đã commit hay chưa.

## 6. Retry có giới hạn và backoff

Nếu nhiều session liên tục cập nhật cùng dữ liệu, retry ngay lập tức có thể tạo một vòng lặp xung đột mới. Chiến lược thường dùng:

1. Chỉ retry lỗi đã xác định là transient, chẳng hạn Oracle error code 8177.
2. Rollback toàn transaction trước khi retry.
3. Giới hạn số lần thử.
4. Tăng dần thời gian chờ giữa các lần thử (*exponential backoff*).
5. Thêm một lượng ngẫu nhiên (*jitter*) để các client không đồng loạt thử lại.
6. Ghi log số lần retry và thời gian chờ.
7. Khi hết giới hạn, trả lỗi có thể xử lý hoặc đưa vào hàng đợi thử lại theo chính sách nghiệp vụ.

Ví dụ lịch chờ minh họa:

| Lần retry | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 50 ms |
| 2 | 100 ms |
| 3 | 200 ms |
| 4 | 400 ms |
| 5 | 800 ms |

Thời gian thực tế có thể cộng jitter và bị giới hạn bởi timeout tổng của request. Không có một con số cố định phù hợp cho mọi workload.

### 6.1 Vì sao không retry vô hạn?

Retry vô hạn có thể:

- Giữ request và connection quá lâu.
- Tăng tải khi database đang chịu contention.
- Làm hàng đợi request dài thêm.
- Che giấu lỗi thiết kế khiến transaction liên tục xung đột.
- Tạo hiệu ứng retry storm khi nhiều client cùng thất bại.

Sau số lần thử hợp lý, ghi nhận lỗi, trả trạng thái có thể thử lại sau hoặc chuyển sang xử lý bất đồng bộ.

### 6.2 Chỉ retry lỗi có thể phục hồi

Không nên viết:

~~~java
catch (SQLException ex) {
    retryEverything();
}
~~~

ORA-00001 có thể là request trùng; ORA-02291 có thể là dữ liệu tham chiếu không tồn tại; ORA-00942 là lỗi schema/quyền; các lỗi này không tự biến mất sau một khoảng chờ ngắn.

## 7. Mẫu retry trong JDBC

Trong JDBC, cần cấu hình isolation trước khi bắt đầu thực hiện câu SQL của transaction. Tắt autocommit để nhiều câu lệnh nằm trong cùng transaction.

Ví dụ khung xử lý:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE
        );
        connection.setAutoCommit(false);

        try {
            // Đọc lại dữ liệu trong transaction mới.
            Account source = loadAccount(connection, sourceAccountId);
            Account target = loadAccount(connection, targetAccountId);

            // Kiểm tra và tính toán lại từ dữ liệu vừa đọc.
            validateTransfer(source, target, amount);

            // Thực hiện toàn bộ thay đổi thuộc nghiệp vụ.
            debit(connection, sourceAccountId, amount);
            credit(connection, targetAccountId, amount);
            insertTransferLog(connection, requestId,
                              sourceAccountId, targetAccountId, amount);

            connection.commit();
            return;
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    } catch (SQLException ex) {
        if (!isOra08177(ex) || attempt == maxAttempts) {
            throw ex;
        }

        sleepWithBackoffAndJitter(attempt);
    }
}
~~~

Hàm kiểm tra lỗi có thể duyệt cả chuỗi SQLException:

~~~java
static boolean isOra08177(SQLException exception) {
    for (SQLException current = exception;
         current != null;
         current = current.getNextException()) {
        if (current.getErrorCode() == 8177) {
            return true;
        }
    }
    return false;
}
~~~

Các hàm loadAccount, validateTransfer, debit, credit, insertTransferLog và sleepWithBackoffAndJitter là phần minh họa cấu trúc; cần triển khai theo ứng dụng. Nếu lỗi được bọc trong exception khác, cần duyệt cause chain phù hợp với framework đang dùng.

### 7.1 Điểm quan trọng trong mẫu JDBC

- Mỗi lần thử lấy một transaction mới và đọc lại dữ liệu.
- Isolation được đặt trước các câu lệnh nghiệp vụ.
- Các DML cùng dùng một connection.
- Khi lỗi, rollback trước khi đóng connection.
- Chỉ lỗi 8177 được đưa vào nhánh retry trong ví dụ.
- Nếu commit thành công, trả về ngay.

Trong connection pool, cần tuân thủ quy tắc reset connection của pool. Không trả connection có transaction chưa kết thúc về pool. Nếu rollback thất bại, loại bỏ hoặc đánh dấu connection theo cơ chế của pool để tránh tái sử dụng trạng thái không rõ.

### 7.2 Xử lý kết quả COMMIT không xác định

Một lỗi mạng xảy ra đúng lúc gửi COMMIT có thể khiến client không biết server đã commit hay chưa. Đây khác với trường hợp server trả rõ ORA-08177.

Nếu client mù quáng chạy lại nghiệp vụ sau lỗi kết nối, có thể tạo giao dịch trùng nếu lần trước đã commit thành công. Dùng request ID/idempotency key có unique constraint hoặc một bảng trạng thái nghiệp vụ để nhận diện lần xử lý đã hoàn tất.

## 8. Idempotency và side effect trong transaction có retry

Một transaction có thể được chạy nhiều lần do retry. Vì vậy, thao tác phải được thiết kế để không tạo kết quả trùng khi cùng một yêu cầu được gửi lại.

Ví dụ bảng transfer có request ID duy nhất:

~~~sql
CREATE TABLE lab_transfer_request (
    request_id     VARCHAR2(64) PRIMARY KEY,
    from_account   NUMBER NOT NULL,
    to_account     NUMBER NOT NULL,
    amount         NUMBER(14,2) NOT NULL,
    status         VARCHAR2(20) NOT NULL,
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Ứng dụng dùng một REQUEST_ID ổn định cho cùng một yêu cầu nghiệp vụ. Nếu request đã được commit trước đó, unique constraint giúp nhận diện lần gửi trùng. Cần định nghĩa cách trả lại kết quả của request đã hoàn tất thay vì trừ tiền lần nữa.

### 8.1 Không gửi email hoặc gọi API trong vòng retry

Nếu ứng dụng gửi email trước COMMIT rồi gặp ORA-08177, email không thể tự rollback. Lần retry có thể gửi email lần nữa.

Mẫu thường dùng là transactional outbox:

1. Ghi thay đổi nghiệp vụ và một dòng outbox trong cùng transaction.
2. COMMIT.
3. Worker riêng đọc outbox và gửi message/email.
4. Worker đánh dấu đã gửi hoặc retry gửi theo idempotency key.

Như vậy việc thử lại transaction database không tự lặp side effect bên ngoài.

### 8.2 Không dùng sequence để bảo đảm request không trùng

Sequence có thể tạo khoảng trống khi transaction rollback hoặc retry. Một sequence ID mới ở mỗi lần thử không chứng minh đó là yêu cầu nghiệp vụ mới. Dùng request ID ổn định hoặc khóa nghiệp vụ duy nhất để chống trùng.

## 9. SERIALIZABLE và write skew

SERIALIZABLE trong Oracle cung cấp transaction-level read consistency và phát hiện xung đột khi transaction cố ghi dữ liệu đã bị transaction khác sửa sau snapshot. Tuy nhiên, không nên giả định chỉ đặt isolation level này là mọi quy tắc nghiệp vụ liên quan nhiều hàng đều được bảo vệ tự động.

Một tình huống đáng chú ý là **write skew**: hai transaction đọc cùng một trạng thái hợp lệ, sau đó cập nhật hai hàng khác nhau. Vì chúng không ghi đè cùng một hàng, xung đột ghi trên cùng row có thể không xảy ra, dù tổng thể dữ liệu sau hai commit vi phạm một quy tắc nghiệp vụ.

Ví dụ quy tắc: luôn phải có ít nhất một bác sĩ đang trực. Bảng có hai bác sĩ, cả hai đang trực:

| DOCTOR_ID | ON_CALL |
|---:|---|
| 1 | Y |
| 2 | Y |

Hai transaction cùng đọc thấy có hai người trực:

- Transaction A đổi bác sĩ 1 thành N.
- Transaction B đổi bác sĩ 2 thành N.
- Mỗi transaction chỉ cập nhật một hàng khác nhau.

Nếu không có khóa chung hoặc constraint bảo vệ quy tắc tổng thể, cả hai có thể commit và để lại trạng thái không còn ai trực. Đây là lý do cần phân tích invariant nghiệp vụ ở cấp nhiều hàng, không chỉ dựa vào isolation label.

### 9.1 Khóa một hàng điều phối chung

Một cách là tạo hàng khóa/guard đại diện cho lịch trực. Mỗi transaction phải khóa hàng đó trước khi đọc và cập nhật các bác sĩ:

~~~sql
SELECT roster_id
FROM on_call_roster
WHERE roster_id = 1
FOR UPDATE;

SELECT COUNT(*)
FROM doctors
WHERE on_call = 'Y';

-- Kiểm tra quy tắc rồi cập nhật bác sĩ.
~~~

Trong thiết kế dùng READ COMMITTED, các transaction cùng khóa một hàng guard sẽ được tuần tự hóa ở điểm đó. Sau khi chờ lấy khóa, transaction tiếp theo đọc trạng thái đã commit mới nhất ở câu lệnh tiếp theo rồi kiểm tra lại invariant.

Tất cả đường ghi liên quan phải tuân thủ cùng quy tắc khóa. Nếu có một luồng cập nhật bỏ qua guard row, cơ chế bảo vệ không còn đầy đủ.

### 9.2 Ưu tiên constraint khi có thể biểu diễn

Nếu quy tắc có thể biểu diễn bằng:

- PRIMARY KEY hoặc UNIQUE.
- FOREIGN KEY.
- CHECK constraint trên cùng một hàng.
- Một cột tổng hợp/guard được cập nhật có kiểm soát.

hãy để database bảo vệ invariant ở nơi thích hợp. Các quy tắc tổng hợp trên nhiều hàng thường cần khóa hoặc một mô hình dữ liệu khác; CHECK constraint thông thường không thể chứa truy vấn đếm hàng trong bảng khác.

## 10. Khi nào dùng SERIALIZABLE, khi nào dùng READ COMMITTED?

Không có isolation level tốt nhất cho mọi truy vấn.

### 10.1 SERIALIZABLE có thể phù hợp khi

- Một transaction cần đọc một snapshot nhất quán qua nhiều câu SELECT.
- Quy tắc nghiệp vụ phụ thuộc dữ liệu tại cùng thời điểm logic.
- Ứng dụng có thể rollback và retry toàn bộ transaction.
- Tần suất xung đột ghi đủ thấp để retry có hiệu quả.
- Các invariant nhiều hàng đã có khóa/constraint phù hợp.

### 10.2 READ COMMITTED thường phù hợp khi

- Ứng dụng chấp nhận mỗi câu SELECT thấy trạng thái mới nhất đã commit tại thời điểm câu đó bắt đầu.
- Cần cập nhật hàng cụ thể và có thể khóa bằng SELECT FOR UPDATE.
- Có thể gói kiểm tra và cập nhật vào một câu DML có điều kiện.
- Muốn tránh retry serialization conflict ở cấp transaction cho workload cập nhật thường xuyên.

### 10.3 Cập nhật có điều kiện thay cho đọc rồi ghi

Thay vì:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :account_id;

-- Ứng dụng kiểm tra balance ở phía client.

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id;
~~~

có thể đặt điều kiện ngay trong DML:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Sau đó kiểm tra số hàng cập nhật:

- 1 hàng: thao tác thỏa điều kiện.
- 0 hàng: tài khoản không tồn tại hoặc không đủ số dư; cần xác định nguyên nhân theo yêu cầu nghiệp vụ.

Cách này giảm khoảng thời gian giữa đọc và ghi và tận dụng khóa hàng của UPDATE. Nó thường đơn giản hơn việc nâng cả transaction lên SERIALIZABLE nếu chỉ cần bảo vệ một điều kiện trên một hàng.

### 10.4 SELECT FOR UPDATE

Nếu nghiệp vụ cần đọc nhiều cột rồi mới quyết định, có thể khóa hàng:

~~~sql
SELECT balance, status
FROM accounts
WHERE account_id = :account_id
FOR UPDATE;
~~~

Hàng được khóa cho tới khi transaction commit hoặc rollback. Session khác muốn sửa hàng đó phải chờ hoặc xử lý theo timeout/NOWAIT/SKIP LOCKED phù hợp.

Khóa tường minh có thể giúp tuần tự hóa thao tác trên các hàng được chọn. Nó không tự bảo vệ một quy tắc liên quan tới các hàng khác không được khóa; phải xác định đầy đủ tập hàng hoặc khóa guard row.

## 11. Các lỗi thường bị nhầm với ORA-08177

| Mã lỗi | Nguyên nhân | Có nên dùng cùng chính sách retry ORA-08177? |
|---|---|---|
| ORA-08177 | Serialization conflict trong transaction SERIALIZABLE | Có thể retry toàn transaction sau rollback |
| ORA-00060 | Deadlock | Có thể retry transaction theo chính sách riêng, nhưng cần điều tra thứ tự khóa |
| ORA-00001 | Vi phạm unique | Thường không retry mù; kiểm tra dữ liệu/request trùng |
| ORA-02291 | Thiếu khóa cha tham chiếu | Sửa thứ tự hoặc dữ liệu; không phải serialization conflict |
| ORA-02292 | Không thể xóa hàng cha vì còn hàng con | Xử lý quan hệ dữ liệu |
| ORA-00054 | Resource busy/NOWAIT hoặc timeout | Có thể thử lại theo timeout, nhưng phải hiểu resource đang bị giữ |
| ORA-30006 | Hết thời gian chờ khóa | Retry có thể phù hợp nếu nghiệp vụ và deadline cho phép |

Không phân loại lỗi chỉ bằng việc “có vẻ liên quan đến đồng thời”. Hãy kiểm tra mã Oracle, SQL operation, transaction state và log của các session liên quan.

## 12. Chẩn đoán ORA-08177 trong môi trường thực tế

Khi nhận lỗi, ghi nhận tối thiểu:

- SQL statement và bind values liên quan.
- Oracle error code 8177 và stack exception đầy đủ.
- Isolation level của session.
- Thời điểm bắt đầu transaction và thời điểm lỗi.
- SQL_ID nếu có.
- Request ID/correlation ID ở tầng ứng dụng.
- Số lần retry và thời gian chờ.
- Transaction có bao nhiêu câu DML trước câu lỗi.

### 12.1 Kiểm tra session

Trong môi trường có quyền truy cập view phù hợp:

~~~sql
SELECT sid,
       serial#,
       username,
       sql_id,
       module,
       action
FROM v$session
WHERE audsid = SYS_CONTEXT('USERENV', 'SESSIONID');
~~~

V$SESSION không nhất thiết hiển thị trực tiếp isolation level hiện tại trong mọi release. Ứng dụng nên ghi log cấu hình transaction tại thời điểm bắt đầu; DBA có thể dùng các view/session instrumentation phù hợp để điều tra.

### 12.2 Xem session và SQL đang hoạt động

DBA có thể kiểm tra:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       sql_id,
       event,
       blocking_session
FROM v$session
WHERE username IS NOT NULL
ORDER BY sid;
~~~

ORA-08177 là serialization conflict chứ không nhất thiết là session đang chờ khóa. Không phải lúc nào cũng có BLOCKING_SESSION để giải thích lỗi; cần xem lịch sử thao tác và transaction timing.

### 12.3 Đo tần suất retry

Ứng dụng nên ghi metric:

- Số transaction SERIALIZABLE bắt đầu.
- Số lần ORA-08177.
- Số transaction retry thành công.
- Số transaction hết retry.
- Retry count trung bình và percentile.
- Thời gian hoàn thành sau retry.
- Bảng/khóa nghiệp vụ thường xảy ra conflict.

Nếu một luồng nghiệp vụ thường xuyên retry nhiều lần, có thể isolation level hoặc mô hình khóa không phù hợp với mức contention. Tăng số lần retry vô hạn chỉ che giấu vấn đề.

## 13. Thử lại trong PL/SQL và quyền sở hữu transaction

PL/SQL procedure thường chạy trong transaction của session gọi nó. Một procedure không nên tự ý COMMIT/ROLLBACK toàn bộ transaction của caller nếu hợp đồng không quy định như vậy.

Đối với ORA-08177, việc retry thường nên được điều phối ở tầng sở hữu toàn bộ đơn vị nghiệp vụ:

1. Bắt lỗi serialization.
2. ROLLBACK transaction hiện tại.
3. Bắt đầu transaction mới ở isolation level phù hợp.
4. Đọc lại dữ liệu.
5. Chạy lại toàn bộ nghiệp vụ.

Không nên chỉ bắt ORA-08177 trong một procedure con rồi chạy lại một câu UPDATE, vì procedure con không nhất thiết biết các quyết định đã được caller thực hiện trước đó.

### 13.1 Savepoint không làm mới snapshot

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT balance
FROM lab_serializable_account
WHERE account_id = 101;

SAVEPOINT before_change;

-- Một session khác cập nhật và COMMIT hàng này.

UPDATE lab_serializable_account
SET balance = balance + 10
WHERE account_id = 101;
~~~

Nếu UPDATE nhận ORA-08177, việc:

~~~sql
ROLLBACK TO before_change;
~~~

không tạo snapshot mới. Transaction vẫn là transaction SERIALIZABLE ban đầu. Muốn lấy snapshot mới, cần kết thúc transaction bằng ROLLBACK và bắt đầu transaction khác.

## 14. Tối ưu thiết kế để giảm serialization conflict

Nếu ORA-08177 xảy ra thường xuyên, hãy điều tra nguyên nhân ở cấp thiết kế:

### 14.1 Giảm thời gian transaction mở

- Đọc và kiểm tra dữ liệu cần thiết gần thời điểm cập nhật.
- Không gọi dịch vụ bên ngoài trong khi transaction đang mở.
- Không thực hiện xử lý CPU dài giữa các DML.
- Không giữ transaction qua nhiều thao tác người dùng.
- Commit hoặc rollback sớm khi đơn vị nghiệp vụ đã hoàn tất.

Transaction càng dài, càng có nhiều thời gian để session khác sửa các hàng mà nó dự định cập nhật.

### 14.2 Giảm vùng dữ liệu ghi chung

- Xác định hàng nào thực sự cần cập nhật.
- Tránh cập nhật một hàng tổng hợp toàn cục cho mọi request nếu có thể phân vùng theo khóa nghiệp vụ.
- Cập nhật theo điều kiện chính xác.
- Tránh đọc một tập lớn rồi ghi lại toàn bộ nếu chỉ một số hàng thay đổi.

Không chia nhỏ partition/khóa một cách tùy tiện nếu làm thay đổi invariant. Mục tiêu là giảm contention mà vẫn bảo vệ đúng quy tắc.

### 14.3 Chọn isolation và locking theo yêu cầu

- Dùng READ COMMITTED khi snapshot theo câu lệnh là đủ.
- Dùng SELECT FOR UPDATE khi cần tuần tự hóa thao tác trên hàng cụ thể.
- Dùng guard row khi invariant trải trên nhiều hàng.
- Dùng unique/foreign key/check constraints khi có thể biểu diễn quy tắc trong schema.
- Dùng SERIALIZABLE khi cần transaction snapshot nhất quán và có khả năng xử lý retry.

## 15. Sơ đồ quyết định xử lý ORA-08177

~~~mermaid
flowchart TD
    A["Ứng dụng nhận ORA-08177"] --> B["Xác định lỗi 8177 từ Oracle"]
    B --> C["Rollback toàn bộ transaction"]
    C --> D{"Còn lượt retry và còn thời gian request?"}
    D -->|Không| E["Trả lỗi có thể xử lý / đưa vào hàng đợi"]
    D -->|Có| F["Backoff + jitter"]
    F --> G["Bắt đầu transaction mới"]
    G --> H["Đọc lại dữ liệu và kiểm tra nghiệp vụ"]
    H --> I{"Dữ liệu còn thỏa điều kiện?"}
    I -->|Không| J["Trả kết quả nghiệp vụ"]
    I -->|Có| K["Chạy lại toàn bộ DML"]
    K --> L{"COMMIT thành công?"}
    L -->|Có| M["Hoàn tất"]
    L -->|ORA-08177| B
    L -->|Lỗi khác| N["Xử lý theo mã lỗi"]
~~~

## 16. Bài thực hành tự kiểm tra

Các bài thực hành dùng bảng LAB_SERIALIZABLE_ACCOUNT ở phần 4. Nên chạy trong schema thử nghiệm và hai session độc lập.

### Bài 1 — Tái hiện ORA-08177

Thực hiện đúng thứ tự:

1. Session A chạy SET TRANSACTION SERIALIZABLE và SELECT số dư.
2. Session B UPDATE cùng hàng và COMMIT.
3. Session A SELECT lại.
4. Session A UPDATE cùng hàng.

Ghi lại giá trị A nhìn thấy và lỗi nhận được. Giải thích vì sao SELECT thứ hai vẫn thấy snapshot cũ.

### Bài 2 — Retry transaction

Sau lỗi ở bài 1, Session A ROLLBACK. Bắt đầu transaction SERIALIZABLE mới, đọc lại số dư, thực hiện lại UPDATE và COMMIT. So sánh snapshot trước và sau retry.

### Bài 3 — Statement rollback và transaction rollback

Trong Session A, thực hiện một UPDATE hợp lệ trên hàng khác trước khi tạo xung đột. Khi câu UPDATE xung đột nhận ORA-08177, kiểm tra trạng thái thay đổi trước đó. Sau đó ROLLBACK toàn transaction và kiểm tra từ session khác.

### Bài 4 — Savepoint không refresh snapshot

Trong transaction SERIALIZABLE, tạo SAVEPOINT rồi để Session B sửa và commit hàng. Khi Session A gặp ORA-08177, thử ROLLBACK TO SAVEPOINT và chạy lại câu UPDATE. Quan sát vì sao snapshot không được làm mới. Cuối cùng ROLLBACK toàn phần.

### Bài 5 — READ COMMITTED

Chạy cùng kịch bản ở READ COMMITTED. So sánh việc Session A đọc lại dữ liệu sau khi B commit và khả năng UPDATE của A. Giải thích khác biệt giữa snapshot theo câu lệnh và snapshot theo transaction.

### Bài 6 — Retry có giới hạn

Viết pseudo-code hoặc Java loop với tối đa 4 lần thử, backoff và jitter. Chỉ retry khi Oracle error code là 8177. Các lỗi unique constraint và dữ liệu nghiệp vụ không hợp lệ phải thoát khỏi vòng retry.

### Bài 7 — Idempotency

Tạo request ID duy nhất cho một lần chuyển tiền. Mô phỏng cùng request được gửi lại sau timeout. Thiết kế để lần gửi lại không trừ tiền hai lần.

### Bài 8 — Write skew

Dùng hai hàng bác sĩ trực. Hai session cùng đọc cả hai hàng rồi cập nhật hai hàng khác nhau trong transaction SERIALIZABLE. Quan sát invariant “luôn có ít nhất một người trực”. Đề xuất guard row hoặc cơ chế khóa chung.

### Bài 9 — Conditional DML

Viết UPDATE giảm số dư với điều kiện balance >= :amount, sau đó kiểm tra rowcount. So sánh với cách SELECT trước rồi UPDATE không điều kiện.

### Bài 10 — Đo contention

Chạy nhiều session cùng cập nhật một tập hàng. Ghi số ORA-08177, retry thành công, retry thất bại và thời gian hoàn thành. Thay đổi thời lượng transaction và so sánh.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| SERIALIZABLE khóa tất cả hàng đã SELECT | SELECT thông thường không tự khóa hàng |
| ORA-08177 tự rollback toàn bộ transaction | Câu lệnh lỗi được rollback; transaction trước đó có thể còn pending |
| Chỉ chạy lại câu SQL lỗi là đủ | Cần rollback và chạy lại toàn bộ nghiệp vụ từ snapshot mới |
| ROLLBACK TO SAVEPOINT tạo snapshot mới | Savepoint không kết thúc transaction và không refresh snapshot |
| SERIALIZABLE luôn ngăn mọi invariant bị vi phạm | Quy tắc nhiều hàng vẫn cần constraint hoặc khóa chung phù hợp |
| Mọi lỗi SQL đều có thể retry | Chỉ retry lỗi transient đã phân loại |
| Retry ngay lập tức vô hạn là an toàn | Cần giới hạn, backoff, jitter và metric |
| JDBC rollback luôn hủy được lần commit trước | Autocommit hoặc commit thành công trước đó không thể bị rollback |
| ORA-08177 giống deadlock | Đây là serialization conflict, khác ORA-00060 |
| Sequence không có khoảng trống nếu transaction rollback | NEXTVAL không được trả lại khi rollback |
| Email/API tự rollback cùng database | Side effect ngoài transaction cần outbox hoặc bù trừ |

## 18. Checklist triển khai retry SERIALIZABLE

Trước khi bật retry trong production, xác định:

- Isolation level được đặt trước câu lệnh đầu tiên của transaction chưa?
- Transaction có thực sự cần snapshot nhất quán cấp transaction không?
- Mã lỗi 8177 được nhận diện chính xác qua Oracle error code chưa?
- Khi gặp lỗi, ứng dụng có rollback toàn transaction không?
- Mỗi lần retry có đọc lại dữ liệu và tính lại quyết định không?
- Retry có giới hạn số lần và tổng thời gian không?
- Có backoff và jitter để tránh retry storm không?
- Có request ID/idempotency key để xử lý gửi lặp không?
- Có email/API hoặc side effect ngoài database trong vòng retry không?
- Có xử lý riêng kết quả COMMIT không xác định do lỗi mạng không?
- Các invariant nhiều hàng có khóa chung hoặc constraint bảo vệ không?
- Có metric về retry rate, thành công, thất bại và contention không?
- Có kiểm thử bằng nhiều session với dữ liệu đại diện không?

## 19. Ghi nhớ

| Chủ đề | Quy tắc |
|---|---|
| READ COMMITTED | Snapshot nhất quán theo từng câu lệnh |
| SERIALIZABLE | Snapshot nhất quán ở cấp transaction |
| SET TRANSACTION | Đặt isolation level ở đầu transaction |
| ORA-08177 | Xung đột ghi với dữ liệu đã bị transaction khác commit sau snapshot |
| Statement atomicity | Câu lệnh DML thất bại được rollback riêng |
| Transaction retry | Rollback toàn bộ và bắt đầu transaction mới |
| Savepoint | Không làm mới snapshot của transaction |
| Retry policy | Có giới hạn, backoff, jitter và chỉ retry lỗi phù hợp |
| Idempotency | Cùng request không tạo tác động nghiệp vụ lặp |
| Side effect | Dùng outbox/compensation cho hệ thống ngoài database |
| Write skew | Khóa/constraint chung có thể cần thiết cho invariant nhiều hàng |
| READ COMMITTED + locking | Thường phù hợp khi chỉ cần bảo vệ hàng hoặc phạm vi cụ thể |

ORA-08177 là tín hiệu Oracle không thể cho transaction SERIALIZABLE tiếp tục ghi theo snapshot cũ. Hãy rollback toàn transaction, bắt đầu transaction mới, đọc lại dữ liệu và chạy lại nghiệp vụ với retry có giới hạn. Đồng thời, xem lại isolation level, thời gian giữ transaction, các hàng bị tranh chấp và invariant nhiều hàng. Một chiến lược retry tốt phải bảo vệ cả tính đúng đắn của dữ liệu lẫn tính idempotent của request, đặc biệt khi ứng dụng có side effect bên ngoài database.
