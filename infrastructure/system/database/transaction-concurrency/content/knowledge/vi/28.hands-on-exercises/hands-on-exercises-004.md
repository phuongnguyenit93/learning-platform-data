# Thiết kế chuyển tiền có thứ tự khóa và khả năng thực thi lại

Một thao tác chuyển tiền phải cập nhật ít nhất hai tài khoản: trừ tiền ở tài khoản nguồn và cộng tiền ở tài khoản đích. Hai thay đổi phải cùng thành công hoặc cùng thất bại. Khi nhiều giao dịch chuyển tiền chạy đồng thời, chúng có thể khóa cùng các tài khoản theo thứ tự ngược nhau và tạo deadlock. Khi database hủy một transaction, ứng dụng còn phải biết khi nào có thể chạy lại toàn bộ thao tác mà không trừ hoặc cộng tiền hai lần.

Một thiết kế đáng tin cậy cần kết hợp bốn cơ chế:

1. **Invariant nghiệp vụ:** số dư không âm, số tiền hợp lệ, hai tài khoản phù hợp và tổng thay đổi được bảo toàn.
2. **Thứ tự khóa nhất quán:** mọi transaction khóa các tài khoản theo cùng một thứ tự xác định, chẳng hạn account_id tăng dần.
3. **Tính nguyên tử và sổ cái:** debit, credit, bản ghi chuyển tiền và hai bút toán ledger được commit trong cùng transaction.
4. **Idempotency và retry:** mỗi yêu cầu có một khóa duy nhất ổn định; khi deadlock hoặc kết quả COMMIT chưa rõ, ứng dụng có thể thực thi lại an toàn.

Bài học này xây dựng một quy trình chuyển tiền từ đầu, giải thích deadlock giữa hai chiều chuyển tiền, rồi đưa ra cách xử lý lỗi và kiểm chứng kết quả.

## 1. Xác định quy tắc nghiệp vụ trước khi viết SQL

Giả sử hệ thống có tài khoản A và B. Người dùng yêu cầu chuyển một số tiền từ A sang B.

Một thao tác hợp lệ phải thỏa các điều kiện:

- Tài khoản nguồn và đích tồn tại.
- Hai tài khoản khác nhau.
- Cả hai tài khoản đang ở trạng thái cho phép giao dịch.
- Số tiền lớn hơn 0.
- Hai tài khoản dùng cùng loại tiền, trừ khi hệ thống có quy trình đổi tiền riêng.
- Tài khoản nguồn có đủ số dư khả dụng.
- Số dư nguồn sau khi trừ không âm.
- Số dư đích sau khi cộng không vượt giới hạn lưu trữ hoặc giới hạn nghiệp vụ.
- Một request chỉ tạo tối đa một lần chuyển tiền.
- Bút toán debit và credit cùng xuất hiện hoặc cùng không xuất hiện.

Với chuyển tiền cùng loại tiền, invariant cơ bản là:

\[
Balance_{source}^{after}
=
Balance_{source}^{before} - Amount
\]

\[
Balance_{destination}^{after}
=
Balance_{destination}^{before} + Amount
\]

Và tổng số dư của hai tài khoản không đổi:

\[
Balance_{source}^{after}
+
Balance_{destination}^{after}
=
Balance_{source}^{before}
+
Balance_{destination}^{before}
\]

Đây là invariant của riêng hai tài khoản trong một giao dịch không có phí. Nếu có phí, tài khoản thu phí hoặc ledger fee phải được đưa vào cùng mô hình bảo toàn.

Không dùng kiểu số dấu phẩy động như FLOAT hoặc REAL để lưu tiền. Dùng DECIMAL/NUMERIC với precision và scale phù hợp với đơn vị tiền. Không so sánh số tiền bằng phép tính floating point.

### 1.1. Phân biệt số dư lưu trữ và sổ cái

Có thể lưu balance trực tiếp trên bảng Account để đọc nhanh, đồng thời lưu ledger bất biến để ghi lại từng lần thay đổi.

- Account.balance là số dư hiện tại được duy trì trong transaction.
- Ledger ghi hai bút toán cho một lần chuyển tiền: một debit âm và một credit dương.
- Transfer ghi nhận yêu cầu, người gửi, người nhận, số tiền và kết quả.
- Idempotency key liên kết các lần retry của cùng một ý định nghiệp vụ.

Balance và ledger phải được cập nhật trong cùng transaction. Nếu balance thay đổi nhưng ledger không được ghi, hệ thống mất khả năng đối soát. Nếu ledger được ghi nhưng balance không đổi, số dư hiển thị không còn khớp sổ cái.

Với hệ thống tài chính quan trọng, ledger thường là nguồn sự thật có tính bất biến; balance có thể là projection hoặc cache được duy trì đồng bộ. Dù chọn mô hình nào, việc ghi debit và credit phải nguyên tử.

## 2. Mô hình dữ liệu minh họa

Ví dụ dưới đây dùng PostgreSQL làm cú pháp chính. Có thể chuyển sang SQL Server, MySQL InnoDB hoặc Oracle với cú pháp tương ứng.

### 2.1. Bảng Account

~~~sql
CREATE TABLE account
(
    account_id bigint PRIMARY KEY,
    currency char(3) NOT NULL,
    status varchar(20) NOT NULL,
    balance numeric(19, 4) NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative
        CHECK (balance >= 0),
    CONSTRAINT ck_account_status
        CHECK (status IN ('ACTIVE', 'FROZEN', 'CLOSED'))
);
~~~

Khóa chính trên account_id giúp tìm và khóa một tài khoản nhanh. Index này cũng quan trọng đối với việc giới hạn phạm vi khóa khi nhiều transaction cùng hoạt động.

### 2.2. Bảng Transfer

~~~sql
CREATE TABLE transfer
(
    transfer_id uuid PRIMARY KEY,
    idempotency_key varchar(100) NOT NULL UNIQUE,
    request_fingerprint varchar(128) NOT NULL,
    source_account_id bigint NOT NULL,
    destination_account_id bigint NOT NULL,
    currency char(3) NOT NULL,
    amount numeric(19, 4) NOT NULL,
    status varchar(20) NOT NULL,
    rejection_code varchar(40),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CONSTRAINT ck_transfer_amount
        CHECK (amount > 0),
    CONSTRAINT ck_transfer_accounts
        CHECK (source_account_id <> destination_account_id),
    CONSTRAINT ck_transfer_status
        CHECK (status IN ('PENDING', 'COMPLETED', 'REJECTED'))
);
~~~

idempotency_key có UNIQUE constraint. Nếu cùng request được gửi lại, database chỉ cho phép một transfer có key đó.

request_fingerprint đại diện cho nội dung request đã chuẩn hóa, chẳng hạn source account, destination account, currency và amount. Khi một key đã tồn tại nhưng payload mới khác payload cũ, ứng dụng phải trả lỗi xung đột idempotency thay vì trả nhầm kết quả của giao dịch khác.

Trong ví dụ này, bảng Transfer không đặt foreign key trực tiếp đến Account để có thể lưu cả kết quả REJECTED cho tài khoản không tồn tại hoặc không hợp lệ. Ledger bên dưới vẫn tham chiếu các tài khoản hợp lệ. Nếu hệ thống chỉ lưu transfer thành công, có thể chọn schema khác.

### 2.3. Bảng Ledger

~~~sql
CREATE TABLE ledger_entry
(
    ledger_entry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_id uuid NOT NULL REFERENCES transfer(transfer_id),
    account_id bigint NOT NULL REFERENCES account(account_id),
    currency char(3) NOT NULL,
    entry_type varchar(10) NOT NULL,
    amount numeric(19, 4) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_ledger_entry_type
        CHECK (entry_type IN ('DEBIT', 'CREDIT')),
    CONSTRAINT uq_ledger_transfer_side
        UNIQUE (transfer_id, entry_type)
);
~~~

Một transfer thành công có đúng hai entry:

| Entry | Account | Amount |
|---|---|---:|
| DEBIT | Tài khoản nguồn | -Amount |
| CREDIT | Tài khoản đích | +Amount |

Ràng buộc UNIQUE trên (transfer_id, entry_type) ngăn tạo hai entry DEBIT hoặc hai entry CREDIT cho cùng transfer. Ứng dụng vẫn cần ghi cả hai entry trong cùng transaction.

Có thể thêm constraint hoặc quy trình kiểm tra để bảo đảm tổng ledger của mỗi transfer bằng 0 đối với chuyển tiền cùng currency. CHECK thông thường trên một dòng không thể kiểm tra tổng của nhiều dòng; invariant nhiều dòng cần được bảo vệ trong transaction và có thể được kiểm tra bằng reconciliation.

## 3. Vì sao hai chiều chuyển tiền có thể deadlock?

Deadlock có thể xảy ra khi hai transaction khóa cùng tài nguyên theo thứ tự ngược nhau.

Giả sử tài khoản có ID 10 và 20. Hai request đồng thời:

- T1 chuyển từ 10 sang 20.
- T2 chuyển từ 20 sang 10.

Nếu mỗi transaction khóa tài khoản nguồn trước rồi mới khóa tài khoản đích, lịch có thể là:

~~~text
Transaction T1                  Transaction T2
--------------                  --------------
Khóa account 10
                                Khóa account 20
Yêu cầu khóa account 20
                                Yêu cầu khóa account 10
Chờ T2                          Chờ T1

T1 giữ 10, chờ 20.
T2 giữ 20, chờ 10.
Hai transaction tạo chu trình chờ.
Database phát hiện deadlock và hủy một victim.
~~~

Đây không phải lỗi ngẫu nhiên của database. Mỗi transaction đang giữ một khóa mà transaction kia cần. Nếu không có quy tắc thứ tự khóa chung, hệ thống có thể lặp lại deadlock khi hai chiều chuyển tiền xuất hiện đồng thời.

### 3.1. Thứ tự khóa toàn cục

Chọn một thứ tự cố định, ví dụ khóa account_id nhỏ hơn trước rồi mới khóa account_id lớn hơn.

Với hai tài khoản 10 và 20:

- Chuyển 10 → 20: khóa 10 rồi 20.
- Chuyển 20 → 10: vẫn khóa 10 rồi 20.

Cả hai transaction đều xin khóa theo cùng thứ tự. Một transaction có thể phải chờ transaction kia ở account 10, nhưng không thể giữ account 20 trong khi chờ account 10. Vì vậy, chu trình chờ ngược chiều trên hai dòng này được loại bỏ.

~~~text
Thứ tự khóa chuẩn: account_id tăng dần

T1: 10 -> 20       T2: 20 -> 10
     |                  |
     v                  v
   khóa 10            khóa 10
     |                  |
   khóa 20            chờ 10
     |                  |
   commit              T1 kết thúc
                        |
                      khóa 10
                        |
                      khóa 20
                        |
                      commit
~~~

Thứ tự khóa phải được áp dụng cho mọi đường ghi liên quan đến tài khoản: chuyển tiền, thu phí, hoàn tiền, điều chỉnh số dư, đóng băng tài khoản và batch settlement. Nếu một luồng khác vẫn khóa nguồn trước đích, deadlock vẫn có thể xuất hiện.

### 3.2. Mở rộng quy tắc cho nhiều tài nguyên

Nếu transaction khóa nhiều loại tài nguyên, hãy định nghĩa thứ tự toàn cục, ví dụ:

1. Idempotency/Transfer request key.
2. Các Account theo account_id tăng dần.
3. Các record phụ theo khóa chính tăng dần.
4. Ledger entries và Outbox events.
5. Các tài nguyên khác theo thứ tự đã thống nhất.

Thứ tự cụ thể phụ thuộc schema và luồng nghiệp vụ. Điều quan trọng là mọi code path dùng cùng quy tắc. Trigger, foreign key, unique index và stored procedure cũng có thể tham gia lấy khóa; cần tính chúng vào khi điều tra deadlock.

## 4. Khóa tài khoản theo thứ tự xác định

Không nên viết logic "khóa nguồn trước, khóa đích sau". Hãy tính hai ID theo thứ tự tăng dần, khóa lần lượt và sau đó ánh xạ dữ liệu đã đọc về vai trò source/destination.

### 4.1. PostgreSQL: hai locking read tuần tự

Trong một transaction:

~~~sql
BEGIN;

-- :first_account_id là LEAST(source_id, destination_id)
-- :second_account_id là GREATEST(source_id, destination_id)

SELECT account_id, currency, status, balance
FROM account
WHERE account_id = :first_account_id
FOR UPDATE;

SELECT account_id, currency, status, balance
FROM account
WHERE account_id = :second_account_id
FOR UPDATE;

-- Ứng dụng ánh xạ hai dòng về source và destination,
-- kiểm tra nghiệp vụ rồi thực hiện debit/credit.

COMMIT;
~~~

Hai câu SELECT chạy trên cùng connection và transaction. Câu thứ nhất khóa account ID nhỏ hơn. Câu thứ hai chỉ chạy sau khi đã lấy khóa thứ nhất.

Có thể dùng một SELECT ... ORDER BY account_id FOR UPDATE để khóa một tập dòng, nhưng hai locking read tuần tự làm quy tắc thứ tự rõ ràng ở tầng ứng dụng. Hãy dùng khóa chính để mỗi truy vấn tìm đúng một dòng và không thay đổi account_id trong vòng đời tài khoản.

### 4.2. SQL Server: UPDLOCK và HOLDLOCK

Với SQL Server, có thể dùng hai truy vấn point lookup theo thứ tự tăng dần:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Currency, Status, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = @firstAccountId;

SELECT AccountId, Currency, Status, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = @secondAccountId;

-- Kiểm tra và cập nhật hai tài khoản.

COMMIT TRANSACTION;
~~~

UPDLOCK yêu cầu update lock khi đọc; HOLDLOCK áp dụng semantics SERIALIZABLE cho tham chiếu bảng trong câu lệnh. Với truy vấn bằng khóa chính, mục tiêu là khóa dòng tài khoản cần cập nhật và giữ khóa đến cuối transaction.

Cần kiểm tra execution plan, index và lock behavior thực tế. Hint không thay thế quy tắc khóa nhất quán trong mọi đường ghi. Nếu transaction truy cập thêm bảng khác, vẫn phải thống nhất thứ tự tài nguyên trên toàn hệ thống.

### 4.3. MySQL InnoDB và Oracle

InnoDB:

~~~sql
START TRANSACTION;

SELECT account_id, currency, status, balance
FROM account
WHERE account_id = ?
FOR UPDATE;

-- Thực hiện truy vấn cho account_id còn lại theo thứ tự tăng dần.
-- Sau khi khóa cả hai dòng, kiểm tra và cập nhật.

COMMIT;
~~~

Oracle cũng hỗ trợ SELECT ... FOR UPDATE. Với cả hai DBMS, ứng dụng cần gửi truy vấn cho ID nhỏ trước rồi ID lớn sau trên cùng transaction/connection.

Đừng dựa vào thứ tự tham số nguồn/đích để chọn thứ tự khóa. Hãy sắp xếp ID trước khi truy vấn.

## 5. Quy trình chuyển tiền trong một transaction

Một luồng chuyển tiền nên có ranh giới rõ:

~~~text
Nhận request và idempotency key
             |
             v
Kiểm tra request đã xử lý chưa
             |
             v
BEGIN transaction mới
             |
             v
Ghi nhận key hoặc lấy kết quả cũ
             |
             v
Khóa hai account theo ID tăng dần
             |
             v
Kiểm tra trạng thái, currency, balance
             |
       +-----+------+
       |            |
     Không hợp lệ   Hợp lệ
       |            |
       v            v
Ghi REJECTED     Debit source
       |         Credit destination
       |         Ghi hai ledger entries
       |         Ghi outbox event
       |         Ghi COMPLETED
       +-----+------+
             |
             v
           COMMIT
             |
             v
         Trả kết quả
~~~

Các thay đổi liên quan phải cùng commit. Nếu debit đã chạy nhưng credit hoặc ledger insert thất bại, ROLLBACK sẽ hủy tất cả thay đổi trong transaction.

Không gọi email, webhook, payment provider hoặc message broker trong lúc đang giữ khóa hai tài khoản. Những thao tác mạng có thời gian không xác định sẽ kéo dài transaction và tăng contention.

## 6. Idempotency: cùng một request chỉ chuyển tiền một lần

Một request có thể được gửi lại vì người dùng nhấn nút hai lần, gateway retry hoặc client mất kết nối sau khi database đã commit. Nếu mỗi lần retry tạo một transfer mới, tài khoản có thể bị trừ tiền nhiều lần.

Dùng một idempotency key ổn định cho một ý định chuyển tiền. Key đó được tạo ở client hoặc service boundary và giữ nguyên qua mọi lần retry của cùng request.

### 6.1. Ghi key trước khi khóa account

Trong PostgreSQL, có thể thử insert transfer request trước:

~~~sql
INSERT INTO transfer
(
    transfer_id,
    idempotency_key,
    request_fingerprint,
    source_account_id,
    destination_account_id,
    currency,
    amount,
    status
)
VALUES
(
    :transfer_id,
    :idempotency_key,
    :request_fingerprint,
    :source_account_id,
    :destination_account_id,
    :currency,
    :amount,
    'PENDING'
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING transfer_id;
~~~

Có hai kết quả:

- Có một dòng trả về: transaction này vừa đăng ký key và có quyền tiếp tục xử lý request.
- Không có dòng trả về: key đã được dùng. Đọc transfer hiện có theo key, so sánh fingerprint/payload và trả kết quả đã lưu.

Nếu hai request cùng key chạy đồng thời, unique index phối hợp chúng. Một request có thể phải chờ request còn lại commit hoặc rollback. Nếu request đầu commit, request sau đọc kết quả cũ. Nếu request đầu rollback, request sau có thể đăng ký key và thực hiện giao dịch.

Mọi code path phải dùng cùng thứ tự: đăng ký hoặc kiểm tra idempotency key trước, sau đó mới khóa account. Nếu một luồng khác khóa account trước rồi mới lấy key, có thể tạo deadlock giữa unique-key wait và account lock.

### 6.2. Cùng key nhưng payload khác phải bị từ chối

Ví dụ key X đã dùng cho chuyển 100 từ A sang B. Một request mới gửi key X nhưng chuyển 500 từ C sang D. Không được trả kết quả cũ như thể request mới thành công.

So sánh các trường quan trọng:

- source account.
- destination account.
- currency.
- amount.
- loại giao dịch hoặc tenant nếu có.

Nếu khác, trả lỗi idempotency conflict. Không chạy giao dịch mới dưới cùng key.

### 6.3. Lưu kết quả REJECTED hay rollback?

Có hai chính sách:

**Ghi nhận cả kết quả từ chối.** Nếu nguồn không đủ tiền, cập nhật transfer thành REJECTED, ghi rejection_code và commit transaction mà không thay đổi số dư. Lần gửi lại cùng key sẽ nhận lại kết quả từ chối ban đầu. Người dùng muốn thử lại sau khi nạp tiền phải tạo một idempotency key mới vì đó là một ý định mới.

**Chỉ lưu transfer thành công.** Nếu không đủ tiền, rollback cả transfer request. Một request cùng key được gửi lại sau này có thể được đánh giá lại. Cách này có semantics khác và phải được định nghĩa rõ.

Ví dụ trong bài này chọn chính sách thứ nhất: key đại diện cho một lần thử nghiệp vụ và kết quả REJECTED được lưu. Các lỗi kỹ thuật khiến transaction rollback thì không lưu kết quả cuối; cùng key có thể được retry.

## 7. Ví dụ quy trình SQL PostgreSQL

Đây là mẫu minh họa cho tầng service hoặc stored procedure. Ứng dụng phải giữ cùng connection và transaction từ lúc đăng ký idempotency key đến lúc COMMIT. Các placeholder được thay bằng tham số đã bind; không nối chuỗi SQL từ dữ liệu người dùng.

### 7.1. Bắt đầu transaction và đăng ký request

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

INSERT INTO transfer
(
    transfer_id,
    idempotency_key,
    request_fingerprint,
    source_account_id,
    destination_account_id,
    currency,
    amount,
    status
)
VALUES
(
    :transfer_id,
    :idempotency_key,
    :request_fingerprint,
    :source_account_id,
    :destination_account_id,
    :currency,
    :amount,
    'PENDING'
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING transfer_id;
~~~

Nếu không insert được vì key đã tồn tại, đọc transfer hiện tại:

~~~sql
SELECT
    transfer_id,
    request_fingerprint,
    status,
    rejection_code,
    source_account_id,
    destination_account_id,
    currency,
    amount
FROM transfer
WHERE idempotency_key = :idempotency_key;
~~~

So sánh fingerprint và trả kết quả đã lưu nếu khớp. Nếu khác, rollback transaction và trả lỗi xung đột key. Không tiếp tục khóa account cho request trùng.

Trong READ COMMITTED, câu SELECT tiếp theo có snapshot mới và có thể nhìn thấy transfer đã commit của request cạnh tranh sau khi INSERT ... ON CONFLICT chờ kết thúc. Với SERIALIZABLE, có thể cần xử lý serialization failure và retry toàn bộ transaction.

### 7.2. Khóa hai account theo ID tăng dần

Ứng dụng tính:

~~~text
first_id  = min(source_account_id, destination_account_id)
second_id = max(source_account_id, destination_account_id)
~~~

Sau đó thực hiện tuần tự:

~~~sql
SELECT account_id, currency, status, balance
FROM account
WHERE account_id = :first_id
FOR UPDATE;

SELECT account_id, currency, status, balance
FROM account
WHERE account_id = :second_id
FOR UPDATE;
~~~

Ứng dụng giữ dữ liệu hai dòng, ánh xạ lại source và destination theo ID ban đầu rồi kiểm tra:

- Cả hai dòng tồn tại.
- Cả hai có status ACTIVE.
- Currency của hai tài khoản và request giống nhau.
- Amount lớn hơn 0.
- Source balance đủ.
- Destination balance không vượt giới hạn.

Nếu một điều kiện nghiệp vụ không thỏa, cập nhật transfer sang REJECTED với rejection_code tương ứng rồi COMMIT. Không thay đổi account hoặc ledger.

### 7.3. Debit và credit có điều kiện

Khi mọi điều kiện đã hợp lệ, vẫn nên đặt điều kiện bảo vệ trong UPDATE để tránh phụ thuộc hoàn toàn vào logic ứng dụng:

~~~sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :source_account_id
  AND status = 'ACTIVE'
  AND currency = :currency
  AND balance >= :amount
RETURNING account_id;
~~~

Phải nhận đúng một dòng. Nếu không có dòng, coi là điều kiện nghiệp vụ không còn hợp lệ hoặc dữ liệu đã thay đổi; không tiếp tục credit.

Cộng tiền vào tài khoản đích:

~~~sql
UPDATE account
SET balance = balance + :amount
WHERE account_id = :destination_account_id
  AND status = 'ACTIVE'
  AND currency = :currency
RETURNING account_id;
~~~

Phải nhận đúng một dòng. Nếu credit thất bại sau debit, rollback toàn transaction để debit cũng được hoàn tác.

Nếu tài khoản đích có giới hạn số dư tối đa, thêm điều kiện phù hợp vào UPDATE và xử lý kết quả không cập nhật được dòng.

### 7.4. Ghi hai ledger entries và hoàn tất transfer

~~~sql
INSERT INTO ledger_entry
    (transfer_id, account_id, currency, entry_type, amount)
VALUES
    (:transfer_id, :source_account_id, :currency, 'DEBIT', -:amount),
    (:transfer_id, :destination_account_id, :currency, 'CREDIT', :amount);

UPDATE transfer
SET status = 'COMPLETED',
    completed_at = clock_timestamp()
WHERE transfer_id = :transfer_id
  AND status = 'PENDING';
~~~

Kiểm tra UPDATE transfer thay đổi đúng một dòng. Sau đó có thể ghi một event vào Outbox trong cùng transaction:

~~~sql
INSERT INTO outbox_event
    (event_id, aggregate_id, event_type, payload, created_at)
VALUES
    (:event_id, :transfer_id, 'TransferCompleted', :payload,
     clock_timestamp());
~~~

Cuối cùng:

~~~sql
COMMIT;
~~~

Khi COMMIT thành công, balance, hai ledger entries, transfer status và outbox event cùng trở nên bền vững. Nếu bất kỳ bước ghi nào thất bại trước commit, ROLLBACK hủy toàn bộ thay đổi của transaction.

## 8. Vì sao phải retry toàn bộ transaction?

Deadlock victim hoặc serialization failure có thể làm transaction hiện tại bị rollback. Các giá trị balance mà ứng dụng đã đọc trước đó không còn là đầu vào đáng tin cậy cho một lần chạy mới.

Ví dụ:

1. T1 đọc source balance = 500.
2. T1 chuẩn bị chuyển 300.
3. T1 gặp deadlock và bị hủy.
4. Một giao dịch khác chuyển tiền khỏi source và commit.
5. Ứng dụng chỉ chạy lại câu UPDATE với giả định balance cũ.
6. Quyết định có đủ tiền hay không có thể sai.

Retry đúng phải bắt đầu transaction mới, đọc lại hai account, kiểm tra trạng thái và số dư, tính lại kết quả rồi mới ghi.

~~~text
Attempt 1
  BEGIN
  Register/check idempotency
  Lock accounts in order
  Read balances
  Validate
  Debit + credit + ledger
  DEADLOCK -> ROLLBACK

Backoff

Attempt 2
  BEGIN transaction mới
  Resolve same idempotency key
  Lock accounts in same order
  Read balances again
  Validate again
  Debit + credit + ledger
  COMMIT
~~~

Không tái sử dụng object Account hoặc số dư được load bên ngoài vòng retry. Mỗi lần thử cần có transaction và dữ liệu đọc mới.

## 9. Phân loại lỗi: lỗi nào retry, lỗi nào trả về nghiệp vụ?

Không retry mọi exception. Một số lỗi là kết quả nghiệp vụ ổn định; một số lỗi là xung đột tạm thời; một số lỗi khiến kết quả commit chưa xác định.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Deadlock victim | SQL Server 1205, PostgreSQL 40P01, InnoDB 1213, Oracle ORA-00060 | Rollback transaction và retry toàn bộ với giới hạn |
| Serialization failure | PostgreSQL 40001, Oracle ORA-08177 | Rollback và chạy lại toàn bộ transaction trên snapshot mới |
| Snapshot update conflict | SQL Server 3960 | Rollback transaction và đánh giá lại toàn bộ nghiệp vụ |
| Lock wait timeout | SQL Server 1222, MySQL 1205 | Kiểm tra phạm vi rollback và trạng thái transaction; retry toàn bộ nếu transaction được khởi động lại an toàn |
| Không đủ số dư | Quy tắc nghiệp vụ | Ghi REJECTED hoặc trả lỗi; không retry tự động cùng dữ liệu |
| Tài khoản bị đóng băng | Quy tắc nghiệp vụ | Từ chối; chỉ thử lại khi có một request nghiệp vụ mới |
| Sai currency hoặc amount | Validation | Trả lỗi; sửa request trước khi gửi lại |
| Idempotency key trùng, payload giống | Request đã xử lý | Trả kết quả đã lưu, không tạo transfer mới |
| Idempotency key trùng, payload khác | Client dùng lại key sai | Trả conflict; không retry dưới key đó |
| Mất kết nối trong lúc COMMIT | Kết quả commit không rõ | Tra cứu bằng cùng idempotency key trước khi quyết định |
| Lỗi constraint do bug hoặc dữ liệu sai | Unique/FK/CHECK ngoài trường hợp idempotency dự kiến | Điều tra; không retry mù |

Mã lỗi và phạm vi rollback cụ thể phụ thuộc DBMS, phiên bản và cấu hình. Ví dụ MySQL InnoDB thường rollback toàn transaction khi chọn deadlock victim, nhưng lock wait timeout mặc định thường chỉ rollback statement gây timeout trừ khi cấu hình thay đổi. SQL Server lock timeout không đồng nghĩa mọi transaction tự động rollback. Ứng dụng phải kết thúc transaction cũ đúng cách trước khi retry.

## 10. Chính sách retry có giới hạn và backoff

Một retry loop nên có số lần thử tối đa và thời gian chờ tăng dần để các request không cùng retry liên tục.

Công thức minh họa:

\[
delay = \min(maxDelay,\ baseDelay \times 2^{attempt-1})
\]

Thêm jitter ngẫu nhiên:

\[
actualDelay = random(0, delay)
\]

Ví dụ:

| Lần thử | Thời gian chờ tối đa |
|---:|---:|
| 1 | 40 ms |
| 2 | 80 ms |
| 3 | 160 ms |
| 4 | 320 ms |

Đây chỉ là giá trị minh họa. Hãy chọn theo latency, deadline request, tỷ lệ contention và giới hạn hệ thống.

Quy trình retry:

1. Bắt lỗi đã được phân loại là retryable.
2. Rollback hoặc đóng transaction cũ để giải phóng khóa.
3. Chờ backoff có jitter bên ngoài transaction.
4. Bắt đầu transaction mới trên connection hợp lệ.
5. Dùng lại đúng idempotency key của request.
6. Đọc lại transfer hiện tại và account balances.
7. Khóa account theo cùng thứ tự.
8. Kiểm tra lại toàn bộ điều kiện.
9. Commit hoặc trả kết quả nghiệp vụ.

Không sleep khi vẫn giữ transaction và row locks. Không retry vô hạn. Khi hết số lần thử, trả lỗi tạm thời để caller có thể thử lại sau với cùng idempotency key.

### 10.1. Pseudocode tầng service

~~~java
public TransferResult transfer(TransferCommand command) {
    int maxAttempts = 4;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionRunner.execute(status -> {
                // Đăng ký hoặc đọc lại idempotency key trong transaction.
                TransferRequest request =
                    transferRepository.beginOrFind(command);

                if (request.isExisting()) {
                    return request.resultFor(command);
                }

                long firstId = Math.min(
                    command.sourceAccountId(),
                    command.destinationAccountId()
                );
                long secondId = Math.max(
                    command.sourceAccountId(),
                    command.destinationAccountId()
                );

                // Cả hai truy vấn dùng cùng transaction/connection.
                Account first = accountRepository.lockById(firstId);
                Account second = accountRepository.lockById(secondId);

                Account source = command.sourceAccountId() == firstId
                    ? first : second;
                Account destination = command.destinationAccountId() == firstId
                    ? first : second;

                validateAccounts(source, destination, command);

                if (source.balance().compareTo(command.amount()) < 0) {
                    transferRepository.markRejected(
                        request.id(), "INSUFFICIENT_FUNDS"
                    );
                    return TransferResult.rejected(
                        request.id(), "INSUFFICIENT_FUNDS"
                    );
                }

                accountRepository.debitConditionally(
                    source.id(), command.amount()
                );
                accountRepository.creditConditionally(
                    destination.id(), command.amount()
                );

                ledgerRepository.insertPair(request.id(), command);
                transferRepository.markCompleted(request.id());
                outboxRepository.insertTransferCompleted(request.id());

                return TransferResult.completed(request.id());
            });
        } catch (RuntimeException error) {
            if (!isRetryableConcurrencyError(error)
                    || attempt == maxAttempts) {
                throw error;
            }

            sleepWithExponentialBackoffAndJitter(attempt);
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Đây là pseudocode, không phải một implementation hoàn chỉnh gắn với một framework cụ thể. transactionRunner phải bảo đảm mỗi lần execute tạo một transaction vật lý mới và rollback transaction cũ trước khi exception được xử lý ở vòng lặp. Các repository phải dùng cùng connection được transaction manager quản lý.

Nếu framework tự retry transaction callback, không bọc thêm một retry loop khác mà không hiểu thứ tự của hai cơ chế. Tránh retry lồng nhau vì số lần thử có thể nhân lên và làm tải tăng đột biến.

## 11. Kết quả COMMIT không xác định và idempotency

Một tình huống khó là client gửi COMMIT nhưng kết nối bị ngắt trước khi nhận phản hồi.

~~~text
Ứng dụng                         Database
---------                         --------
Gửi COMMIT
                                  Commit transfer thành công
                                  Balance và ledger đã lưu
Kết nối bị ngắt
Không nhận ACK
Ứng dụng thấy timeout
~~~

Client không biết transaction đã commit hay chưa. Timeout không chứng minh rollback.

Cách phục hồi:

1. Giữ nguyên idempotency key của yêu cầu ban đầu.
2. Kết nối lại database.
3. Tìm transfer theo idempotency key.
4. Nếu status COMPLETED, trả lại kết quả đã lưu.
5. Nếu status REJECTED, trả lại kết quả từ chối đã lưu.
6. Nếu không tìm thấy record vì transaction trước rollback, có thể chạy lại cùng key.
7. Nếu request đang ở trạng thái trung gian do một quy trình nhiều bước, tiếp tục theo state machine đã thiết kế.

Unique idempotency key là lớp bảo vệ để client có thể hỏi lại kết quả mà không tạo thêm một lần chuyển tiền. Không tạo key mới chỉ vì lần gọi trước timeout.

## 12. Side effect bên ngoài: dùng Transactional Outbox

Không gửi email, SMS, webhook hoặc message broker ngay trong transaction đang khóa hai tài khoản. Một cuộc gọi mạng có thể chậm hoặc timeout, làm transaction giữ khóa lâu hơn.

Thay vào đó, ghi một outbox event trong cùng transaction với transfer:

~~~text
Database transaction
  Lock accounts
  Debit source
  Credit destination
  Insert ledger entries
  Mark transfer COMPLETED
  Insert Outbox event
  COMMIT
          |
          v
Outbox publisher
  Đọc event đã commit
  Gửi message
  Đánh dấu đã gửi
          |
          v
Consumer
  Deduplicate theo EventId
  Xử lý thông báo hoặc nghiệp vụ phụ
~~~

Nếu publisher gửi message thành công nhưng bị dừng trước khi đánh dấu event đã gửi, event có thể được phát lại. Consumer cần idempotent theo EventId.

Outbox bảo đảm ý định phát event được commit cùng thay đổi tài khoản. Nó thường cung cấp giao ít nhất một lần, không tự bảo đảm consumer chỉ nhận đúng một lần.

## 13. Kiểm thử deadlock và thứ tự khóa bằng hai session

Có thể tái hiện deadlock bằng hai connection và hai tài khoản. Thí nghiệm dưới đây dùng SQL Server. Chuẩn bị hai account có balance đủ lớn và không dùng chung với dữ liệu thật.

### 13.1. Lịch sai: mỗi transaction khóa nguồn trước

Session A:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 20;

COMMIT TRANSACTION;
~~~

Session B chạy gần như đồng thời:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 20;

WAITFOR DELAY '00:00:05';

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 10;

COMMIT TRANSACTION;
~~~

A giữ account 10 rồi yêu cầu 20. B giữ account 20 rồi yêu cầu 10. Nếu hai câu SELECT đầu hoàn tất trước khi hai câu thứ hai chạy, database có thể phát hiện deadlock và chọn một transaction làm victim. Session victim nhận lỗi deadlock; transaction của nó phải được xử lý theo trạng thái rollback của SQL Server.

Thời gian WAITFOR chỉ để đồng bộ thí nghiệm. Thứ tự chính xác phụ thuộc lịch scheduler; nếu không tái hiện, chạy lại và điều chỉnh khoảng chờ.

### 13.2. Lịch đúng: cả hai khóa account 10 rồi 20

Session A:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 20;

COMMIT TRANSACTION;
~~~

Session B, dù request nghiệp vụ là chuyển 20 → 10, vẫn khóa theo ID tăng dần:

~~~sql
BEGIN TRANSACTION;

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 10;

WAITFOR DELAY '00:00:05';

SELECT AccountId, Balance
FROM dbo.Account WITH (UPDLOCK, HOLDLOCK)
WHERE AccountId = 20;

COMMIT TRANSACTION;
~~~

Một session lấy khóa account 10 trước. Session còn lại chờ tại account 10 và chưa giữ account 20. Khi session đầu commit, session chờ tiếp tục lấy 10 rồi 20. Lịch này không tạo chu trình chờ ngược chiều giữa hai account.

Thứ tự khóa thống nhất làm giảm deadlock do cặp account, nhưng không loại bỏ mọi deadlock có thể xuất phát từ trigger, index, foreign key, ledger hoặc tài nguyên khác.

## 14. Những điểm cần bảo vệ ngoài thứ tự khóa

### 14.1. Không khóa rồi gọi dịch vụ ngoài

Sau khi khóa account, chỉ làm các thao tác database cần thiết. Không gọi API, gửi message trực tiếp hoặc chờ người dùng. Nếu cần ghi nhận thông báo, dùng Outbox.

### 14.2. Khóa theo khóa chính có index

Truy vấn khóa account bằng primary key để giới hạn phạm vi tìm kiếm. Nếu thiếu index phù hợp, DBMS có thể quét nhiều dòng và khóa rộng hơn dự kiến, làm tăng contention.

### 14.3. Mọi luồng cập nhật balance phải tuân thủ cùng giao thức

Nếu chuyển tiền khóa account theo ID tăng dần nhưng một luồng điều chỉnh số dư khóa theo thứ tự khác, deadlock vẫn có thể xảy ra. Quy tắc cần được chia sẻ ở repository, stored procedure hoặc tầng truy cập dữ liệu chung.

### 14.4. Kiểm tra số dòng cập nhật

Sau mỗi UPDATE có điều kiện, xác nhận đúng một dòng bị ảnh hưởng. Nếu không, rollback hoặc ghi kết quả REJECTED theo chính sách. Không tiếp tục tạo ledger entry khi debit hoặc credit không thành công.

### 14.5. Không cho phép sửa/xóa ledger tùy tiện

Ledger nên bất biến. Nếu cần hoàn tiền hoặc điều chỉnh, tạo transfer mới hoặc bút toán đảo có tham chiếu đến giao dịch gốc. Không sửa một entry cũ để làm lịch sử mất dấu.

## 15. Chẩn đoán deadlock và contention

Ghi log các trường:

- transfer_id và idempotency key đã được hash hoặc bảo vệ.
- source/destination account ID.
- attempt number.
- thời gian bắt đầu và kết thúc transaction.
- số lần retry và mã lỗi database.
- thời gian chờ khóa.
- kết quả cuối cùng COMPLETED/REJECTED/UNKNOWN.
- correlation ID của request.

Không ghi dữ liệu nhạy cảm như thông tin xác thực hoặc toàn bộ payload tài chính nếu không cần thiết.

Công cụ theo DBMS:

| DBMS | Cách điều tra |
|---|---|
| PostgreSQL | Log SQLSTATE 40P01/40001, pg_stat_activity, pg_locks, pg_blocking_pids và deadlock log |
| SQL Server | Extended Events deadlock graph, error 1205, sys.dm_tran_locks, sys.dm_exec_requests |
| MySQL InnoDB | SHOW ENGINE INNODB STATUS, Performance Schema data_locks/data_lock_waits |
| Oracle | Alert log, deadlock trace, ORA-00060 và session wait |

Deadlock graph cho biết tài nguyên và thứ tự chờ thực tế. Đừng chỉ nhìn mã lỗi rồi tăng retry. Nếu cùng một cặp bảng hoặc cùng một luồng liên tục xuất hiện, cần sửa thứ tự truy cập hoặc giảm thời gian giữ khóa.

## 16. Đối soát sau chuyển tiền

Một giao dịch thành công phải có hai ledger entries cân bằng:

~~~sql
SELECT
    transfer_id,
    currency,
    SUM(amount) AS net_amount,
    COUNT(*) AS entry_count
FROM ledger_entry
GROUP BY transfer_id, currency
HAVING COUNT(*) <> 2
    OR SUM(amount) <> 0;
~~~

Với chuyển tiền cùng currency và không có phí, truy vấn trên phải không trả dòng nào cho các transfer hoàn tất. Nếu có phí hoặc FX, quy tắc cân bằng phải tính cả tài khoản phí, tài khoản clearing và tỷ giá tương ứng.

Tìm transfer COMPLETED nhưng thiếu bút toán:

~~~sql
SELECT t.transfer_id, t.status
FROM transfer AS t
LEFT JOIN ledger_entry AS l
    ON l.transfer_id = t.transfer_id
WHERE t.status = 'COMPLETED'
GROUP BY t.transfer_id, t.status
HAVING COUNT(l.ledger_entry_id) <> 2;
~~~

Kiểm tra idempotency key trùng nếu schema không có UNIQUE constraint hoặc khi đối soát dữ liệu legacy:

~~~sql
SELECT idempotency_key, COUNT(*)
FROM transfer
GROUP BY idempotency_key
HAVING COUNT(*) > 1;
~~~

Đối chiếu balance với ledger cần xác định số dư đầu kỳ và tất cả loại bút toán được tính. Không thể chỉ SUM ledger rồi so với balance nếu hệ thống đã có số dư mở đầu hoặc dữ liệu lịch sử chưa được nhập đầy đủ.

## 17. Checklist thiết kế và kiểm thử

Khi triển khai chuyển tiền, hãy lần lượt xác nhận:

1. **Invariant:** amount dương, currency phù hợp, tài khoản hoạt động, source đủ tiền và balance không âm.
2. **Schema:** dùng NUMERIC/DECIMAL cho tiền, primary key cho account và unique idempotency key.
3. **Lock order:** mọi transfer khóa account ID tăng dần, bất kể chiều chuyển.
4. **Transaction boundary:** đăng ký request, khóa account, debit, credit, ledger, status và outbox cùng một transaction.
5. **Atomicity:** lỗi ở bất kỳ bước ghi nào đều rollback toàn bộ thay đổi tài chính.
6. **Idempotency:** cùng key và cùng payload trả lại kết quả cũ; cùng key nhưng payload khác bị từ chối.
7. **Retry:** chỉ retry lỗi concurrency tạm thời; mỗi lần retry mở transaction mới và đọc lại dữ liệu.
8. **Backoff:** có giới hạn số lần thử, jitter và deadline.
9. **Ambiguous commit:** timeout khi COMMIT được giải quyết bằng cùng idempotency key.
10. **External side effect:** phát event qua Outbox; consumer deduplicate.
11. **Observability:** ghi attempt, lock wait, deadlock, SQLSTATE/error code và kết quả.
12. **Reconciliation:** kiểm tra hai ledger entries, tổng bằng 0 và balance khớp mô hình sổ cái.

### 17.1. Ma trận test tối thiểu

| Kịch bản | Kết quả mong đợi |
|---|---|
| Chuyển A → B khi đủ tiền | Debit A, credit B và hai ledger entries cùng commit |
| Chuyển A → B khi thiếu tiền | REJECTED; balance không đổi; không có ledger entry |
| Hai request cùng idempotency key | Chỉ một transfer được thực hiện; request còn lại nhận cùng kết quả |
| Cùng key nhưng amount khác | Idempotency conflict; không chuyển tiền lần thứ hai |
| A → B đồng thời B → A | Khóa theo account ID tăng dần; một request có thể chờ nhưng deadlock do cặp account được tránh |
| Deadlock do tài nguyên khác | Một transaction bị hủy; retry toàn bộ với cùng key |
| Lỗi sau debit nhưng trước credit | Rollback; cả hai balance và ledger giữ nguyên |
| Mất kết nối sau COMMIT | Tra cứu cùng key; không tạo transfer thứ hai |
| Outbox publisher gửi trùng | Consumer deduplicate theo EventId |
| Nhiều request cùng một tài khoản nguồn | Số dư không âm; throughput có thể bị giới hạn bởi hot account |

## 18. Những nguyên tắc cần ghi nhớ

- Chuyển tiền là một đơn vị nghiệp vụ nguyên tử: debit, credit, ledger và trạng thái transfer phải cùng commit hoặc cùng rollback.
- Dùng NUMERIC/DECIMAL cho số tiền; không dùng FLOAT/REAL.
- Hai transaction chuyển tiền ngược chiều có thể deadlock nếu mỗi transaction khóa tài khoản nguồn trước.
- Khóa mọi account theo cùng thứ tự xác định, thường là account_id tăng dần.
- Mọi luồng cập nhật tài khoản phải tuân thủ cùng quy tắc thứ tự khóa, kể cả hoàn tiền, phí và batch job.
- Thứ tự khóa làm giảm deadlock nhưng không loại bỏ deadlock do trigger, index hoặc tài nguyên khác.
- Dùng điều kiện balance >= amount trong UPDATE để bảo vệ invariant ở database và kiểm tra đúng một dòng được cập nhật.
- Ghi hai ledger entries trong cùng transaction; không gửi email hoặc gọi dịch vụ ngoài khi đang giữ khóa.
- Idempotency key ổn định giúp request retry không tạo chuyển tiền trùng; cùng key với payload khác phải bị từ chối.
- Deadlock và serialization failure yêu cầu rollback rồi thực thi lại toàn bộ transaction trên dữ liệu đọc mới.
- Dùng retry có giới hạn, exponential backoff và jitter; không retry lỗi nghiệp vụ như insufficient funds.
- Timeout trong lúc COMMIT có thể để lại kết quả chưa xác định; tra cứu bằng cùng idempotency key trước khi chạy lại.
- Dùng Transactional Outbox và consumer idempotent cho thông báo hoặc side effect sau commit.
- Đối soát ledger và balance sau test để phát hiện thiếu bút toán, duplicate hoặc counter drift.

Một giao dịch chuyển tiền an toàn không dựa vào việc ứng dụng hy vọng hai câu UPDATE sẽ chạy đúng thứ tự. Database phải khóa hai tài khoản theo một quy tắc thống nhất, ghi mọi thay đổi trong cùng transaction và lưu một định danh request có thể dùng lại. Khi transaction bị hủy, ứng dụng bắt đầu lại từ dữ liệu mới với cùng idempotency key. Nhờ đó, hệ thống vừa giảm deadlock do khóa ngược chiều vừa có thể phục hồi khỏi xung đột mà không chuyển tiền hai lần.

