# Hành vi sau lỗi và khả năng tiếp tục giao dịch theo hệ quản trị

Giao dịch (*transaction*) giúp nhiều thao tác SQL được xử lý như một đơn vị logic: hoặc những thay đổi cần thiết được xác nhận cùng nhau, hoặc chúng được hủy. Tuy nhiên, **không phải mọi hệ quản trị SQL đều phản ứng giống nhau khi một câu lệnh bên trong giao dịch gặp lỗi**.

Hãy tưởng tượng ứng dụng chuyển 100.000 đồng từ ví A sang ví B:

1. Trừ 100.000 đồng khỏi ví A.
2. Ghi một dòng nhật ký chuyển tiền.
3. Cộng 100.000 đồng vào ví B.
4. **COMMIT** nếu mọi bước đều hợp lệ; nếu không, **ROLLBACK**.

Nếu bước 2 gặp lỗi trùng khóa, câu hỏi không chỉ là “SQL nào đã lỗi?” mà còn là:

- **Bước 1 đã bị hủy hay vẫn đang nằm trong giao dịch?**
- **Giao dịch hiện tại còn tồn tại không?**
- **Có được chạy tiếp bước 3 không?**
- **Có thể COMMIT công việc trước lỗi không, hay bắt buộc ROLLBACK?**
- **SAVEPOINT có cứu được phần trước lỗi không?**
- **Một lỗi khác, chẳng hạn deadlock, có làm mất toàn bộ giao dịch không?**

Đây là nội dung của bài **“Hành vi sau lỗi và khả năng tiếp tục giao dịch theo hệ quản trị”**, thuộc chương **Giao dịch SQL** của module **Database SQL**. Ví dụ thực hành chính dùng **PostgreSQL 15 trở lên**; những phần đối chiếu riêng mô tả **MySQL 8.0/InnoDB, SQL Server, SQLite và Oracle Database**.

> **Nguyên tắc an toàn chung:** sau khi bất kỳ thao tác quan trọng nào thất bại, **không tự động COMMIT phần còn lại**. Hãy xác định lỗi, trạng thái giao dịch và chính sách nghiệp vụ; mặc định **ROLLBACK toàn bộ giao dịch** nếu không có cơ chế khôi phục một phần được thiết kế rõ ràng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **lỗi câu lệnh**, **giao dịch bị đánh dấu thất bại**, **giao dịch đã bị hủy hoàn toàn** và **giao dịch còn có thể COMMIT**.
2. Giải thích vì sao PostgreSQL thường yêu cầu **ROLLBACK** hoặc **ROLLBACK TO SAVEPOINT** sau lỗi trong một giao dịch tường minh.
3. Nhận diện trạng thái lỗi **25P02** của PostgreSQL và không nhầm nó với nguyên nhân gốc.
4. Sử dụng **SAVEPOINT**, **ROLLBACK TO SAVEPOINT** và **RELEASE SAVEPOINT** ở đúng thời điểm.
5. Hiểu cách **MySQL InnoDB** thường hủy một câu lệnh lỗi mà vẫn giữ transaction, và vì sao deadlock có thể hủy cả transaction.
6. Dùng **XACT_STATE()**, **TRY...CATCH**, **XACT_ABORT** trên SQL Server để quyết định COMMIT/ROLLBACK.
7. Phân biệt hành vi **ABORT/FAIL/IGNORE/REPLACE/ROLLBACK** khi SQLite gặp lỗi ràng buộc.
8. Hiểu quy tắc **statement-level rollback** thường gặp của Oracle và nguy cơ DDL tự COMMIT.
9. Thiết kế cách xử lý lỗi từ ứng dụng/JDBC: rollback, retry toàn giao dịch, idempotency và quản lý connection.
10. Tránh suy luận rằng “câu SQL sau lỗi vẫn chạy được” đồng nghĩa dữ liệu đang nhất quán và an toàn để COMMIT.

## 2. Bốn trạng thái sau lỗi cần phân biệt

Hãy tách bốn tình huống sau, dù bề ngoài đều bắt đầu bằng thông báo lỗi SQL.

| Trạng thái thực tế | Ý nghĩa | Hành động thông thường |
| --- | --- | --- |
| **Chỉ câu lệnh lỗi bị hủy** | Những thay đổi trước đó trong transaction còn ở trạng thái chưa COMMIT; giao dịch có thể vẫn dùng được | Kiểm tra chính sách, sửa lỗi hoặc ROLLBACK; chỉ tiếp tục nếu hợp lệ |
| **Giao dịch còn tồn tại nhưng không thể COMMIT** | Transaction đã bị đánh dấu thất bại/uncommittable; các thao tác ghi tiếp theo có thể bị chặn | ROLLBACK toàn bộ hoặc ROLLBACK TO SAVEPOINT khi hệ cho phép |
| **Toàn bộ transaction đã được rollback tự động** | Những thay đổi chưa COMMIT trong giao dịch bị hủy | Bắt đầu transaction mới nếu cần retry |
| **Kết nối/phiên bị chấm dứt** | Không thể tiếp tục trên cùng connection; transaction chưa COMMIT thường bị hủy theo quy tắc của hệ | Thiết lập lại kết nối và xác minh kết quả trước retry |

Chỉ biết **loại lỗi** chưa đủ. Hành vi còn phụ thuộc:

- Hệ quản trị và phiên bản.
- Có ở trong **transaction tường minh** hay đang bật **autocommit**.
- Loại ràng buộc/lỗi: UNIQUE, FK, CHECK, lỗi cú pháp, deadlock, timeout, hết dung lượng, mất kết nối.
- Tùy chọn như **SET XACT_ABORT** hoặc **innodb_rollback_on_timeout**.
- Transaction đã có **SAVEPOINT** hay chưa.
- Câu lệnh là DML, DDL, lệnh đặc thù của engine, hoặc đoạn code procedure/trigger.

**ACID/atomicity** không bắt buộc mọi hệ quản trị phải có cùng một cơ chế “sau một câu lệnh lỗi thì transaction còn chạy được hay không”. Atomicity cho phép hủy toàn bộ đơn vị giao dịch, còn **khả năng tiếp tục sau lỗi** là một quyết định về ngữ nghĩa thực thi của từng hệ.

## 3. Transaction tường minh khác autocommit

### 3.1. Autocommit

Trong chế độ autocommit thường gặp, **mỗi câu lệnh độc lập** được xử lý như một giao dịch riêng nếu ứng dụng chưa chủ động bắt đầu một transaction nhiều bước.

Ví dụ ý tưởng:

~~~sql
UPDATE wallets SET balance = balance - 100 WHERE wallet_id = 1;
UPDATE wallets SET balance = balance + 100 WHERE wallet_id = 2;
~~~

Nếu hai lệnh chạy **độc lập, tự COMMIT từng lệnh**, lỗi ở lệnh thứ hai không tự hủy lệnh thứ nhất đã COMMIT. Vì vậy, autocommit **không phù hợp** cho một chuyển tiền cần atomicity.

### 3.2. Transaction tường minh

~~~sql
BEGIN;

UPDATE wallets SET balance = balance - 100 WHERE wallet_id = 1;
UPDATE wallets SET balance = balance + 100 WHERE wallet_id = 2;

COMMIT;
~~~

Đây là **khung ý tưởng** với bảng wallets giả định. Trong hệ hỗ trợ BEGIN, hai UPDATE có thể nằm trong cùng giao dịch. Nếu chúng phải cùng thành công, ứng dụng cần **ROLLBACK khi bất kỳ bước bắt buộc nào thất bại**.

**Lưu ý quan trọng:** một client có thể có tùy chọn tự tắt hoặc bật autocommit, tự rollback khi gặp lỗi, hay dừng script. Trạng thái **client** và trạng thái **transaction trên máy chủ** phải được phân biệt. Ví dụ, việc psql dừng gửi câu lệnh khi gặp lỗi không có nghĩa PostgreSQL đã tự ROLLBACK toàn bộ giao dịch trong mọi trường hợp.

## 4. Bộ dữ liệu thực hành PostgreSQL

Tạo hai bảng tạm trong một phiên PostgreSQL: ví và biên nhận. Dữ liệu được thiết kế để tạo lỗi UNIQUE khi cần.

~~~sql
CREATE TEMP TABLE tx_demo_wallets (
    wallet_id INTEGER PRIMARY KEY,
    balance_vnd NUMERIC(12, 2) NOT NULL
        CHECK (balance_vnd >= 0)
);

CREATE TEMP TABLE tx_demo_receipts (
    receipt_id INTEGER PRIMARY KEY,
    wallet_id INTEGER NOT NULL
        REFERENCES tx_demo_wallets(wallet_id),
    amount_vnd NUMERIC(12, 2) NOT NULL
        CHECK (amount_vnd > 0),
    description TEXT NOT NULL
);

INSERT INTO tx_demo_wallets(wallet_id, balance_vnd)
VALUES
    (1, 1000000),
    (2, 500000);

INSERT INTO tx_demo_receipts
    (receipt_id, wallet_id, amount_vnd, description)
VALUES
    (10, 1, 10000, 'Bien nhan da ton tai');
~~~

Trạng thái ban đầu:

| Bảng | Khóa | Giá trị |
| --- | --- | --- |
| tx_demo_wallets | wallet_id = 1 | 1.000.000 VND |
| tx_demo_wallets | wallet_id = 2 | 500.000 VND |
| tx_demo_receipts | receipt_id = 10 | Biên nhận đã tồn tại |

Để làm các thí nghiệm độc lập, phần lớn ví dụ dùng **BEGIN ... ROLLBACK** thay vì COMMIT. Điều đó giúp giữ dữ liệu mẫu không đổi qua các phần.

> **Các ví dụ có chú thích “cố ý lỗi” là thí nghiệm:** một số công cụ SQL sẽ dừng cả script ngay tại lỗi thay vì chạy các dòng sau. Nếu cần quan sát trạng thái sau lỗi, hãy gửi từng câu trong **cùng một connection và transaction**, rồi gửi ROLLBACK để dọn trạng thái. Không chạy chúng trên bảng sản xuất.

## 5. PostgreSQL: một lỗi thường làm transaction vào trạng thái aborted

Trong PostgreSQL, nếu một câu lệnh gây lỗi khi đang ở transaction tường minh, transaction thường chuyển sang trạng thái **aborted/failed**. Những câu SQL thông thường sau đó không còn được thực thi cho tới khi **ROLLBACK toàn bộ** hoặc **ROLLBACK TO SAVEPOINT hợp lệ** để phục hồi.

### 5.1. Minh họa lỗi trùng khóa

~~~sql
BEGIN;

-- Bước 1: phép ghi hợp lệ, nhưng vẫn chưa COMMIT.
UPDATE tx_demo_wallets
SET balance_vnd = balance_vnd - 100000
WHERE wallet_id = 1;

-- Bước 2: cố ý trùng PRIMARY KEY receipt_id = 10.
INSERT INTO tx_demo_receipts
    (receipt_id, wallet_id, amount_vnd, description)
VALUES
    (10, 1, 100000, 'Bien nhan bi trung');

-- Bước 3: không thể tiếp tục bình thường sau lỗi ở bước 2.
UPDATE tx_demo_wallets
SET balance_vnd = balance_vnd + 100000
WHERE wallet_id = 2;

ROLLBACK;
~~~

Khi chạy từng câu trong cùng transaction:

1. UPDATE đầu có thể tạm thời làm ví 1 còn **900.000**.
2. INSERT với **receipt_id = 10** thất bại vì PRIMARY KEY đã tồn tại. PostgreSQL trả lỗi UNIQUE, thường có SQLSTATE **23505**.
3. UPDATE tiếp theo không chạy thành công; máy chủ có thể trả:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
~~~

4. **ROLLBACK** hủy thay đổi từ bước 1; hai ví về số dư ban đầu.

**Điểm mấu chốt:** một lỗi ở bước 2 làm PostgreSQL không cho transaction tiếp tục theo cách thông thường. **25P02 là hậu quả của trạng thái transaction đã hỏng**, không nhất thiết là lỗi gốc cần xử lý. Hãy tìm **thông báo lỗi đầu tiên**, trong ví dụ là **23505**.

### 5.2. COMMIT khi transaction đã aborted không phải lối thoát

Nếu người dùng gửi **COMMIT** khi transaction PostgreSQL đang ở trạng thái aborted, PostgreSQL không xác nhận các thao tác trước lỗi như một giao dịch thành công; nó **kết thúc bằng rollback** theo hành vi của hệ. Một số client hiển thị phản hồi **ROLLBACK**.

Vì vậy, không viết logic ứng dụng kiểu:

~~~text
try INSERT
nếu INSERT lỗi thì bỏ qua
cuối cùng cứ COMMIT
~~~

trên PostgreSQL. Kịch bản này vừa không tiếp tục được, vừa có thể khiến người lập trình hiểu nhầm trạng thái dữ liệu nếu chỉ nhìn xem lệnh COMMIT có được gửi hay không.

**Thực hành đúng:** khi lỗi bất ngờ xảy ra trong transaction, gọi **ROLLBACK** có chủ đích, ghi nhận lỗi gốc, rồi quyết định có bắt đầu một transaction mới không.

### 5.3. Cách quan sát rollback

Sau khi chạy thí nghiệm và ROLLBACK:

~~~sql
SELECT wallet_id, balance_vnd
FROM tx_demo_wallets
ORDER BY wallet_id;
~~~

Kết quả vẫn là 1.000.000 và 500.000. Bản ghi receipt_id = 10 ban đầu vẫn còn, không bị biến thành một dòng mới.

**Một rollback không “undo” những transaction đã COMMIT trước đó.** Nó chỉ hủy những thay đổi chưa được xác nhận trong transaction đang xét.

## 6. PostgreSQL: SAVEPOINT cho phép khôi phục một phần sau lỗi

Trong nhiều workflow, một bước không bắt buộc có thể được thử trong một transaction lớn. Nếu bước đó lỗi, nghiệp vụ có thể cho phép hủy **chỉ phần từ SAVEPOINT trở đi**, giữ các thay đổi hợp lệ trước SAVEPOINT.

Cú pháp:

~~~sql
SAVEPOINT checkpoint_name;
ROLLBACK TO SAVEPOINT checkpoint_name;
RELEASE SAVEPOINT checkpoint_name;
~~~

**SAVEPOINT** đặt một điểm khôi phục. **ROLLBACK TO SAVEPOINT** hủy thay đổi kể từ điểm đó và làm transaction quay lại trạng thái có thể tiếp tục khi rollback thành công. **RELEASE SAVEPOINT** bỏ điểm khôi phục sau khi không còn cần sử dụng; nó **không COMMIT transaction ngoài**.

### 6.1. Thực hành: bắt lỗi của bước tùy chọn

~~~sql
BEGIN;

-- Bước bắt buộc: cập nhật mô phỏng trong giao dịch.
UPDATE tx_demo_wallets
SET balance_vnd = balance_vnd - 10000
WHERE wallet_id = 1;

-- Đặt savepoint trước một bước tùy chọn có thể thất bại.
SAVEPOINT before_optional_receipt;

-- Cố ý lỗi: receipt_id = 10 đã có.
INSERT INTO tx_demo_receipts
    (receipt_id, wallet_id, amount_vnd, description)
VALUES
    (10, 1, 10000, 'Thu ghi bi trung');

-- Sau khi nhận lỗi, câu phục hồi phải là:
ROLLBACK TO SAVEPOINT before_optional_receipt;

-- Có thể thực hiện một thao tác mới sau khi đã hồi phục.
INSERT INTO tx_demo_receipts
    (receipt_id, wallet_id, amount_vnd, description)
VALUES
    (11, 1, 10000, 'Thu ghi hop le');

-- Chỉ xem thử các thay đổi còn hiệu lực trong transaction.
SELECT wallet_id, balance_vnd
FROM tx_demo_wallets
WHERE wallet_id = 1;

SELECT receipt_id, description
FROM tx_demo_receipts
WHERE receipt_id IN (10, 11)
ORDER BY receipt_id;

ROLLBACK;
~~~

**Điều kiện để chạy thử:** client phải tiếp tục gửi **ROLLBACK TO SAVEPOINT** sau lỗi INSERT. Một số IDE hoặc script runner dừng thực thi khi câu SQL đầu tiên lỗi; khi đó cần gửi câu rollback tới savepoint bằng tay trong cùng connection.

Sau ROLLBACK TO SAVEPOINT:

- UPDATE trước savepoint vẫn tồn tại **tạm thời** trong transaction.
- INSERT lỗi receipt_id = 10 không được áp dụng.
- INSERT receipt_id = 11 có thể thực hiện.
- ROLLBACK toàn bộ ở cuối hủy cả UPDATE đầu và INSERT id 11, đưa dữ liệu mẫu về ban đầu.

### 6.2. Không được RELEASE thay cho ROLLBACK TO sau lỗi

Trong PostgreSQL, ngay sau lỗi làm transaction aborted, không nên thử:

~~~sql
RELEASE SAVEPOINT before_optional_receipt;
~~~

để “bỏ qua lỗi”. Bước cần thiết là **ROLLBACK TO SAVEPOINT before_optional_receipt**. Nếu muốn bỏ savepoint sau khi transaction đã được hồi phục, có thể dùng RELEASE SAVEPOINT sau đó.

**RELEASE không đồng nghĩa COMMIT; ROLLBACK TO không đồng nghĩa ROLLBACK toàn bộ.**

### 6.3. Savepoint không làm một nghiệp vụ sai trở thành hợp lệ

Giả sử chuyển tiền cần cả ba bước đều thành công. Nếu lỗi ghi nhật ký ở bước 2 mà hệ thống vẫn COMMIT phép trừ tiền bước 1, giao dịch có thể vi phạm yêu cầu kiểm toán. Kỹ thuật rollback một phần chỉ nên dùng khi **nghiệp vụ cho phép phần đó thất bại mà tổng thể vẫn đúng**.

Với chuyển tiền thực, cách an toàn thường là **ROLLBACK toàn bộ và sửa hoặc retry từ đầu**. Savepoint phù hợp hơn với các thao tác thực sự **tùy chọn**, ví dụ ghi dữ liệu bổ sung không có tính bắt buộc, và phải có chính sách audit đúng.

## 7. PostgreSQL: vì sao 25P02 không phải nguyên nhân gốc?

Giả sử log có nhiều lỗi:

~~~text
ERROR 23505: duplicate key value violates unique constraint
ERROR 25P02: current transaction is aborted
ERROR 25P02: current transaction is aborted
ERROR 25P02: current transaction is aborted
~~~

Lỗi đầu tiên **23505** mới cho biết một receipt_id bị trùng. Những lỗi **25P02** sau đó chủ yếu báo rằng ứng dụng tiếp tục gửi SQL khi transaction đang ở trạng thái aborted.

Các mã SQLSTATE PostgreSQL đáng nhận diện:

| SQLSTATE | Tên lỗi PostgreSQL thường gặp | Ý nghĩa đối với xử lý |
| --- | --- | --- |
| **23505** | unique_violation | Bản ghi vi phạm UNIQUE/PRIMARY KEY |
| **23503** | foreign_key_violation | Không thỏa ràng buộc tham chiếu |
| **23514** | check_violation | Vi phạm CHECK |
| **23502** | not_null_violation | Thiếu giá trị bắt buộc |
| **25P02** | in_failed_sql_transaction | Transaction đã lỗi từ trước, cần rollback thích hợp |
| **40P01** | deadlock_detected | Giao dịch bị chọn làm nạn nhân deadlock; cần retry toàn đơn vị khi thích hợp |
| **40001** | serialization_failure | Cần retry **toàn bộ transaction**, không chỉ một câu lệnh tùy ý |
| **57014** | query_canceled | Truy vấn bị hủy, ví dụ do statement_timeout hoặc người dùng hủy |

Không nên tự động kết luận mọi SQLSTATE đều được xử lý bằng cách **retry ngay cùng câu SQL**. Vi phạm UNIQUE do dữ liệu nguồn trùng không hết khi retry, trong khi deadlock/serialization failure có thể là lỗi tạm thời nếu retry đúng quy tắc.

### 7.1. Các lỗi có thể phát sinh trước khi transaction bắt đầu

Nếu một câu SQL không hợp lệ được gửi **ngoài transaction tường minh** trong chế độ autocommit, PostgreSQL có thể rollback transaction ngầm của riêng câu đó và chấp nhận câu tiếp theo bình thường. Điều này **không mâu thuẫn** với hành vi aborted của transaction tường minh: hai trường hợp có **ranh giới giao dịch khác nhau**.

### 7.2. psql và ON_ERROR_ROLLBACK

**psql** có tùy chọn client **ON_ERROR_ROLLBACK**, có thể dùng savepoint nội bộ để hỗ trợ thử nghiệm nhiều câu trong transaction mà không để một lỗi đơn giản phá hỏng toàn bộ phiên thử. Ví dụ meta-command:

~~~text
\set ON_ERROR_ROLLBACK on
~~~

Đây là **thiết lập của psql**, không phải thuộc tính chung của giao dịch PostgreSQL và không áp dụng tự động cho mọi driver JDBC hoặc ứng dụng.

Tùy chọn **ON_ERROR_STOP** của psql lại quyết định client có dừng xử lý script khi gặp lỗi hay không. Cần phân biệt **dừng gửi lệnh ở client** với **rollback/sử dụng savepoint ở server**.

## 8. MySQL InnoDB: lỗi câu lệnh thường không hủy toàn bộ transaction

Trên **MySQL 8.0 với InnoDB**, nhiều lỗi DML như vi phạm khóa duy nhất thường khiến **chỉ câu lệnh lỗi bị rollback**, trong khi transaction tường minh vẫn đang hoạt động và những thay đổi trước đó chưa COMMIT vẫn được giữ.

Đây là **khác biệt lớn với hành vi aborted sau lỗi thông thường của PostgreSQL**.

### 8.1. Ví dụ MySQL

Ví dụ dưới đây dành cho MySQL 8.0/InnoDB, không chạy nguyên văn trên bảng tạm PostgreSQL của phần 4:

~~~sql
CREATE TABLE mysql_tx_demo (
    id INT PRIMARY KEY,
    note VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO mysql_tx_demo(id, note)
VALUES (10, 'Co san');

START TRANSACTION;

INSERT INTO mysql_tx_demo(id, note)
VALUES (11, 'Truoc loi');

-- Cố ý gây lỗi duplicate key, mã MySQL thường là 1062.
INSERT INTO mysql_tx_demo(id, note)
VALUES (10, 'Bi trung');

-- Thường vẫn được phép chạy trong InnoDB.
INSERT INTO mysql_tx_demo(id, note)
VALUES (12, 'Sau loi');

-- Dùng ROLLBACK cho thí nghiệm để không lưu 11 và 12.
ROLLBACK;
~~~

Giả sử client tiếp tục gửi lệnh sau lỗi:

1. Hàng id = 11 được chèn trong transaction.
2. Lệnh chèn id = 10 gặp lỗi **Duplicate entry**.
3. Lệnh chèn id = 12 có thể vẫn thành công.
4. Nếu **COMMIT** thay cho ROLLBACK, cả id = 11 và id = 12 **có thể được lưu**, mặc dù có một lệnh ở giữa đã thất bại.

**Vì vậy, việc MySQL vẫn cho chạy câu SQL kế tiếp không có nghĩa nên COMMIT.** Với một nghiệp vụ phải thành công toàn phần, ứng dụng cần tự đánh dấu transaction thất bại và ROLLBACK cả các lệnh trước đó.

### 8.2. Đây là hành vi của InnoDB, không phải mọi storage engine

MySQL cho phép những storage engine có đặc tính giao dịch khác nhau. Ví dụ, **InnoDB** hỗ trợ transaction; những engine không transactional có hành vi rollback khác. Khi hệ thống trộn bảng transactional và nontransactional, giả định “ROLLBACK hủy mọi thay đổi” có thể không đúng.

**Trước khi dựa vào khả năng rollback**, cần xác nhận bảng dùng **engine transactional**, ví dụ InnoDB, và hiểu tác động của trigger, DDL hoặc thao tác ngoài transaction.

## 9. MySQL InnoDB: deadlock và lock wait timeout là hai trường hợp khác

Không được áp dụng máy móc câu “MySQL chỉ rollback câu SQL lỗi” cho mọi lỗi.

### 9.1. Deadlock thường làm InnoDB rollback toàn transaction

Một tình huống deadlock:

~~~text
Transaction A                  Transaction B
-------------                  -------------
khóa hàng X                    khóa hàng Y
chờ hàng Y                     chờ hàng X
            \                  /
                 DEADLOCK
~~~

InnoDB phát hiện vòng chờ và chọn một transaction làm nạn nhân. Với nạn nhân, **toàn bộ transaction bị rollback** để giải phóng deadlock. Mã lỗi MySQL thường gặp là **1213**.

Khi gặp deadlock, không nên cố gửi COMMIT tiếp trên cùng “transaction cũ” như thể chỉ một INSERT lỗi. Cần coi đơn vị nghiệp vụ đã thất bại và, nếu hợp lý, **bắt đầu transaction mới và retry toàn bộ**.

### 9.2. Lock wait timeout có thể chỉ rollback statement

Lỗi chờ khóa quá lâu thường có mã MySQL **1205**. Trong cấu hình InnoDB thông dụng, lock wait timeout có thể rollback **chỉ câu lệnh đang chờ**, trong khi transaction còn tồn tại.

Tuy nhiên, cấu hình **innodb_rollback_on_timeout** có thể làm MySQL rollback **toàn transaction** khi timeout. Vì vậy, cách xử lý phải dựa vào **cấu hình và trạng thái thực tế**, không chỉ đọc chữ “timeout”.

Đặc biệt, một transaction đã bị timeout ở bước ghi quan trọng **không nên được COMMIT một phần** chỉ vì engine vẫn còn cho phép thực thi câu khác.

### 9.3. DDL có thể ngầm COMMIT

Trong MySQL, nhiều lệnh DDL như **CREATE TABLE**, **ALTER TABLE** có cơ chế **implicit commit**. Nếu một ứng dụng đang xử lý transaction nhập dữ liệu rồi chen vào một lệnh DDL, ranh giới atomicity có thể bị thay đổi ngoài ý muốn.

Do đó, nên tách **migration schema** khỏi **transaction nghiệp vụ**, và kiểm tra quy tắc commit của từng loại lệnh trong MySQL đang dùng.

## 10. SQL Server: trạng thái giao dịch phụ thuộc lỗi và XACT_ABORT

Trên **SQL Server**, một số lỗi chỉ làm câu lệnh thất bại, nhưng một số lỗi làm transaction trở nên **uncommittable** hoặc bị rollback hoàn toàn. Thiết lập **SET XACT_ABORT ON/OFF** và cách bắt lỗi bằng **TRY...CATCH** có vai trò lớn.

Không nên trả lời chung rằng SQL Server “giống PostgreSQL” hay “giống MySQL” về mọi lỗi.

### 10.1. XACT_STATE() là công cụ quyết định

SQL Server có hàm:

~~~sql
SELECT XACT_STATE() AS transaction_state;
~~~

Giá trị:

| XACT_STATE() | Nghĩa | Có COMMIT được không? | Hành động phổ biến |
| ---: | --- | --- | --- |
| **1** | Có transaction đang hoạt động và **committable** | **Có**, về mặt kỹ thuật | COMMIT chỉ nếu nghiệp vụ cho phép; nếu không ROLLBACK |
| **-1** | Có transaction nhưng **uncommittable** | **Không** | ROLLBACK toàn transaction |
| **0** | Không có user transaction đang hoạt động | Không có gì để COMMIT | Xác minh kết quả, có thể bắt đầu transaction mới |

Hàm **@@TRANCOUNT** cho biết số mức transaction logic hiện có, nhưng **không cho biết transaction còn COMMIT được hay không**. Trong trường hợp XACT_STATE() = -1, @@TRANCOUNT có thể vẫn lớn hơn 0.

**Không dùng @@TRANCOUNT > 0 làm điều kiện duy nhất để COMMIT.** Hãy kiểm tra XACT_STATE() và chính sách nghiệp vụ.

### 10.2. SET XACT_ABORT OFF: một số lỗi vẫn cho tiếp tục

Trong nhiều ngữ cảnh ad-hoc, **SET XACT_ABORT OFF** cho phép một số lỗi như vi phạm ràng buộc chỉ hủy câu lệnh, không tự hủy transaction. Ví dụ minh họa trong SQL Server:

~~~sql
SET XACT_ABORT OFF;

CREATE TABLE #tx_demo (
    id INT PRIMARY KEY,
    note NVARCHAR(100) NOT NULL
);

INSERT INTO #tx_demo(id, note) VALUES (10, N'Co san');

BEGIN TRY
    BEGIN TRANSACTION;

    INSERT INTO #tx_demo(id, note)
    VALUES (11, N'Truoc loi');

    -- Cố ý trùng khóa. Lỗi thường là 2627.
    INSERT INTO #tx_demo(id, note)
    VALUES (10, N'Bi trung');

    INSERT INTO #tx_demo(id, note)
    VALUES (12, N'Sau loi');

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    SELECT
        ERROR_NUMBER() AS error_number,
        ERROR_MESSAGE() AS error_message,
        XACT_STATE() AS xact_state;

    -- Chính sách an toàn ở ví dụ: lỗi bất kỳ thì rollback.
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
END CATCH;
~~~

Khi lỗi trùng khóa chuyển điều khiển vào CATCH, **câu lệnh sau lỗi trong TRY không tiếp tục chạy**, kể cả nếu transaction còn committable. Với tình huống duplicate key và XACT_ABORT OFF thông dụng, XACT_STATE() có thể là **1**; điều này có nghĩa **về mặt kỹ thuật có thể COMMIT** những thay đổi trước lỗi, **không có nghĩa nghiệp vụ nên làm vậy**.

Ví dụ cố ý ROLLBACK bất cứ khi nào bắt được lỗi, để không lưu một phần.

### 10.3. SET XACT_ABORT ON: nhiều lỗi khiến transaction không thể COMMIT

~~~sql
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    -- Các lệnh DML bắt buộc.
    -- Một số runtime error có thể làm transaction không thể COMMIT.
    -- ...

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    SELECT XACT_STATE() AS xact_state;

    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
~~~

Với **XACT_ABORT ON**, nhiều lỗi khi chạy DML có thể làm toàn bộ transaction bị hủy hoặc chuyển sang trạng thái **-1** trong TRY...CATCH. Nếu XACT_STATE() = -1, chỉ có thể **đọc dữ liệu** hoặc **ROLLBACK toàn transaction**; các thao tác ghi và COMMIT không được phép.

**Không khẳng định mọi lỗi luôn trả -1.** Một số lỗi khiến transaction đã bị rollback nên XACT_STATE() = 0, một số lỗi không thuộc TRY...CATCH ở cùng cấp, và các mức nghiêm trọng có thể làm hỏng connection. Cần xử lý cả ba giá trị.

### 10.4. RAISERROR và THROW không giống nhau

Trong SQL Server, **THROW** tuân theo cách xử lý của **SET XACT_ABORT**; **RAISERROR** có những khác biệt và không tuân theo XACT_ABORT như THROW. Nếu ứng dụng tự phát sinh lỗi nghiệp vụ, cách chọn câu lệnh báo lỗi có thể ảnh hưởng trạng thái transaction.

Vì vậy, không nên giả định một đoạn **RAISERROR** trong stored procedure có hậu quả transaction giống hệt một lỗi UNIQUE của engine.

## 11. SQL Server: SAVE TRANSACTION và giới hạn trong trạng thái -1

SQL Server có lệnh tạo savepoint:

~~~sql
SAVE TRANSACTION before_optional_step;
~~~

Và rollback về savepoint:

~~~sql
ROLLBACK TRANSACTION before_optional_step;
~~~

Điều kiện quan trọng: nếu **XACT_STATE() = -1**, transaction đã **uncommittable**; không thể dùng rollback đến savepoint như một cách ghi thay đổi bù trừ trong transaction bị hỏng. Phải **ROLLBACK toàn bộ**.

Một khung xử lý:

~~~sql
-- Ví dụ SQL Server, dùng khi giao dịch có bước tùy chọn.
SET XACT_ABORT OFF;

BEGIN TRANSACTION;
SAVE TRANSACTION before_optional_step;

BEGIN TRY
    -- Thao tác tùy chọn có thể gây lỗi.
    -- ...
END TRY
BEGIN CATCH
    IF XACT_STATE() = 1
    BEGIN
        -- Có thể phục hồi tới savepoint khi nghiệp vụ cho phép.
        ROLLBACK TRANSACTION before_optional_step;
    END
    ELSE IF XACT_STATE() = -1
    BEGIN
        -- Không thể commit hoặc rollback riêng một savepoint.
        ROLLBACK TRANSACTION;
    END
    -- Nếu XACT_STATE() = 0 thì không còn transaction để rollback.
END CATCH;

-- Phải kiểm tra còn transaction và chính sách nghiệp vụ
-- trước khi đưa ra quyết định COMMIT cuối cùng.
IF XACT_STATE() = 1
    ROLLBACK TRANSACTION; -- Bài thực hành hủy dữ liệu.
~~~

Đoạn này minh họa **lựa chọn theo XACT_STATE**, không phải một mẫu đầy đủ để tự động bỏ qua mọi lỗi. Trong ứng dụng thật, cần xác định bước nào tùy chọn và **THROW/báo lại lỗi** khi chính sách yêu cầu hủy toàn nghiệp vụ.

### 11.1. Lỗi deadlock SQL Server

SQL Server thường trả lỗi **1205** khi một transaction bị chọn làm nạn nhân deadlock. Transaction nạn nhân đã bị rollback. Ứng dụng nên **retry toàn đơn vị giao dịch** từ đầu khi thích hợp, không cố dùng các câu SQL sau lỗi để nối tiếp transaction đã mất.

Retry cần có giới hạn số lần, backoff và phải biết các side effect bên ngoài transaction đã xảy ra hay chưa.

## 12. SQLite: hành vi theo conflict resolution algorithm

SQLite có cơ chế giải quyết lỗi ràng buộc như **ABORT**, **FAIL**, **IGNORE**, **REPLACE** và **ROLLBACK**. Những tên này không có nghĩa mọi lỗi trong SQLite đều dùng chung một chính sách, nhưng chúng rất quan trọng khi làm việc với UNIQUE/NOT NULL/CHECK/PRIMARY KEY ở những trường hợp được hỗ trợ.

### 12.1. Bảng minh họa

~~~sql
CREATE TABLE sqlite_tx_demo (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL UNIQUE
);

INSERT INTO sqlite_tx_demo(id, label)
VALUES (1, 'A');
~~~

SQLite có giao dịch:

~~~sql
BEGIN;
-- ...
ROLLBACK;
~~~

### 12.2. ABORT: mặc định thường gặp

~~~sql
BEGIN;

INSERT INTO sqlite_tx_demo(id, label)
VALUES (2, 'B');

-- Cố ý trùng id = 1, hành vi ABORT mặc định:
INSERT INTO sqlite_tx_demo(id, label)
VALUES (1, 'C');

-- Transaction thường còn mở sau constraint ABORT.
ROLLBACK;
~~~

Với conflict algorithm **ABORT**, SQLite hủy những thay đổi của **câu lệnh gây lỗi**, nhưng **giữ các thay đổi của các câu trước trong transaction** và thường cho phép transaction tiếp tục. Điều này tương tự hành vi statement rollback trong nhiều tình huống InnoDB/Oracle, **không giống trạng thái aborted mặc định của PostgreSQL trong explicit transaction**.

### 12.3. FAIL, IGNORE, REPLACE và ROLLBACK

| Thuật toán SQLite | Hành vi khái quát đối với xung đột phù hợp | Cần chú ý |
| --- | --- | --- |
| **ABORT** | Hủy thay đổi của **câu lệnh hiện tại**, giữ transaction | Mặc định của nhiều constraint |
| **FAIL** | Dừng khi lỗi nhưng **có thể giữ** những thay đổi từ các hàng trước đó trong **cùng câu lệnh** | Không đồng nghĩa statement atomic rollback |
| **IGNORE** | Bỏ qua hàng vi phạm loại constraint được hỗ trợ, tiếp tục những hàng khác | Có thể che giấu dòng nguồn bị loại |
| **REPLACE** | Với UNIQUE/PRIMARY KEY, có thể **xóa hàng xung đột rồi chèn hàng mới** | Không tương đương UPDATE; ảnh hưởng khóa ngoại/triggers/định danh |
| **ROLLBACK** | Hủy toàn bộ transaction hiện tại khi xảy ra xung đột phù hợp | Nếu không có transaction tường minh, hiệu ứng gần với ABORT |

Ví dụ:

~~~sql
-- SQLite, chỉ dùng để thí nghiệm trên bảng mẫu:
INSERT OR IGNORE INTO sqlite_tx_demo(id, label)
VALUES (1, 'Trung id');
~~~

Hàng bị trùng có thể bị bỏ qua. Nhưng **IGNORE không phải bộ lọc lỗi nghiệp vụ tổng quát**; đặc biệt lỗi FOREIGN KEY không được xử lý theo cùng cách như một số UNIQUE/NOT NULL/CHECK conflict.

### 12.4. REPLACE không phải UPDATE

~~~sql
-- SQLite:
INSERT OR REPLACE INTO sqlite_tx_demo(id, label)
VALUES (1, 'A moi');
~~~

Với conflict UNIQUE/PRIMARY KEY phù hợp, SQLite có thể **xóa hàng cũ và chèn hàng mới** thay vì sửa tại chỗ. Điều này có thể gây tác động đến quan hệ tham chiếu, trigger hoặc giá trị khóa không được cung cấp.

Không dùng **INSERT OR REPLACE** làm bản dịch tự động của PostgreSQL **ON CONFLICT DO UPDATE** nếu nghiệp vụ yêu cầu **giữ nguyên danh tính hàng cũ**.

### 12.5. SQLite UPSERT và thuật toán xung đột

SQLite hiện đại có:

~~~sql
INSERT INTO sqlite_tx_demo(id, label)
VALUES (1, 'A moi')
ON CONFLICT(id) DO UPDATE
SET label = excluded.label;
~~~

Cách viết này diễn đạt update-or-insert, khác với **INSERT OR REPLACE**. Tuy nhiên, nếu **DO UPDATE** vi phạm ràng buộc khác, SQLite có những quy tắc riêng; hành động DO UPDATE của UPSERT thường có hành vi **ABORT** khi ràng buộc thất bại, bất kể conflict algorithm bên ngoài.

**Không gom mọi trường hợp SQLite constraint violation vào một quy tắc duy nhất.**

## 13. SQLite: một số lỗi tài nguyên có thể tự rollback transaction

Ngoài lỗi constraint thông thường, SQLite có các lỗi như:

- **SQLITE_BUSY**: không thể lấy khóa cần thiết.
- **SQLITE_FULL**: thiết bị/cơ sở dữ liệu không còn đủ dung lượng theo điều kiện áp dụng.
- **SQLITE_IOERR**: lỗi I/O.
- **SQLITE_NOMEM**: thiếu bộ nhớ.
- Các lỗi phát sinh khi cố **COMMIT** một transaction có FOREIGN KEY hoãn kiểm tra nhưng chưa thỏa.

Tùy lỗi và tình huống, SQLite có thể **rollback chỉ câu lệnh** hoặc **tự rollback cả transaction**. Ứng dụng có thể dùng API **sqlite3_get_autocommit()** để kiểm tra liệu connection còn ở trong transaction hay không:

~~~text
sqlite3_get_autocommit(db) != 0
    → connection đang ở autocommit mode, không có transaction
      tường minh đang hoạt động.

sqlite3_get_autocommit(db) == 0
    → transaction vẫn đang hoạt động.
~~~

Đây là **API C của SQLite**, không phải một hàm SQL có thể gọi bằng SELECT trong mọi driver. Driver khác cần dùng API/metadata tương ứng để nhận biết tình trạng giao dịch.

### 13.1. SQLITE_BUSY khi COMMIT

Một tình huống SQLite có thể trả **SQLITE_BUSY** khi COMMIT không lấy được khóa cần thiết. Trong trường hợp này, transaction **có thể vẫn đang hoạt động**, và COMMIT có thể được thử lại khi điều kiện khóa đã thay đổi.

**Không tự suy luận rằng mọi COMMIT thất bại trong SQLite đã rollback transaction.** Cần kiểm tra lỗi, connection và trạng thái; logic retry phù hợp với hoàn cảnh.

### 13.2. Deferred foreign key

Với ràng buộc FOREIGN KEY được trì hoãn đến COMMIT, nếu lúc COMMIT còn vi phạm, SQLite có thể **từ chối COMMIT nhưng vẫn giữ transaction mở** để ứng dụng sửa dữ liệu hoặc rollback.

Đây là lý do nữa cho thấy “COMMIT lỗi” không có một ý nghĩa duy nhất là **đã hủy mọi thay đổi**.

## 14. Oracle Database: lỗi statement thường không hủy transaction

Oracle có cơ chế **statement-level atomicity**: mỗi câu DML có thể được rollback về **implicit savepoint** khi câu lệnh thất bại. Nhiều lỗi như UNIQUE violation thường làm **câu lệnh hiện tại bị hủy**, trong khi những câu lệnh thành công trước đó **vẫn thuộc transaction chưa COMMIT**.

### 14.1. Ví dụ Oracle

~~~sql
-- Ví dụ Oracle, bảng oracle_tx_demo giả định đã tồn tại:
-- CREATE TABLE oracle_tx_demo (
--     id NUMBER PRIMARY KEY,
--     note VARCHAR2(100)
-- );

INSERT INTO oracle_tx_demo(id, note)
VALUES (10, 'Co san');
COMMIT;

INSERT INTO oracle_tx_demo(id, note)
VALUES (11, 'Truoc loi');

-- Cố ý vi phạm PRIMARY KEY, thường ORA-00001.
INSERT INTO oracle_tx_demo(id, note)
VALUES (10, 'Trung id');

-- Câu lệnh sau có thể chạy trên transaction còn mở.
INSERT INTO oracle_tx_demo(id, note)
VALUES (12, 'Sau loi');

ROLLBACK;
~~~

Sau ROLLBACK, hàng id = 11 và 12 chưa COMMIT bị hủy; hàng id = 10 đã COMMIT trước đó vẫn tồn tại.

Điểm khác PostgreSQL: trong trường hợp lỗi UNIQUE thông thường, Oracle **không mặc định chặn toàn bộ các câu SQL tiếp theo trong transaction chỉ vì một DML gặp lỗi**.

**Nhưng không nên COMMIT những bước còn lại nếu nghiệp vụ yêu cầu all-or-nothing.** Oracle cho phép về mặt kỹ thuật không đồng nghĩa ứng dụng được phép ghi nhận một giao dịch thiếu bước bắt buộc.

### 14.2. SAVEPOINT trong Oracle

~~~sql
SAVEPOINT before_optional_step;

-- DML tùy chọn...

ROLLBACK TO SAVEPOINT before_optional_step;
~~~

Oracle hỗ trợ savepoint tường minh để hủy các thay đổi sau điểm lưu. Cũng có thể **ROLLBACK** toàn giao dịch. Không lẫn **rollback của một statement lỗi** với **rollback về savepoint do ứng dụng đặt** và **rollback toàn bộ transaction**.

### 14.3. DDL thường implicit COMMIT

Trong Oracle, nhiều câu DDL có cơ chế **implicit COMMIT** trước và, khi DDL thành công, sau thao tác DDL. Điều này có thể xác nhận những DML trước đó ngoài ý định nếu nhà phát triển trộn thay đổi schema với transaction nghiệp vụ.

Ví dụ, đừng dựa vào:

~~~text
INSERT dữ liệu nghiệp vụ
CREATE TABLE mới
ROLLBACK
~~~

để giả định INSERT ban đầu chắc chắn được rollback. Ranh giới giao dịch với DDL của Oracle khác PostgreSQL. Nên tách **migration** và **DML nghiệp vụ** thành quy trình riêng.

### 14.4. PL/SQL và xử lý exception

Trong PL/SQL, một exception có thể được bắt bằng **EXCEPTION WHEN ... THEN ...**. Việc bắt exception cho phép chương trình chọn tiếp tục, rollback về savepoint hoặc ném lỗi tiếp, nhưng **không tự bảo đảm một transaction đang ở trạng thái nghiệp vụ hợp lệ**.

Khi một PL/SQL block được gọi như một câu lệnh từ client và lỗi bị truyền ra ngoài, quy tắc rollback ở mức **statement/call** có thể ảnh hưởng những thay đổi do cả block thực hiện. Vì vậy cần phân biệt:

- Một câu SQL DML lỗi trong block nhưng được bắt.
- Cả block thất bại và trả lỗi ra client.
- Giao dịch lớn của client đã chứa công việc trước khi gọi block.

**Không kết luận rằng bắt được exception có nghĩa mọi DML trước đó đã được COMMIT hoặc đều đã bị rollback.** Phải xem transaction boundary và điểm rollback thực tế.

## 15. Bảng so sánh trọng tâm giữa các hệ quản trị

Bảng sau tóm lược **trường hợp lỗi DML/ràng buộc thông thường trong transaction tường minh**, không áp dụng vô điều kiện cho deadlock, mất kết nối hay mọi mức lỗi.

| Hệ quản trị | Sau lỗi UNIQUE thông thường | Có thể gửi DML tiếp trong transaction đó? | Phục hồi điển hình |
| --- | --- | --- | --- |
| **PostgreSQL** | Transaction vào **failed/aborted** | **Không**, trước khi rollback thích hợp | ROLLBACK toàn bộ hoặc ROLLBACK TO SAVEPOINT đã đặt trước lỗi |
| **MySQL 8.0 / InnoDB** | Thường rollback **câu lệnh lỗi** | **Thường có**, nếu lỗi không làm hủy toàn transaction | Ứng dụng quyết định ROLLBACK/tiếp tục, có thể dùng SAVEPOINT |
| **SQL Server XACT_ABORT OFF** | Một số lỗi chỉ làm statement thất bại | **Có thể**, khi **XACT_STATE() = 1** | TRY...CATCH, kiểm tra XACT_STATE, ROLLBACK theo chính sách |
| **SQL Server XACT_ABORT ON** | Nhiều runtime errors làm transaction **uncommittable** hoặc hủy | **Không** nếu XACT_STATE = -1 | ROLLBACK toàn bộ; xử lý trường hợp XACT_STATE = 0 |
| **SQLite ABORT thông thường** | Hủy **câu lệnh hiện tại** | **Thường có**, nếu transaction vẫn hoạt động | ROLLBACK/tiếp tục có kiểm soát; xem loại lỗi |
| **Oracle Database** | Thường rollback **câu lệnh lỗi** | **Thường có** | Ứng dụng quyết định ROLLBACK/tiếp tục; SAVEPOINT |

Các ngoại lệ không được bỏ qua:

- **MySQL InnoDB deadlock**: thường rollback **toàn transaction**.
- **SQL Server deadlock**: transaction nạn nhân thường bị rollback.
- **PostgreSQL serialization failure/deadlock**: nên retry **toàn transaction** sau rollback.
- **SQLite lỗi tài nguyên/COMMIT**: cần kiểm tra transaction có còn hoạt động hay không.
- **DDL có implicit COMMIT** trên MySQL/Oracle có thể thay đổi ranh giới giao dịch.
- **Mất kết nối**: trạng thái COMMIT có thể không biết chắc ở phía client, đòi hỏi đối soát.

## 16. Một lỗi trong một statement nhiều hàng

Không chỉ trạng thái transaction sau lỗi quan trọng: còn phải hỏi **trong một câu SQL gồm nhiều hàng, các hàng trước khi lỗi có được giữ hay không?**

Ví dụ ý tưởng:

~~~sql
INSERT INTO target_table (id, amount)
VALUES
    (1, 100),
    (2, 200),
    (1, 300);
~~~

Dòng thứ ba trùng id = 1 theo PRIMARY KEY. Trong nhiều RDBMS và cấu hình thông thường, một statement DML có tính atomicity: lỗi làm **không áp dụng các thay đổi của toàn statement**, dù các hàng đầu đã được xét.

Nhưng SQLite **INSERT OR FAIL** có thể giữ những thay đổi đã thực hiện với các hàng trước lỗi **ngay trong cùng statement**, khác với mặc định ABORT. Ngoài ra, các cơ chế bulk load đặc thù, bảng nontransactional hoặc tùy chọn error handling có thể tạo hành vi khác.

Do đó, phân biệt:

1. **Atomicity của một statement**.
2. **Atomicity của transaction nhiều statement**.
3. **Chính sách của batch import** có cho phép bỏ qua từng hàng lỗi hay không.

Một công cụ import có báo “đã nhận 100 hàng, 3 hàng lỗi” không đủ để kết luận **100 hàng đã nằm trong bảng chính** hoặc **transaction đã COMMIT**, nếu chưa biết ngữ nghĩa của công cụ và engine.

## 17. SAVEPOINT: so sánh thao tác phục hồi

| Hệ quản trị | Tạo savepoint | Rollback về savepoint | Điểm cần nhớ |
| --- | --- | --- | --- |
| PostgreSQL | SAVEPOINT s | ROLLBACK TO SAVEPOINT s | Sau lỗi trong transaction, rollback tới savepoint phù hợp mới được tiếp tục |
| MySQL/InnoDB | SAVEPOINT s | ROLLBACK TO SAVEPOINT s | Lỗi thông thường có thể vẫn cho tiếp tục; deadlock có thể hủy toàn transaction và savepoint |
| SQL Server | SAVE TRANSACTION s | ROLLBACK TRANSACTION s | Không dùng rollback đến savepoint khi XACT_STATE() = -1 |
| SQLite | SAVEPOINT s | ROLLBACK TO s | Cần hiểu transaction/savepoint còn tồn tại sau loại lỗi đang gặp |
| Oracle | SAVEPOINT s | ROLLBACK TO SAVEPOINT s | Thường có statement rollback ngầm; savepoint phục vụ phạm vi do ứng dụng chọn |

**SAVEPOINT không đồng nghĩa transaction lồng nhau độc lập.** Trong nhiều RDBMS, release hoặc rollback về savepoint không thể thay thế COMMIT của transaction ngoài.

### 17.1. Điểm lưu phải có trước lỗi

Nếu ứng dụng chỉ nghĩ tới SAVEPOINT **sau** khi transaction PostgreSQL đã aborted, không thể tạo một savepoint mới trong trạng thái failed rồi dùng nó để cứu các thay đổi trước đó.

Muốn khôi phục phần sau một bước tùy chọn, đặt SAVEPOINT **trước khi thực thi bước có rủi ro**.

### 17.2. ROLLBACK TO không khôi phục mọi tài nguyên ngoài database

SAVEPOINT có thể rollback dữ liệu SQL của transaction theo cơ chế hệ, nhưng **không xóa email đã gửi**, **không thu hồi một HTTP request đã hoàn tất**, và không bảo đảm các thao tác với hệ thống ngoài database được đảo ngược.

Đối với side effect ngoài database, cần thiết kế như **outbox**, idempotency key, hàng đợi hoặc tác vụ bù trừ phù hợp; không xem rollback DB là rollback mọi thứ trong thế giới thực.

## 18. Tại sao "có thể tiếp tục" chưa chắc "nên tiếp tục"?

Trở lại bài chuyển tiền:

~~~text
BEGIN
Trừ ví A 100.000
Ghi nhật ký chuyển tiền → ERROR
Cộng ví B 100.000
COMMIT
~~~

Giả sử MySQL/InnoDB hoặc Oracle cho phép chạy bước sau lỗi. Nếu ứng dụng tiếp tục và COMMIT mà thiếu nhật ký bắt buộc, transaction có thể đúng về **cân đối hai số dư** nhưng sai **điều kiện nghiệp vụ/kiểm toán**.

Trường hợp còn nguy hiểm hơn:

~~~text
Trừ ví A 100.000 → THÀNH CÔNG
Cộng ví B 100.000 → THẤT BẠI
COMMIT bước trước → TIỀN BỊ TRỪ, BÊN NHẬN KHÔNG ĐƯỢC CỘNG
~~~

Vì vậy cần định nghĩa:

- **Bước bắt buộc**: lỗi ở bất kỳ bước nào → ROLLBACK toàn bộ giao dịch.
- **Bước tùy chọn**: có thể rollback về savepoint và tiếp tục nếu thất bại đã được nghiệp vụ chấp nhận.
- **Lỗi tạm thời**: có thể rollback rồi retry cả giao dịch.
- **Lỗi dữ liệu cố định**: rollback, trả thông báo và yêu cầu sửa đầu vào; không retry vô hạn.

**Khả năng tiếp tục về mặt kỹ thuật là điều kiện cần, không phải quyết định nghiệp vụ để COMMIT.**

## 19. Deadlock và serialization failure: retry toàn transaction

Một deadlock hoặc serialization failure thường liên quan đến **cách nhiều transaction cạnh tranh trên cùng dữ liệu**. Nếu transaction bị hủy, chạy lại **chỉ câu INSERT cuối** sẽ không phục hồi những bước trước đã rollback.

### 19.1. Ví dụ thứ tự khóa ngược nhau

~~~text
Transaction T1                   Transaction T2
----------------                 ----------------
UPDATE ví 1                      UPDATE ví 2
giữ khóa ví 1                    giữ khóa ví 2
UPDATE ví 2 → chờ                UPDATE ví 1 → chờ
                  \             /
                       DEADLOCK
~~~

Một cách giảm nguy cơ là khi cần khóa hai ví, các transaction cố gắng **khóa theo thứ tự nhất quán** (chẳng hạn wallet_id tăng dần). Tuy nhiên, ngay cả khi đã thiết kế tốt, deadlock vẫn có thể xảy ra trong hệ thống phức tạp.

### 19.2. Retry từ đâu?

Với PostgreSQL **40001/40P01**, hoặc MySQL InnoDB/SQL Server deadlock khi transaction đã rollback, cách thường dùng là:

~~~text
1. ROLLBACK/dọn transaction đã lỗi nếu cần.
2. Chờ một khoảng ngắn có backoff.
3. Mở transaction mới.
4. Đọc lại dữ liệu cần thiết.
5. Chạy lại TOÀN BỘ logic nghiệp vụ trong transaction.
6. COMMIT nếu thành công.
7. Dừng sau số lần thử giới hạn và trả lỗi khi vẫn thất bại.
~~~

Không chỉ chạy lại một UPDATE bằng các tham số được tính từ snapshot cũ, vì dữ liệu có thể đã đổi trong lúc transaction trước thất bại.

### 19.3. Retry không phù hợp cho mọi lỗi

| Lỗi | Retry tự động ngay? | Lý do |
| --- | --- | --- |
| Deadlock | **Có thể**, toàn giao dịch, giới hạn lần thử | Cạnh tranh tạm thời |
| Serialization failure | **Có thể**, toàn giao dịch | Snapshot/cách sắp xếp giao dịch cần được tính lại |
| Duplicate key do tệp nhập trùng dữ liệu | **Thường không** | Retry không làm khóa tự biến mất |
| Foreign key thiếu hàng cha | **Không mặc định** | Cần sửa thứ tự/nguồn dữ liệu hoặc chờ dữ liệu cha có cơ chế rõ |
| CHECK(amount > 0) bị vi phạm | **Không** | Giá trị nguồn sai nghiệp vụ |
| Mất kết nối ngay sau COMMIT | **Không retry mù** | Phải xác minh lần trước đã COMMIT hay chưa |

Một retry an toàn còn cần kiểm soát việc gửi email, nhận thanh toán qua API hoặc phát sự kiện tới hệ thống khác; nếu đã phát bên ngoài transaction, lặp lại cả giao dịch có thể gây side effect trùng.

## 20. Mất kết nối và "commit outcome unknown"

Đây là trường hợp khác với một lỗi UNIQUE được trả rõ ràng.

~~~text
Ứng dụng                  Database
   |                         |
   |--------- COMMIT ------->|
   |                         | có thể COMMIT thành công
   |<---- kết nối bị đứt -----X
   |
   ? Không biết COMMIT đã được xác nhận hay chưa
~~~

Khi client không nhận được phản hồi, có thể:

1. COMMIT đã thành công nhưng phản hồi bị mất.
2. COMMIT chưa được thực hiện.
3. Database hoặc connection gặp lỗi trong quá trình xử lý.

**Không thể kết luận “ứng dụng thấy exception” đồng nghĩa “giao dịch chắc chắn rollback”.**

### 20.1. Dùng khóa idempotency để đối soát

Ví dụ mỗi yêu cầu chuyển tiền có **transfer_request_id duy nhất**:

~~~sql
-- Ví dụ schema PostgreSQL cho hệ xử lý thanh toán:
CREATE TABLE transfer_requests (
    transfer_request_id TEXT PRIMARY KEY,
    from_wallet_id BIGINT NOT NULL,
    to_wallet_id BIGINT NOT NULL,
    amount_vnd NUMERIC(18, 2) NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL
);
~~~

Đây là **ví dụ mô hình**, không chạy trên bảng tạm tx_demo_wallets vì kiểu khóa và nghiệp vụ sản xuất chưa được thiết kế đầy đủ.

Nếu giao dịch tạo/cập nhật transfer_request_id **cùng transaction** với chuyển tiền, sau lỗi kết nối, ứng dụng có thể truy vấn lại theo **transfer_request_id** để xem yêu cầu đã được ghi nhận hay chưa. Khi retry, dùng cùng idempotency key và quy tắc xử lý bản ghi đã tồn tại thay vì sinh một ID hoàn toàn mới.

**Idempotency không tự giải quyết mọi phân tán**: các hệ bên ngoài như ngân hàng/nhà cung cấp thanh toán cũng cần cơ chế idempotency, đối soát và trạng thái phù hợp.

## 21. Xử lý lỗi ở ứng dụng JDBC

Với Java, JDBC cho phép kiểm soát transaction thông qua **Connection**:

~~~java
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
~~~

Mẫu an toàn khi **mọi bước đều bắt buộc**:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public class WalletService {
    public void transfer(DataSource dataSource) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                // Bước 1: trừ số dư với điều kiện đủ tiền.
                // Bước 2: ghi nhật ký/chuyển tiền.
                // Bước 3: cộng số dư bên nhận.
                // Mỗi bước dùng PreparedStatement và kiểm tra số hàng đổi.

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đây là **khung điều khiển transaction**, không phải hàm chuyển tiền chạy hoàn chỉnh vì chưa có các PreparedStatement nghiệp vụ. Điểm cốt lõi là **commit chỉ khi các bước bắt buộc đều hoàn tất**. Khi có exception, chủ động rollback trước khi trả connection về pool.

### 21.1. Không đặt commit trong finally

Mẫu **nguy hiểm**:

~~~java
try {
    // nhiều SQL
} catch (SQLException e) {
    log(e);
} finally {
    connection.commit(); // Sai về chính sách all-or-nothing.
}
~~~

Với MySQL/Oracle, connection có thể vẫn cho COMMIT và lưu **các bước trước lỗi**; với PostgreSQL, transaction có thể aborted và COMMIT kết thúc bằng rollback; với SQL Server, trạng thái còn tùy XACT_STATE. Cùng một đoạn Java vì vậy có thể cho kết quả rất khác khi đổi database.

**Nơi gọi commit phải nằm trên nhánh xác nhận rằng mọi điều kiện nghiệp vụ đều đạt.**

### 21.2. JDBC savepoint

JDBC có API:

~~~java
java.sql.Savepoint checkpoint = connection.setSavepoint();

try {
    // Một thao tác tùy chọn có thể gây SQLException.
} catch (SQLException ex) {
    connection.rollback(checkpoint);
    // Chỉ tiếp tục nếu nghiệp vụ cho phép và rollback thành công.
}
~~~

Khả năng dùng savepoint phụ thuộc **driver, chế độ autocommit và trạng thái transaction của hệ**. Ví dụ, nếu SQL Server đang ở XACT_STATE = -1 thì không thể coi rollback về savepoint là phép phục hồi hợp lệ.

JDBC còn có **DatabaseMetaData.supportsSavepoints()** để biết khả năng hỗ trợ được driver báo cáo, nhưng hỗ trợ tính năng không đồng nghĩa **mọi lỗi đều có thể cứu bằng savepoint**.

### 21.3. Không tái sử dụng connection đang ở transaction lỗi

Đặc biệt với PostgreSQL, nếu một connection còn ở trạng thái transaction aborted và bị đưa lại vào pool mà không rollback, yêu cầu sau có thể nhận hàng loạt lỗi **25P02**.

Quy tắc vận hành:

- **Đóng/hoàn trả connection theo hợp đồng của DataSource/pool**, không giữ transaction ở trạng thái lửng.
- Sau exception, rollback hoặc đánh dấu connection không còn đáng tin nếu rollback thất bại.
- Không tùy tiện tiếp tục chạy SQL trên connection sau mất kết nối.
- Đặt timeout hợp lý, nhưng phân biệt **timeout của câu SQL**, **timeout lấy connection**, **timeout mạng**.
- Không log trực tiếp dữ liệu nhạy cảm hoặc nguyên câu SQL chứa token/password.

### 21.4. Chỉ nhìn exception không đủ để biết transaction state

SQLException có thể cung cấp:

~~~java
String sqlState = exception.getSQLState();
int vendorCode = exception.getErrorCode();
~~~

Nhưng **SQLSTATE/vendor code chỉ là thông tin chẩn đoán**. Muốn quyết định tiếp tục, phải xem loại database, trạng thái giao dịch, khả năng rollback, chính sách nghiệp vụ và việc driver có giữ connection hoạt động không.

**Đừng xây một catch chung “nếu SQLException thì bỏ qua, đi tiếp” cho nhiều loại RDBMS.**

## 22. Ứng dụng và framework quản lý transaction

Các framework Java như Spring có thể quản lý transaction theo annotation hoặc programmatic transaction. Cần hiểu vài nguyên tắc:

1. **Framework chỉ rollback theo quy tắc mà nó thấy được.** Nếu ứng dụng bắt exception rồi không báo lại hoặc không đánh dấu rollback-only, framework có thể nghĩ nghiệp vụ thành công và thử commit.
2. **Quy tắc rollback mặc định phụ thuộc loại exception và cấu hình.** Không mặc định mọi checked exception đều khiến transaction rollback theo cùng cách.
3. **Một lỗi SQL PostgreSQL đã làm transaction aborted** không được “chữa” chỉ bằng cách bắt exception trong Java.
4. **Rollback-only** là trạng thái điều khiển transaction của framework, không tự đồng nhất với trạng thái uncommittable của engine.
5. Một phương thức gọi nội bộ trong cùng đối tượng có thể không đi qua interceptor transaction của framework tùy cách proxy được dùng.

Ví dụ ý tưởng:

~~~java
@Transactional
public void importBatch() {
    insertParent();
    insertChildren();
    updateImportStatus();
}
~~~

Nếu insertChildren thất bại, kết quả đúng của batch phụ thuộc việc exception **được truyền ra/đánh dấu rollback** theo cấu hình và các thao tác có nằm trong cùng transaction thật sự hay không.

**Đừng dùng việc một hàm có annotation để bỏ qua việc hiểu transaction boundary, connection, isolation và hành vi sau lỗi của database.**

## 23. Xử lý lỗi trong Stored Procedure và trigger

Mọi RDBMS có cơ chế stored procedure/trigger riêng, có thể **bắt lỗi trong một phạm vi hẹp** hoặc làm thay đổi việc rollback.

### PostgreSQL: PL/pgSQL EXCEPTION

Trong PL/pgSQL, block có **EXCEPTION** được xử lý bằng cơ chế subtransaction. Những thay đổi database bên trong block thất bại có thể được rollback khi exception được bắt, trong khi transaction ngoài có thể tiếp tục.

Ví dụ:

~~~sql
DO $$
BEGIN
    BEGIN
        INSERT INTO tx_demo_receipts
            (receipt_id, wallet_id, amount_vnd, description)
        VALUES (10, 1, 10000, 'Thu ghi trung');
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'Receipt 10 da ton tai; bo qua buoc tuy chon';
    END;
END;
$$;
~~~

Block bên trong bắt **unique_violation**, nên lỗi được xử lý trong phạm vi block thay vì lan ra làm transaction ngoài aborted như một INSERT lỗi trực tiếp. Nhưng cách bắt theo loại lỗi **unique_violation** có thể che các UNIQUE khác nếu procedure không kiểm tra chính xác ràng buộc bị vi phạm.

**Cảnh báo:** không nên dùng **EXCEPTION WHEN OTHERS** rồi lặng lẽ bỏ qua mọi lỗi; nó có thể che mất lỗi dữ liệu hoặc vận hành cần xử lý nghiêm trọng.

### SQL Server: TRY...CATCH và trạng thái uncommittable

TRY...CATCH cho phép bắt nhiều lỗi trong T-SQL, nhưng **không làm XACT_STATE() = -1 trở lại 1**. Nếu transaction đã uncommittable, catch chỉ giúp **thực hiện rollback và báo lỗi**.

### Oracle: EXCEPTION và phạm vi rollback

PL/SQL có exception handlers; hành vi statement/call rollback và transaction phía client phải được hiểu cùng nhau. Một exception được bắt không tự COMMIT dữ liệu, và một exception thoát ra client có thể làm thay đổi phạm vi rollback của call.

### MySQL: HANDLER

MySQL có **DECLARE ... HANDLER** trong stored programs để xử lý điều kiện SQL. Handler có thể giúp ghi nhận/điều khiển lỗi, nhưng **không thay thế quyết định COMMIT/ROLLBACK**, đặc biệt với deadlock đã làm InnoDB rollback transaction.

**Điểm chung:** bắt lỗi về mặt ngôn ngữ lập trình không đồng nghĩa đã khôi phục transaction về trạng thái an toàn.

## 24. Quy trình ra quyết định sau khi một câu lệnh thất bại

Một sơ đồ xử lý thực tế:

~~~text
                  Câu SQL thất bại
                         |
                         v
             Ghi nhận lỗi ĐẦU TIÊN
              (SQLSTATE / vendor code)
                         |
                         v
            Connection còn hoạt động?
               /               \
             KHÔNG              CÓ
              |                 |
              v                 v
     Đối soát kết quả      Giao dịch còn tồn tại
     trước khi retry       và còn commit được?
                                |
             +------------------+------------------+
             |                  |                  |
        Đã rollback        Uncommittable      Committable
             |                  |                  |
             v                  v                  v
        Retry toàn         ROLLBACK toàn      Lỗi thuộc bước
        transaction        transaction?      tùy chọn hợp lệ?
        nếu thích hợp                           /       \
                                              CÓ      KHÔNG
                                               |         |
                                               v         v
                                       rollback tới    ROLLBACK
                                       savepoint       toàn bộ
                                       nếu hợp lệ
                                               |
                                               v
                                        Chỉ COMMIT nếu
                                        nghiệp vụ vẫn đúng
~~~

Một hàm ứng dụng đa cơ sở dữ liệu nên đưa ra **quyết định có kiểm soát**, không đơn giản chọn hành động dựa trên câu lệnh cuối cùng đã trả kết quả thành công.

### 24.1. Checklist ngắn khi xử lý sự cố

1. **Lỗi đầu tiên là gì?** PostgreSQL 25P02 có thể chỉ là lỗi dây chuyền.
2. **Transaction tường minh hay autocommit?** Có bước trước nào đã COMMIT chưa?
3. **Engine/cấu hình nào?** InnoDB, SQL Server XACT_ABORT ON/OFF, SQLite conflict algorithm?
4. **Trạng thái giao dịch hiện tại?** Có thể COMMIT được không, đã rollback tự động chưa?
5. **Bước lỗi có bắt buộc không?** Nếu có, thường rollback toàn bộ.
6. **Có savepoint hợp lệ từ trước không?** Nếu không, đừng giả định có thể rollback một phần.
7. **Lỗi có tạm thời không?** Deadlock/serialization thường có thể retry toàn đơn vị.
8. **Có side effect ngoài DB không?** Retry cần idempotency/đối soát.
9. **Log và audit đã ghi đúng trạng thái chưa?** Không ghi “thành công” trước khi COMMIT được xác nhận.

## 25. Tác động của timeout và hủy câu lệnh

**Timeout** có thể xảy ra ở nhiều tầng:

- **Statement timeout:** database hoặc client hủy một câu SQL quá lâu.
- **Lock wait timeout:** câu SQL chờ khóa quá lâu.
- **Query cancellation:** người dùng/ứng dụng chủ động gửi lệnh hủy.
- **Network timeout:** client không nhận phản hồi trong thời gian cấu hình.
- **Connection acquisition timeout:** ứng dụng không lấy được connection từ pool.

Chúng **không nhất thiết có cùng hậu quả giao dịch**.

### 25.1. PostgreSQL statement_timeout

~~~sql
BEGIN;

SET LOCAL statement_timeout = '100ms';

-- Thí nghiệm có thể bị hủy, không dùng trên môi trường sản xuất:
SELECT pg_sleep(1);

-- Sau query_canceled trong transaction tường minh,
-- transaction thường ở trạng thái aborted.

ROLLBACK;
~~~

Nếu pg_sleep bị hủy vì statement_timeout, PostgreSQL thường trả **57014** và transaction hiện tại cần được rollback thích hợp. **SET LOCAL** chỉ có hiệu lực trong transaction, và ROLLBACK đưa thiết lập đó về trạng thái trước giao dịch.

**Nếu client dừng script ở lỗi timeout**, cần gửi ROLLBACK trong cùng connection để dọn trạng thái. Đừng dựa vào một lệnh khác trong transaction để “thử xem có chạy không”.

### 25.2. Timeout ở tầng mạng khó xác định hơn

Nếu client mất kết nối khi COMMIT đang diễn ra, lỗi mạng không tự nói được giao dịch đã commit hay chưa. Phải dùng **định danh yêu cầu**, **bảng audit** hoặc cơ chế đối soát để biết kết quả thực, như phần 20.

## 26. Ví dụ nghiệp vụ: ghi đơn hàng và chi tiết đơn

Giả sử một transaction gồm:

~~~text
BEGIN
INSERT orders
INSERT order_items dòng 1
INSERT order_items dòng 2  ← lỗi FK tới SKU không tồn tại
UPDATE inventory
COMMIT
~~~

Quy tắc nghiệp vụ thường là: **không công bố một đơn hàng thiếu dòng hoặc đã trừ tồn kho không khớp**.

### PostgreSQL

Lỗi FOREIGN KEY có thể làm transaction aborted. Ứng dụng nên **ROLLBACK toàn bộ**. Dù có savepoint, không nên rollback riêng dòng 2 rồi COMMIT đơn thiếu chi tiết nếu không có chính sách chấp nhận đơn một phần.

### MySQL/InnoDB

Lỗi FK của một statement có thể để transaction còn hoạt động, nhưng chính sách vẫn nên **ROLLBACK toàn bộ** nếu đơn phải hoàn chỉnh. Khả năng tiếp tục kỹ thuật **không** phải phép cho phép lưu đơn thiếu dòng.

### SQL Server

Trong TRY...CATCH, kiểm tra XACT_STATE(); nếu -1 bắt buộc full rollback; ngay cả nếu 1, **nghiệp vụ cũng yêu cầu full rollback**.

### Oracle/SQLite

Nhiều lỗi statement-level có thể không hủy transaction, nhưng ứng dụng phải **chủ động rollback** nếu tính nhất quán của đơn yêu cầu all-or-nothing.

**Bài học xuyên hệ:** atomicity đúng phải được thiết kế theo **đơn vị nghiệp vụ**, không chỉ dựa vào “lệnh SQL sau lỗi có chạy được không”.

## 27. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Gặp 25P02 rồi chỉ retry câu lệnh vừa lỗi | 25P02 là trạng thái PostgreSQL đã aborted | Tìm lỗi gốc, rollback rồi quyết định retry |
| Gọi COMMIT trong finally dù có SQLException | MySQL/Oracle có thể commit một phần | Chỉ commit sau khi mọi bước bắt buộc thành công |
| Thấy MySQL chạy câu SQL sau lỗi nên nghĩ transaction an toàn | Statement có thể lỗi mà transaction vẫn mở | Phân loại lỗi và rollback theo nghiệp vụ |
| Nghĩ mọi deadlock chỉ rollback statement | InnoDB/SQL Server deadlock thường rollback cả transaction | Retry toàn transaction từ đầu |
| Dùng SQL Server @@TRANCOUNT > 0 để luôn COMMIT | Không phát hiện uncommittable transaction | Kiểm tra XACT_STATE() |
| Giả định XACT_ABORT ON luôn trả -1 | Một số lỗi đã rollback, trạng thái 0; loại lỗi khác nhau | Xử lý 1, -1 và 0 |
| Dùng SQL Server ROLLBACK savepoint khi XACT_STATE = -1 | Transaction đã bị doomed | Full ROLLBACK |
| Tạo PostgreSQL savepoint sau khi transaction đã aborted | Không thể thêm savepoint trong failed transaction | Đặt savepoint trước bước có thể lỗi |
| Dùng RELEASE SAVEPOINT sau lỗi để “phục hồi” | RELEASE không rollback thay đổi lỗi | ROLLBACK TO SAVEPOINT trước |
| Coi SQLite INSERT OR REPLACE là UPDATE | Có thể delete rồi insert, ảnh hưởng FK/trigger | Dùng UPSERT hoặc UPDATE đúng nghĩa |
| Nghĩ SQLite luôn giữ transaction sau mọi lỗi | Một số lỗi tài nguyên có thể tự rollback | Kiểm tra trạng thái connection |
| Nghĩ COMMIT SQLite lỗi là chắc chắn rollback | SQLITE_BUSY/hoãn FK có thể giữ transaction mở | Xem lỗi và trạng thái trước retry/rollback |
| Nghĩ Oracle lỗi DML tự rollback mọi thao tác trước | Thường chỉ statement lỗi bị rollback | Chủ động ROLLBACK nếu cần all-or-nothing |
| Chen DDL vào MySQL/Oracle business transaction | DDL có thể implicit COMMIT | Tách migration khỏi transaction nghiệp vụ |
| SELECT NOT EXISTS rồi INSERT trong hai worker | Race condition | UNIQUE và cơ chế upsert/khóa phù hợp |
| Retry chỉ câu UPDATE cuối sau serialization failure | Transaction cũ đã bị hủy; dữ liệu cần đọc lại | Retry toàn bộ đơn vị |
| Retry request thanh toán không có idempotency key | Có thể gửi yêu cầu bên ngoài hai lần | Dùng định danh yêu cầu và đối soát |
| Ghi audit thành công trước COMMIT | Audit và bảng nghiệp vụ có thể lệch | Ghi trạng thái phù hợp sau khi transaction xác nhận |
| Bắt exception rồi không ném lại/đánh dấu rollback | Framework có thể vẫn thử COMMIT | Xử lý chính sách rollback rõ ràng |
| Trả connection PostgreSQL aborted về pool | Request sau lỗi 25P02 dây chuyền | Rollback/reset connection trước khi hoàn trả |

## 28. Bài tập thực hành

Các bài dùng bảng tạm **tx_demo_wallets** và **tx_demo_receipts** từ phần 4 cho PostgreSQL, trừ khi câu hỏi chỉ định hệ khác. Với thí nghiệm cố ý lỗi, chạy từng câu trong một transaction của cùng connection và cuối cùng dùng **ROLLBACK** để không thay đổi dữ liệu gốc.

1. Tạo hai bảng tạm theo phần 4. Ghi số dư ví 1 và ví 2 trước khi thử các transaction.
2. Trong BEGIN, trừ ví 1 100.000, sau đó INSERT receipt_id = 10. Ghi nhận SQLSTATE lỗi đầu tiên.
3. Sau lỗi ở bài 2, thử SELECT COUNT(*) từ tx_demo_wallets trong cùng transaction. PostgreSQL trả mã trạng thái gì?
4. Dùng ROLLBACK, đọc lại hai số dư. Vì sao phép trừ hợp lệ trước lỗi không còn?
5. Đặt SAVEPOINT trước INSERT receipt_id = 10, cố ý gây lỗi, rồi chạy **ROLLBACK TO SAVEPOINT**. Có thể SELECT tiếp không?
6. Trong cùng transaction của bài 5, INSERT receipt_id = 11 sau khi rollback đến savepoint. Vì sao hành động này được phép?
7. So sánh **ROLLBACK TO SAVEPOINT** với **ROLLBACK toàn bộ** khi đã UPDATE ví trước savepoint.
8. Giải thích vì sao **RELEASE SAVEPOINT** không thay thế rollback về savepoint sau một lỗi PostgreSQL.
9. Trong PostgreSQL, phân biệt lỗi **23505** và **25P02**: lỗi nào cần ghi làm nguyên nhân gốc?
10. Thử statement_timeout với pg_sleep(1) trong transaction và SET LOCAL statement_timeout = '100ms'. Nêu điều cần làm sau lỗi query_canceled.
11. Trình bày vì sao hai UPDATE chuyển tiền không nên chạy dưới hai câu lệnh autocommit độc lập.
12. Mô tả MySQL/InnoDB khi INSERT trùng khóa trong transaction: những INSERT hợp lệ trước lỗi có thể còn tồn tại không?
13. Nếu MySQL sau lỗi duplicate key vẫn cho INSERT khác thành công, liệu nghiệp vụ chuyển tiền nên COMMIT không? Vì sao?
14. So sánh MySQL error **1062**, **1213** và **1205** theo nguyên nhân và phạm vi rollback thông dụng.
15. Nêu tác động của **innodb_rollback_on_timeout** và vì sao không được coi mọi lock wait timeout giống nhau.
16. Trong SQL Server, nêu ý nghĩa của **XACT_STATE() = 1, -1, 0** và hành động xử lý tương ứng.
17. Vì sao **@@TRANCOUNT = 1** chưa đủ để khẳng định SQL Server COMMIT được?
18. Viết khung TRY...CATCH của SQL Server dùng **SET XACT_ABORT ON**, ROLLBACK khi XACT_STATE() <> 0 và THROW.
19. Giải thích tại sao SQL Server không thể rollback về SAVE TRANSACTION khi XACT_STATE() = -1.
20. Với SQLite, phân biệt **INSERT OR ABORT**, **INSERT OR FAIL**, **INSERT OR IGNORE**, **INSERT OR REPLACE** và **INSERT OR ROLLBACK**.
21. Vì sao **INSERT OR REPLACE** không phải bản dịch an toàn của PostgreSQL ON CONFLICT DO UPDATE?
22. Nếu SQLite trả SQLITE_BUSY ở COMMIT, có thể kết luận transaction đã rollback không? Cần kiểm tra điều gì?
23. Với Oracle, giải thích statement-level rollback và tại sao một DML lỗi thường không chặn mọi câu DML tiếp theo.
24. Mô tả lý do nên tách DDL khỏi transaction dữ liệu khi dùng MySQL hoặc Oracle.
25. Viết pseudocode JDBC: bắt SQLException, gọi rollback, gắn lỗi rollback làm suppressed exception, rồi ném lại lỗi ban đầu.
26. Đề xuất chính sách retry cho deadlock/serialization failure với tối đa ba lần và backoff; tại sao phải chạy lại toàn transaction?
27. Giả sử ứng dụng mất kết nối ngay sau khi gửi COMMIT chuyển tiền. Vì sao không nên gửi yêu cầu mới với transfer_request_id khác?
28. Một tác vụ gửi email thành công ở giữa transaction, rồi transaction rollback. Email có bị rollback không? Thiết kế cách tránh gửi trùng.
29. Một đơn hàng có 3 dòng item, dòng thứ 3 vi phạm FK. Đề xuất chính sách rollback ở PostgreSQL, MySQL, SQL Server, SQLite và Oracle.
30. Mô tả tình huống lỗi được phép bỏ qua bằng savepoint và tình huống **không được bỏ qua** dù savepoint có thể phục hồi kỹ thuật.

### Câu hỏi tự kiểm tra

**Câu 1.** PostgreSQL có cho chạy một UPDATE bình thường sau lỗi UNIQUE trong transaction tường minh chưa được rollback không?

**Đáp án:** **Thường không.** Transaction ở trạng thái aborted và câu sau nhận **25P02**. Cần ROLLBACK hoặc ROLLBACK TO SAVEPOINT hợp lệ.

**Câu 2.** 25P02 có nhất thiết là nguyên nhân gốc?

**Đáp án:** **Không.** Nó thường phản ánh transaction đã lỗi từ một câu trước. Cần tìm lỗi đầu tiên, ví dụ 23505.

**Câu 3.** Nếu MySQL/InnoDB vẫn cho phép INSERT sau một lỗi duplicate key, có nên COMMIT một giao dịch chuyển tiền?

**Đáp án:** **Không nếu bước lỗi là bắt buộc.** Khả năng tiếp tục không làm phần nghiệp vụ thiếu bước trở nên đúng.

**Câu 4.** SQL Server XACT_STATE() = -1 có COMMIT được không?

**Đáp án:** **Không.** Đây là transaction uncommittable; cần ROLLBACK toàn bộ.

**Câu 5.** XACT_STATE() = 1 có nghĩa ứng dụng phải COMMIT không?

**Đáp án:** **Không.** Nó chỉ nói transaction còn committable về mặt kỹ thuật; chính sách nghiệp vụ có thể vẫn yêu cầu ROLLBACK.

**Câu 6.** SQLite INSERT OR FAIL có giống ABORT về thay đổi từ các hàng trước trong cùng một statement không?

**Đáp án:** **Không.** FAIL có thể giữ các thay đổi của những hàng đã xử lý trước lỗi trong cùng statement; ABORT thường hủy thay đổi của cả statement.

**Câu 7.** Một DML lỗi UNIQUE ở Oracle có thường tự rollback tất cả DML trước đó trong transaction không?

**Đáp án:** **Không.** Oracle thường rollback riêng statement lỗi, còn transaction và DML trước đó vẫn tồn tại tới khi COMMIT/ROLLBACK.

**Câu 8.** SAVEPOINT có làm email đã gửi hoặc API bên ngoài tự hủy khi ROLLBACK TO không?

**Đáp án:** **Không.** Rollback database không tự đảo ngược những side effect đã diễn ra ngoài DB.

**Câu 9.** Khi transaction đã bị rollback do deadlock, chỉ retry câu SQL cuối đủ chưa?

**Đáp án:** **Chưa.** Thường phải mở transaction mới, đọc lại dữ liệu và chạy lại toàn bộ nghiệp vụ nếu điều kiện retry cho phép.

**Câu 10.** Client nhận lỗi mạng sau khi gửi COMMIT có chứng minh transaction chưa COMMIT không?

**Đáp án:** **Không.** Kết quả COMMIT có thể chưa rõ với client; cần đối soát bằng định danh yêu cầu hoặc trạng thái bền vững.

## 29. Ghi nhớ cốt lõi

**Hành vi sau lỗi của giao dịch không đồng nhất giữa các RDBMS.** PostgreSQL thường đưa transaction tường minh vào trạng thái **aborted** sau lỗi và yêu cầu **ROLLBACK** hoặc **ROLLBACK TO SAVEPOINT**. MySQL/InnoDB và Oracle có nhiều trường hợp **chỉ rollback statement lỗi**, còn transaction có thể tiếp tục. SQL Server phụ thuộc **XACT_ABORT, loại lỗi và XACT_STATE()**. SQLite có các **conflict resolution algorithms** và những lỗi tài nguyên có thể thay đổi tình trạng transaction.

Một lỗi có thể xảy ra ở **cấp statement, cấp transaction hoặc cấp connection**. Vì vậy, trước khi tiếp tục, phải biết **đã rollback tới đâu, transaction có còn hoạt động không và có còn COMMIT được không**.

**Không đánh đồng “có thể tiếp tục SQL” với “nên COMMIT”.** Nếu một bước bắt buộc trong nghiệp vụ thất bại, chính sách an toàn thường là **ROLLBACK toàn bộ**, dù database vẫn cho chạy câu sau. SAVEPOINT chỉ phù hợp khi phần bị hủy **thật sự tùy chọn** và giao dịch còn ở trạng thái cho phép phục hồi.

Cuối cùng, **retry toàn transaction** cho lỗi cạnh tranh tạm thời như deadlock/serialization failure khi có thể; không retry mù lỗi dữ liệu cố định, và không giả định mất phản hồi COMMIT đồng nghĩa rollback. Đặt ranh giới giao dịch, logging, idempotency và kiểm soát connection rõ ràng để cùng một nghiệp vụ vẫn đúng khi chạy trên những hệ quản trị khác nhau.
