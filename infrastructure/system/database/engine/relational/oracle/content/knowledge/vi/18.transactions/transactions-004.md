# SAVEPOINT và hoàn tác một phần giao dịch trong Oracle

Trong một transaction, có lúc một số bước đã thực hiện đúng nhưng một bước tiếp theo lại không đạt yêu cầu. Ta có thể muốn hủy riêng phần công việc vừa làm, giữ nguyên các thay đổi hợp lệ trước đó và tiếp tục transaction. Oracle cung cấp **SAVEPOINT** và **ROLLBACK TO SAVEPOINT** cho tình huống này.

SAVEPOINT đánh dấu một vị trí trong transaction. Khi chạy ROLLBACK TO, Oracle hoàn tác các thay đổi được thực hiện sau vị trí đó, trong khi transaction vẫn tiếp tục mở. Đây là cách hoàn tác một phần giao dịch, khác với ROLLBACK toàn bộ transaction.

Bài học dùng Oracle Database để giải thích ranh giới transaction, cú pháp savepoint, thứ tự nhiều savepoint, ví dụ chuyển tiền nhiều bước, xử lý exception trong PL/SQL, tác động của DDL và autocommit, cùng những giới hạn cần nhớ khi dùng trong ứng dụng.

## 1. Transaction và nhu cầu hoàn tác một phần

Một transaction là một đơn vị công việc logic gồm một hoặc nhiều câu lệnh DML. Các thay đổi trong transaction được xác nhận bằng COMMIT hoặc hủy bằng ROLLBACK.

Ví dụ, một quy trình đặt hàng có thể gồm:

1. Tạo bản ghi đơn hàng.
2. Trừ số lượng tồn kho.
3. Ghi nhận thanh toán.
4. Ghi lịch sử xử lý.

Nếu bước 1 và 2 hợp lệ nhưng bước 3 không được chấp nhận, ứng dụng có thể cần quay lại trước bước thanh toán, giữ các thay đổi trước đó để thử một phương án khác. SAVEPOINT hỗ trợ đánh dấu vị trí cần quay lại.

~~~text
BEGIN TRANSACTION
       |
       v
    DML bước 1
       |
       v
  SAVEPOINT sp_a
       |
       v
    DML bước 2
       |
       v
  SAVEPOINT sp_b
       |
       v
    DML bước 3  ----> không hợp lệ
       |
       v
ROLLBACK TO sp_b
       |
       v
Giữ bước 1 và 2, hủy phần sau sp_b
       |
       v
Tiếp tục DML hoặc COMMIT
~~~

SAVEPOINT không tạo một transaction độc lập. Nó chỉ đánh dấu một điểm bên trong transaction hiện tại.

## 2. Cú pháp SAVEPOINT và ROLLBACK TO

### 2.1. Tạo savepoint

~~~sql
SAVEPOINT savepoint_name;
~~~

Ví dụ:

~~~sql
SAVEPOINT before_update;
~~~

Lệnh trên đặt một mốc có tên BEFORE_UPDATE tại vị trí hiện tại của transaction.

### 2.2. Hoàn tác về savepoint

~~~sql
ROLLBACK TO SAVEPOINT savepoint_name;
~~~

Oracle cũng chấp nhận dạng ngắn:

~~~sql
ROLLBACK TO savepoint_name;
~~~

Ví dụ:

~~~sql
ROLLBACK TO SAVEPOINT before_update;
~~~

Oracle hoàn tác các thay đổi sau BEFORE_UPDATE. Transaction vẫn mở và có thể tiếp tục thực hiện DML hoặc kết thúc bằng COMMIT/ROLLBACK.

### 2.3. Kết thúc toàn bộ transaction

~~~sql
COMMIT;
~~~

COMMIT xác nhận mọi thay đổi còn lại trong transaction và xóa các savepoint của transaction đó.

~~~sql
ROLLBACK;
~~~

ROLLBACK không chỉ quay về một savepoint; nó hủy toàn bộ thay đổi chưa commit trong transaction hiện tại và kết thúc transaction.

| Lệnh | Phạm vi hoàn tác/xác nhận | Transaction sau lệnh |
|---|---|---|
| SAVEPOINT name | Không hoàn tác; chỉ đánh dấu vị trí | Vẫn mở |
| ROLLBACK TO name | Hủy thay đổi sau savepoint | Vẫn mở |
| ROLLBACK | Hủy mọi thay đổi chưa commit | Kết thúc |
| COMMIT | Xác nhận mọi thay đổi còn lại | Kết thúc |

## 3. SAVEPOINT không phải nested transaction

Một transaction có thể có nhiều savepoint, nhưng chúng không phải các transaction con độc lập.

- Không thể COMMIT riêng phần trước savepoint trong khi giữ phần sau chưa commit.
- Không thể rollback một savepoint sau khi transaction đã COMMIT.
- ROLLBACK TO không tạo một transaction mới.
- Tất cả savepoint thuộc cùng transaction và cùng session.

Hãy hình dung savepoint như các dấu mốc trên một đường đi. ROLLBACK TO quay về một dấu mốc, còn COMMIT hoặc ROLLBACK kết thúc toàn bộ đường đi đó.

## 4. Chuẩn bị dữ liệu thực hành

Ta dùng hai bảng:

- LAB_TX_ACCOUNT: tài khoản và số dư.
- LAB_TX_TRANSFER: lịch sử chuyển tiền giữa hai tài khoản.

Một giao dịch chuyển tiền gồm cập nhật số dư tài khoản gửi, cập nhật số dư tài khoản nhận và ghi lịch sử. Sau đó ta mô phỏng một lần chuyển tiền tiếp theo bị hủy bằng ROLLBACK TO.

### 4.1. Tạo bảng tài khoản

Chạy trong schema lab thuộc PDB thực hành. Nếu bảng cùng tên đã tồn tại, hãy dùng schema hoặc tên bảng khác; không ghi đè dữ liệu đang được sử dụng.

~~~sql
CREATE TABLE lab_tx_account (
    account_id   NUMBER(6) PRIMARY KEY,
    holder_name  VARCHAR2(60 CHAR) NOT NULL,
    balance      NUMBER(14,2) NOT NULL,
    CONSTRAINT ck_lab_tx_account_balance
      CHECK (balance >= 0)
);
~~~

### 4.2. Tạo bảng lịch sử chuyển tiền

~~~sql
CREATE TABLE lab_tx_transfer (
    transfer_id       NUMBER(8) PRIMARY KEY,
    from_account_id   NUMBER(6) NOT NULL,
    to_account_id     NUMBER(6) NOT NULL,
    transfer_amount   NUMBER(14,2) NOT NULL,
    created_at        DATE NOT NULL,
    CONSTRAINT fk_lab_tx_transfer_from
      FOREIGN KEY (from_account_id)
      REFERENCES lab_tx_account (account_id),
    CONSTRAINT fk_lab_tx_transfer_to
      FOREIGN KEY (to_account_id)
      REFERENCES lab_tx_account (account_id),
    CONSTRAINT ck_lab_tx_transfer_amount
      CHECK (transfer_amount > 0),
    CONSTRAINT ck_lab_tx_transfer_accounts
      CHECK (from_account_id <> to_account_id)
);
~~~

### 4.3. Chèn dữ liệu ban đầu

~~~sql
INSERT INTO lab_tx_account VALUES (1, 'An',   1000);
INSERT INTO lab_tx_account VALUES (2, 'Binh',  500);
INSERT INTO lab_tx_account VALUES (3, 'Chi',   200);
COMMIT;
~~~

Số dư ban đầu:

| ACCOUNT_ID | HOLDER_NAME | BALANCE |
|---:|---|---:|
| 1 | An | 1000 |
| 2 | Binh | 500 |
| 3 | Chi | 200 |

Tổng số dư là 1700. Các ví dụ tiếp theo giả định dữ liệu đã được khởi tạo đúng như bảng này.

## 5. Ví dụ chính: giữ giao dịch thứ nhất, hủy giao dịch thứ hai

Giả sử ta cần:

1. Chuyển 200 từ An sang Binh.
2. Sau đó thử chuyển tiếp 100 từ Binh sang Chi.
3. Phát hiện lần chuyển thứ hai không được duyệt, nên chỉ hủy lần thứ hai.
4. Giữ lần chuyển đầu tiên và COMMIT.

### 5.1. Đặt savepoint trước lần chuyển thứ nhất

~~~sql
SAVEPOINT before_first_transfer;
~~~

Savepoint này đánh dấu trạng thái trước khi bắt đầu các thay đổi chuyển tiền.

### 5.2. Thực hiện lần chuyển thứ nhất

~~~sql
UPDATE lab_tx_account
SET balance = balance - 200
WHERE account_id = 1
  AND balance >= 200;

UPDATE lab_tx_account
SET balance = balance + 200
WHERE account_id = 2;

INSERT INTO lab_tx_transfer (
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
)
VALUES (
    5001,
    1,
    2,
    200,
    DATE '2026-11-14'
);
~~~

Sau ba câu lệnh, số dư là:

| Tài khoản | Số dư |
|---|---:|
| An | 800 |
| Binh | 700 |
| Chi | 200 |

Lịch sử có transfer 5001. Các thay đổi này vẫn chưa được COMMIT; chúng chỉ đang nằm trong transaction hiện tại.

### 5.3. Đánh dấu sau lần chuyển thứ nhất

~~~sql
SAVEPOINT after_first_transfer;
~~~

Đây là mốc ta muốn giữ nếu lần chuyển thứ hai thất bại.

### 5.4. Thử lần chuyển thứ hai

~~~sql
UPDATE lab_tx_account
SET balance = balance - 100
WHERE account_id = 2
  AND balance >= 100;

UPDATE lab_tx_account
SET balance = balance + 100
WHERE account_id = 3;

INSERT INTO lab_tx_transfer (
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
)
VALUES (
    5002,
    2,
    3,
    100,
    DATE '2026-11-14'
);
~~~

Ngay sau các câu lệnh này, số dư tạm thời là:

| Tài khoản | Số dư tạm thời |
|---|---:|
| An | 800 |
| Binh | 600 |
| Chi | 300 |

Lịch sử có cả transfer 5001 và 5002. Giả sử ở bước kiểm tra nghiệp vụ, lần chuyển 5002 không được duyệt.

### 5.5. Hoàn tác riêng lần chuyển thứ hai

~~~sql
ROLLBACK TO SAVEPOINT after_first_transfer;
~~~

Oracle hủy các thay đổi được thực hiện sau savepoint AFTER_FIRST_TRANSFER:

- Hoàn lại 100 đã trừ khỏi Binh.
- Hoàn lại 100 đã cộng cho Chi.
- Xóa bản ghi lịch sử transfer 5002 được chèn sau savepoint.

Những thay đổi của transfer 5001 trước savepoint vẫn còn trong transaction.

Kiểm tra:

~~~sql
SELECT account_id, holder_name, balance
FROM lab_tx_account
ORDER BY account_id;

SELECT transfer_id, from_account_id, to_account_id, transfer_amount
FROM lab_tx_transfer
ORDER BY transfer_id;
~~~

Kết quả mong đợi:

| ACCOUNT_ID | HOLDER_NAME | BALANCE |
|---:|---|---:|
| 1 | An | 800 |
| 2 | Binh | 700 |
| 3 | Chi | 200 |

| TRANSFER_ID | FROM_ACCOUNT_ID | TO_ACCOUNT_ID | TRANSFER_AMOUNT |
|---:|---:|---:|---:|
| 5001 | 1 | 2 | 200 |

### 5.6. COMMIT phần còn lại

Nếu lần chuyển đầu tiên hợp lệ và kết quả kiểm tra đúng:

~~~sql
COMMIT;
~~~

Lúc này thay đổi của transfer 5001 trở thành dữ liệu đã xác nhận. Không thể dùng ROLLBACK TO để quay lại BEFORE_FIRST_TRANSFER sau khi COMMIT.

## 6. Nếu muốn hủy toàn bộ thay đổi thì dùng ROLLBACK

Trong ví dụ trước, nếu sau khi hoàn tác transfer 5002 ta phát hiện transfer 5001 cũng sai, có thể quay về savepoint đầu:

~~~sql
ROLLBACK TO SAVEPOINT before_first_transfer;
~~~

Lệnh này hủy cả transfer 5001 và mọi thay đổi sau BEFORE_FIRST_TRANSFER, miễn là transaction chưa kết thúc.

Nếu muốn hủy toàn bộ transaction, không cần quay về savepoint:

~~~sql
ROLLBACK;
~~~

So sánh:

| Tình huống | Lệnh | Kết quả |
|---|---|---|
| Chỉ hủy lần chuyển thứ hai | ROLLBACK TO after_first_transfer | Giữ lần chuyển thứ nhất |
| Hủy mọi thay đổi từ đầu transaction | ROLLBACK TO before_first_transfer | Quay về mốc đầu đã đánh dấu, transaction vẫn mở |
| Hủy toàn bộ transaction hiện tại | ROLLBACK | Quay về trạng thái trước transaction và kết thúc transaction |
| Xác nhận phần còn lại | COMMIT | Ghi nhận tất cả thay đổi chưa bị hoàn tác |

Nếu chạy lại ví dụ, cần khôi phục dữ liệu lab về trạng thái ban đầu theo cách phù hợp trước khi dùng lại các ID transfer đã tồn tại.

## 7. Nhiều savepoint trong một transaction

Một transaction có thể đánh dấu nhiều vị trí:

~~~sql
SAVEPOINT step_0;

UPDATE lab_tx_account
SET balance = balance - 50
WHERE account_id = 1;

SAVEPOINT step_1;

UPDATE lab_tx_account
SET balance = balance + 50
WHERE account_id = 2;

SAVEPOINT step_2;

UPDATE lab_tx_account
SET balance = balance - 25
WHERE account_id = 2;

SAVEPOINT step_3;
~~~

Tại thời điểm này, các thay đổi theo thứ tự là:

| Mốc | Thay đổi đã thực hiện |
|---|---|
| STEP_0 | Chưa có thay đổi |
| Sau STEP_0 | Trừ 50 ở tài khoản 1 |
| STEP_1 | Đánh dấu sau lần trừ 50 |
| Sau STEP_1 | Cộng 50 ở tài khoản 2 |
| STEP_2 | Đánh dấu sau lần cộng 50 |
| Sau STEP_2 | Trừ 25 ở tài khoản 2 |
| STEP_3 | Đánh dấu sau lần trừ 25 |

Nếu chạy:

~~~sql
ROLLBACK TO step_1;
~~~

Oracle hoàn tác các thay đổi sau STEP_1:

- Hủy khoản cộng 50 vào tài khoản 2.
- Hủy khoản trừ 25 khỏi tài khoản 2.
- Các savepoint được tạo sau STEP_1 (STEP_2 và STEP_3) bị xóa.
- Thay đổi trừ 50 khỏi tài khoản 1 trước STEP_1 vẫn còn.
- STEP_0 và STEP_1 vẫn là các mốc có thể sử dụng trong transaction.

Sau đó có thể tiếp tục DML và COMMIT, hoặc tiếp tục ROLLBACK TO STEP_0 để hủy cả khoản trừ 50.

### 7.1. Savepoint sau mốc rollback bị loại bỏ

Khi rollback về một savepoint, những savepoint được tạo **sau** mốc đó không còn hợp lệ. Ví dụ sau:

~~~sql
ROLLBACK TO step_1;
ROLLBACK TO step_3;
~~~

lệnh thứ hai không thể dùng STEP_3 vì savepoint này đã bị xóa khi rollback về STEP_1. Oracle có thể báo ORA-01086 cho savepoint không còn tồn tại hoặc không hợp lệ.

### 7.2. Savepoint đích vẫn còn sau ROLLBACK TO

Savepoint mà ta rollback về vẫn còn hiệu lực. Ta có thể thực hiện thêm DML rồi lại rollback về chính mốc đó:

~~~sql
SAVEPOINT checkpoint_a;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 3;

ROLLBACK TO checkpoint_a;

UPDATE lab_tx_account
SET balance = balance + 20
WHERE account_id = 3;

ROLLBACK TO checkpoint_a;
~~~

Cả hai lần tăng số dư đều bị hoàn tác vì đều diễn ra sau CHECKPOINT_A. Transaction vẫn mở sau mỗi ROLLBACK TO.

## 8. Đặt lại savepoint cùng tên

Nếu tạo một savepoint mới có cùng tên với savepoint cũ trong cùng transaction, Oracle di chuyển savepoint đó tới vị trí mới; mốc cũ cùng tên không còn được giữ.

~~~sql
SAVEPOINT progress;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT progress;

UPDATE lab_tx_account
SET balance = balance + 20
WHERE account_id = 1;

ROLLBACK TO progress;
~~~

Lệnh ROLLBACK TO PROGRESS quay về lần tạo PROGRESS gần nhất, nên chỉ hủy phần tăng 20. Phần tăng 10 nằm trước savepoint mới vẫn còn.

Vì vậy, hãy đặt tên savepoint có ý nghĩa và tránh vô tình dùng lại tên đã được một procedure hoặc phần khác của ứng dụng sử dụng.

## 9. SAVEPOINT trong PL/SQL và xử lý exception

Một khối PL/SQL có thể đặt savepoint và rollback trong exception handler. Cách này hữu ích khi một thủ tục thực hiện nhiều DML nhưng chỉ muốn hủy phần công việc của chính nó nếu gặp lỗi.

Ví dụ:

~~~sql
DECLARE
    v_rows PLS_INTEGER;
BEGIN
    SAVEPOINT before_account_change;

    UPDATE lab_tx_account
    SET balance = balance - 50
    WHERE account_id = 1
      AND balance >= 50;

    v_rows := SQL%ROWCOUNT;
    IF v_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Account 1 does not exist or has insufficient balance'
        );
    END IF;

    UPDATE lab_tx_account
    SET balance = balance + 50
    WHERE account_id = 2;

    v_rows := SQL%ROWCOUNT;
    IF v_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Destination account does not exist'
        );
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_account_change;
        RAISE;
END;
/
~~~

Luồng xử lý:

1. Đánh dấu BEFORE_ACCOUNT_CHANGE.
2. Trừ tiền tài khoản nguồn và kiểm tra số dòng được cập nhật.
3. Cộng tiền vào tài khoản nhận và kiểm tra số dòng.
4. Nếu bất kỳ bước nào phát sinh lỗi, exception handler rollback về savepoint.
5. RAISE chuyển lỗi về caller để tầng gọi quyết định xử lý tiếp.

Khối PL/SQL không tự COMMIT khi chạy hết. Transaction vẫn thuộc session gọi và caller có thể tiếp tục DML, COMMIT hoặc ROLLBACK.

### 9.1. Vì sao không COMMIT trong procedure dùng chung transaction?

Một procedure thường được gọi trong một transaction lớn hơn do ứng dụng quản lý. Nếu procedure tự COMMIT, nó sẽ xác nhận cả những thay đổi trước đó của caller trong cùng transaction, không chỉ phần DML của procedure.

Mẫu savepoint giúp procedure có thể hoàn tác phần việc của nó mà vẫn giữ các thay đổi hợp lệ trước khi procedure được gọi. Tuy nhiên, cần thống nhất rõ với caller về quyền sở hữu transaction và cách xử lý lỗi.

### 9.2. Tên savepoint trong procedure không có phạm vi cục bộ

Savepoint thuộc transaction của session, không phải biến cục bộ của block PL/SQL. Nếu procedure tạo savepoint trùng tên với savepoint mà caller đã tạo, mốc cùng tên trước đó bị thay thế.

Ví dụ:

~~~sql
SAVEPOINT caller_checkpoint;

-- Một procedure bên dưới vô tình dùng lại tên caller_checkpoint:
SAVEPOINT caller_checkpoint;
~~~

Sau câu lệnh thứ hai, caller không còn quay lại được mốc cũ bằng tên CALLER_CHECKPOINT. Khi viết procedure, hãy chọn tên savepoint có tiền tố riêng để tránh xung đột với caller.

### 9.3. Trường hợp exception handler không rollback được

Nếu transaction đã bị kết thúc bởi COMMIT, ROLLBACK toàn bộ hoặc DDL gây implicit commit, savepoint có thể không còn tồn tại. Khi exception handler chạy:

~~~sql
ROLLBACK TO before_account_change;
~~~

có thể phát sinh lỗi ORA-01086. Vì vậy, một procedure dựa vào savepoint không nên tự ý kết thúc transaction hoặc chạy DDL giữa lúc thiết lập mốc và lúc xử lý lỗi.

## 10. Statement-level rollback khác transaction rollback

Oracle bảo đảm tính nguyên tử ở mức câu lệnh: nếu một câu DML thất bại, Oracle hoàn tác tác động của chính câu lệnh thất bại đó. Những câu lệnh DML trước đó trong transaction vẫn còn hiệu lực chưa commit.

Ví dụ, giả sử:

~~~sql
UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

UPDATE lab_tx_account
SET balance = -100
WHERE account_id = 2;
~~~

Câu UPDATE thứ hai vi phạm CHECK CONSTRAINT BALANCE >= 0 nên bị từ chối. Oracle rollback tác động của câu UPDATE thứ hai; câu UPDATE đầu tiên vẫn còn trong transaction.

Có thể kiểm tra:

~~~sql
SELECT account_id, balance
FROM lab_tx_account
ORDER BY account_id;
~~~

Nếu muốn hủy cả câu UPDATE đầu tiên, cần ROLLBACK toàn transaction hoặc ROLLBACK TO một savepoint được đặt trước câu UPDATE đầu tiên.

Đây là hai phạm vi khác nhau:

| Cơ chế | Phần được hoàn tác |
|---|---|
| Statement failure | Tác động của câu SQL thất bại |
| ROLLBACK TO savepoint | Tất cả thay đổi trong transaction sau savepoint |
| ROLLBACK | Tất cả thay đổi chưa commit trong transaction |

Không cần đặt savepoint trước mọi câu DML chỉ để bảo đảm một câu SQL lỗi không để lại nửa kết quả của chính nó; statement-level atomicity đã đảm nhiệm điều đó. Savepoint hữu ích khi muốn hủy nhiều câu lệnh đã chạy thành công như một nhóm.

## 11. DDL có thể làm mất savepoint

Trong Oracle, các câu lệnh DDL thông thường có implicit commit trước khi thực thi và commit sau khi DDL thực thi thành công. Điều này có hệ quả rất quan trọng:

~~~sql
SAVEPOINT before_ddl;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

CREATE TABLE lab_tx_demo (
    id NUMBER PRIMARY KEY
);

ROLLBACK TO before_ddl;
~~~

CREATE TABLE làm transaction trước đó được commit ngầm; savepoint BEFORE_DDL không còn tồn tại. Câu ROLLBACK TO sau đó không thể hoàn tác khoản UPDATE trước DDL và có thể báo ORA-01086.

Các lệnh như CREATE, ALTER, DROP, TRUNCATE là DDL; đừng đặt chúng giữa một chuỗi DML mà bạn dự định có thể rollback về savepoint.

### 11.1. Chuẩn bị schema trước transaction

Thứ tự phù hợp cho bài lab:

1. Tạo bảng bằng DDL.
2. Chèn dữ liệu ban đầu và COMMIT.
3. Bắt đầu transaction DML.
4. Đặt savepoint và thực hiện các thay đổi.
5. ROLLBACK TO, COMMIT hoặc ROLLBACK theo mục tiêu.

Không tạo bảng hoặc thay đổi constraint giữa các bước DML cần được hoàn tác cùng nhau.

## 12. SAVEPOINT và autocommit của công cụ

Một số SQL client hoặc cấu hình kết nối JDBC bật autocommit. Khi autocommit được bật, mỗi câu DML thành công có thể được commit tự động ngay sau khi thực thi.

Ví dụ nếu client tự commit sau từng câu:

~~~sql
SAVEPOINT before_change;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

ROLLBACK TO before_change;
~~~

Nếu UPDATE đã được autocommit, transaction chứa BEFORE_CHANGE đã kết thúc và savepoint bị xóa. ROLLBACK TO không thể hoàn tác thay đổi đã commit.

Khi thực hành SAVEPOINT:

- Dùng chế độ manual commit/autocommit OFF.
- Xác nhận client không tự commit sau từng câu DML.
- Không bấm nút Commit trước khi kiểm tra.
- Dùng một session nhất quán từ lúc SAVEPOINT đến lúc ROLLBACK TO.

Trong JDBC, ứng dụng thường gọi setAutoCommit(false), thực hiện các câu DML và chủ động gọi commit/rollback. Nếu ứng dụng dùng JDBC Savepoint API, đối tượng Savepoint được quản lý theo connection và transaction hiện tại; không dùng lại sau khi transaction kết thúc.

## 13. Savepoint gắn với session và transaction

Savepoint chỉ có hiệu lực trong transaction của session đã tạo nó:

- Session A tạo SAVEPOINT SP_A thì session B không thể rollback tới SP_A.
- COMMIT hoặc ROLLBACK toàn bộ kết thúc transaction và xóa savepoint.
- Mất kết nối hoặc transaction bị kết thúc thì không thể tiếp tục dùng savepoint cũ.
- Savepoint không phải dữ liệu được lưu bền vững trong bảng.

Trong ứng dụng connection pool, không được giả định một request sau sẽ nhận đúng connection còn giữ transaction của request trước. Hãy quản lý transaction trên cùng connection và không để connection trả về pool khi transaction còn dang dở.

## 14. Tác động của ROLLBACK TO lên khóa

Oracle sử dụng khóa để điều phối các thay đổi đồng thời. Khi rollback về savepoint:

- Các thay đổi dữ liệu sau savepoint được hoàn tác.
- Những savepoint được tạo sau mốc đó bị xóa.
- Oracle giải phóng các khóa bảng/hàng được lấy sau savepoint theo quy tắc rollback.
- Các khóa được lấy trước savepoint vẫn có thể được giữ cho đến khi transaction kết thúc.
- Transaction tiếp tục mở.

Vì vậy, ROLLBACK TO không đồng nghĩa với giải phóng mọi khóa của session. Nếu transaction đã cập nhật một dòng trước savepoint, khóa liên quan có thể vẫn được giữ sau khi rollback về một mốc được tạo muộn hơn.

Ví dụ:

~~~sql
UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

SAVEPOINT after_account_1;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 2;

ROLLBACK TO after_account_1;
~~~

Thay đổi tài khoản 2 bị hoàn tác; khóa phát sinh sau mốc được xử lý theo rollback. Thay đổi tài khoản 1 nằm trước savepoint vẫn còn và transaction chưa kết thúc.

Không giữ transaction mở lâu chỉ vì đã rollback một phần. Khi hoàn tất công việc, hãy COMMIT hoặc ROLLBACK toàn bộ để giải phóng tài nguyên transaction.

## 15. Những giới hạn và quy tắc cần nhớ

### 15.1. Không thể rollback về savepoint sau khi transaction kết thúc

~~~sql
SAVEPOINT before_commit;

UPDATE lab_tx_account
SET balance = balance + 10
WHERE account_id = 1;

COMMIT;

ROLLBACK TO before_commit;
~~~

Sau COMMIT, transaction đã kết thúc và savepoint bị xóa. Lệnh cuối không thể khôi phục trạng thái trước commit.

### 15.2. Không thể rollback tới savepoint không tồn tại

~~~sql
ROLLBACK TO missing_savepoint;
~~~

Nếu savepoint chưa từng được tạo trong transaction hiện tại, đã bị xóa bởi rollback về mốc trước, hoặc transaction đã kết thúc, Oracle thường báo:

~~~text
ORA-01086: savepoint 'MISSING_SAVEPOINT' never established
~~~

Kiểm tra đúng tên, đúng session và trạng thái transaction.

### 15.3. Oracle không dùng RELEASE SAVEPOINT như một số hệ quản trị khác

Không dùng:

~~~sql
RELEASE SAVEPOINT before_update;
~~~

Đây không phải cú pháp Oracle SQL để giải phóng savepoint. Các savepoint được quản lý bởi transaction: COMMIT/ROLLBACK toàn bộ sẽ xóa chúng; ROLLBACK TO một mốc sẽ loại các savepoint phía sau mốc đó; tạo lại cùng tên sẽ thay thế mốc cũ cùng tên.

### 15.4. Savepoint không có thời hạn tồn tại độc lập

Không có cách dùng savepoint sau khi transaction kết thúc, cũng không thể lưu một savepoint để sử dụng trong session khác. Nếu cần khôi phục dữ liệu sau COMMIT, phải dùng cơ chế khác như audit/history, backup, Flashback hoặc quy trình bù trừ nghiệp vụ phù hợp.

## 16. SAVEPOINT trong procedure và transaction do caller quản lý

Một quy ước thường dùng trong ứng dụng:

- Caller bắt đầu và kết thúc transaction.
- Procedure thực hiện một nhóm DML.
- Procedure đặt savepoint trước nhóm DML của mình.
- Nếu lỗi, procedure rollback về savepoint rồi ném lỗi lại.
- Caller quyết định tiếp tục, rollback thêm hoặc commit.

Mẫu:

~~~sql
CREATE OR REPLACE PROCEDURE lab_apply_adjustment (
    p_account_id IN NUMBER,
    p_delta      IN NUMBER
)
AS
BEGIN
    SAVEPOINT lab_apply_adjustment_sp;

    UPDATE lab_tx_account
    SET balance = balance + p_delta
    WHERE account_id = p_account_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Account not found');
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO lab_apply_adjustment_sp;
        RAISE;
END;
/
~~~

Procedure này không COMMIT. Nếu cập nhật thành công, thay đổi vẫn thuộc transaction của caller. Nếu lỗi, phần DML sau savepoint được hoàn tác và exception được truyền ra ngoài.

Đây là quy ước thiết kế, không phải yêu cầu rằng mọi procedure đều phải tạo savepoint. Với procedure chỉ chạy một câu DML, statement-level atomicity có thể đã đủ. Hãy cân nhắc savepoint khi procedure có nhiều DML cần được hoàn tác như một đơn vị.

## 17. Giao dịch tự trị (autonomous transaction) là trường hợp khác

PL/SQL có thể khai báo autonomous transaction bằng PRAGMA AUTONOMOUS_TRANSACTION. Giao dịch tự trị có transaction riêng, tách khỏi transaction của caller; nó phải tự COMMIT hoặc ROLLBACK trước khi kết thúc.

Savepoint của transaction caller không phải savepoint của autonomous transaction và ngược lại. ROLLBACK TO trong autonomous transaction chỉ tác động transaction tự trị đó. Không dùng autonomous transaction như cách thay thế savepoint cho nghiệp vụ thông thường; nó có mục đích riêng, thường dùng cho logging độc lập khi caller rollback.

## 18. Kiểm tra trạng thái trước và sau ROLLBACK TO

Với bài lab chuyển tiền, có thể dùng SELECT để quan sát:

~~~sql
SELECT
    account_id,
    holder_name,
    balance
FROM lab_tx_account
ORDER BY account_id;

SELECT
    transfer_id,
    from_account_id,
    to_account_id,
    transfer_amount,
    created_at
FROM lab_tx_transfer
ORDER BY transfer_id;
~~~

Một cách kiểm tra tổng số dư:

~~~sql
SELECT SUM(balance) AS total_balance
FROM lab_tx_account;
~~~

Nếu chỉ chuyển tiền giữa các tài khoản trong cùng bảng, tổng số dư phải được bảo toàn. Trước và sau khi rollback một phần, tổng vẫn là 1700. Đây là một invariant đơn giản giúp phát hiện lỗi cập nhật thiếu một phía.

Tuy nhiên, tổng số dư bảo toàn chưa chứng minh đúng từng tài khoản hoặc lịch sử. Hãy kiểm tra cả số dư theo account_id và các dòng transfer tương ứng.

## 19. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| ORA-01086 khi ROLLBACK TO | Savepoint chưa tạo, sai tên, đã bị xóa hoặc transaction đã kết thúc | Kiểm tra thứ tự lệnh, session và COMMIT/ROLLBACK/DDL |
| Dữ liệu không quay lại như mong đợi | Savepoint được đặt sau thay đổi cần hủy | Đặt savepoint trước nhóm DML cần có khả năng hoàn tác |
| ROLLBACK TO hủy cả phần muốn giữ | Chọn mốc quá sớm | Tạo savepoint ở ranh giới nghiệp vụ chính xác hơn |
| Không rollback được sau COMMIT | COMMIT đã kết thúc transaction | Dùng cơ chế phục hồi khác; savepoint không tồn tại sau commit |
| Savepoint của caller bị mất | Procedure dùng lại tên savepoint của caller | Dùng tiền tố tên riêng và thống nhất quy ước |
| DDL làm mất savepoint | DDL gây implicit commit | Tách DDL khỏi transaction DML |
| Client không rollback được | Autocommit đã commit câu DML | Tắt autocommit và quản lý transaction trên cùng connection |
| Một câu DML lỗi nhưng DML trước vẫn còn | Oracle rollback ở mức statement, không tự rollback toàn transaction | Dùng ROLLBACK TO hoặc ROLLBACK nếu muốn hủy phần trước |
| Sau ROLLBACK TO vẫn còn khóa | Khóa được lấy trước savepoint vẫn còn | Kết thúc transaction khi hoàn tất để giải phóng toàn bộ khóa |

## 20. Bài tập thực hành

### Bài 1 — Tạo savepoint và rollback một UPDATE

Tăng số dư tài khoản 1 thêm 100, đặt savepoint trước khi cập nhật tài khoản 2, sau đó rollback về savepoint.

**Yêu cầu:** xác định tài khoản nào giữ thay đổi và tài khoản nào trở về số dư cũ.

**Gợi ý:**

~~~sql
SAVEPOINT before_account_2;
~~~

Đặt savepoint đúng trước UPDATE cần có khả năng hủy, sau đó dùng ROLLBACK TO.

### Bài 2 — Hai mốc rollback

Trong một transaction, tạo hai savepoint A và B, thực hiện một UPDATE sau mỗi mốc, rồi rollback về A.

**Câu hỏi:** Những UPDATE nào bị hủy? Savepoint B còn dùng được không?

**Đáp án định hướng:** mọi thay đổi sau A bị hủy; B được tạo sau A nên không còn hợp lệ.

### Bài 3 — Đặt lại tên savepoint

Tạo savepoint tên PROGRESS, cập nhật một dòng, tạo lại PROGRESS, cập nhật dòng khác rồi rollback về PROGRESS.

**Câu hỏi:** Lần rollback quay về mốc nào?

**Đáp án:** mốc PROGRESS được tạo gần nhất; mốc cùng tên trước đó đã bị thay thế.

### Bài 4 — So sánh ROLLBACK TO và ROLLBACK

Thực hiện hai UPDATE sau một savepoint. Chạy ROLLBACK TO, kiểm tra dữ liệu, sau đó thực hiện thêm một UPDATE và chạy ROLLBACK toàn bộ.

**Câu hỏi:** Tại sao kết quả cuối quay về trạng thái trước transaction?

**Đáp án định hướng:** ROLLBACK TO chỉ hủy phần sau savepoint và giữ transaction mở; ROLLBACK sau đó hủy mọi thay đổi còn lại chưa commit.

### Bài 5 — Exception trong PL/SQL

Viết block PL/SQL đặt savepoint, cập nhật tài khoản nguồn, rồi cố cập nhật tài khoản không tồn tại. Nếu số dòng cập nhật không bằng 1, gọi RAISE_APPLICATION_ERROR; exception handler rollback về savepoint và RAISE lại lỗi.

**Yêu cầu:** không COMMIT trong block.

### Bài 6 — DDL và savepoint

Tạo savepoint, chạy một UPDATE, sau đó thử CREATE TABLE và ROLLBACK TO savepoint.

**Câu hỏi:** Vì sao rollback tới savepoint không còn hợp lệ?

**Đáp án định hướng:** DDL gây implicit commit, kết thúc transaction chứa savepoint.

### Bài 7 — Autocommit

Thử cùng một chuỗi SAVEPOINT/UPDATE/ROLLBACK TO trong client có autocommit bật và tắt.

**Câu hỏi:** Khác biệt về khả năng rollback là gì?

**Đáp án định hướng:** khi DML đã autocommit, transaction kết thúc và savepoint bị xóa; khi manual commit, có thể rollback về savepoint.

### Bài 8 — Quy trình chuyển tiền

Viết transaction gồm hai lần chuyển tiền, mỗi lần có hai UPDATE và một INSERT lịch sử. Đặt savepoint sau lần thứ nhất, rồi rollback lần thứ hai. Kiểm tra tổng số dư và lịch sử trước khi COMMIT.

**Kết quả mong đợi với dữ liệu mẫu:** An 800, Binh 700, Chi 200; chỉ transfer 5001 còn lại; tổng số dư 1700.

## 21. Quy trình quyết định đặt SAVEPOINT ở đâu

Trước khi đặt savepoint, xác định ranh giới nghiệp vụ:

1. Nhóm DML nào cần được giữ nếu bước sau thất bại?
2. Nhóm DML nào cần được hoàn tác cùng nhau?
3. Savepoint nên đặt trước bước đầu tiên của nhóm có thể bị hủy.
4. Có DDL, COMMIT hoặc ROLLBACK toàn bộ nào xảy ra giữa savepoint và điểm xử lý lỗi không?
5. Procedure có thể ghi đè savepoint cùng tên của caller không?
6. Client có autocommit hay dùng connection khác không?

Sơ đồ:

~~~text
Xác định transaction nghiệp vụ
             |
             v
Chia thành các nhóm DML hợp lệ
             |
             v
Đặt SAVEPOINT trước nhóm có thể cần hủy
             |
             v
Thực hiện DML và kiểm tra kết quả
             |
       Bước có lỗi?
        /       \
      Không      Có
       |          |
       v          v
Tiếp tục bước   ROLLBACK TO
tiếp theo       savepoint phù hợp
       |          |
       |          v
       |      Transaction còn mở
       |          |
       +-----+----+
             |
             v
       Đã hoàn tất?
        /       \
      Có         Chưa
      |            |
      v            v
   COMMIT      Tiếp tục DML
      |
      v
Transaction kết thúc
~~~

SAVEPOINT đánh dấu ranh giới có thể quay lại trong một transaction. ROLLBACK TO hủy các thay đổi sau mốc và giữ transaction mở để ứng dụng tiếp tục xử lý; ROLLBACK hủy toàn bộ thay đổi chưa commit; COMMIT xác nhận phần còn lại. Khi đặt mốc đúng trước nhóm DML cần kiểm soát, kiểm tra trạng thái sau mỗi bước và quản lý transaction trên cùng session, ta có thể hoàn tác một phần công việc mà không làm mất những thay đổi hợp lệ trước đó.
