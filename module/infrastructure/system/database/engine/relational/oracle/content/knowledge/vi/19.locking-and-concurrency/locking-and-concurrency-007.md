# Deadlock, nguyên nhân theo thứ tự khóa và phạm vi rollback trong Oracle

Hai transaction có thể cùng cần sửa nhiều hàng. Nếu chúng lấy khóa theo thứ tự ngược nhau, mỗi transaction có thể giữ một khóa và chờ khóa còn lại. Không transaction nào tiếp tục được: đó là **deadlock**. Oracle tự phát hiện chu trình chờ này và báo lỗi ORA-00060 cho một statement liên quan.

Điểm dễ gây lỗi trong ứng dụng là phạm vi rollback. Khi Oracle phát hiện deadlock, nó rollback statement được chọn để phá chu trình; điều đó **không đồng nghĩa toàn bộ transaction của session nhận lỗi đã tự rollback**. Các DML thành công trước đó trong transaction có thể vẫn đang chờ commit và các khóa tương ứng vẫn được giữ. Nếu các câu lệnh thuộc cùng một đơn vị công việc nghiệp vụ, ứng dụng thường phải rollback toàn transaction trước khi thử lại.

Bài học thuộc nhóm **Khóa và đồng thời** của Database Engine Relational Oracle. Nội dung giải thích cách hình thành chu trình khóa, những nguyên nhân thường gặp, quy tắc thứ tự khóa nhất quán, cách đọc deadlock graph, phạm vi statement rollback và transaction rollback, cùng bài lab hai session có thể tái hiện ORA-00060.

Sau bài này, bạn có thể:

- Phân biệt blocking thông thường với deadlock.
- Mô tả chu trình chờ khóa và nhận biết nguyên nhân do thứ tự truy cập hàng.
- Hiểu vì sao hai câu SQL riêng lẻ đúng vẫn có thể deadlock khi chạy đồng thời.
- Tổ chức thứ tự khóa nhất quán giữa các transaction và các đường gọi trong ứng dụng.
- Nhận diện deadlock liên quan đến nhiều bảng, trigger, khóa ngoại và index.
- Hiểu chính xác Oracle rollback statement nào và phần nào của transaction còn tồn tại.
- Dùng deadlock trace/graph và thông tin session để tìm nguyên nhân.
- Thiết kế retry có giới hạn, rollback toàn đơn vị công việc và chống request trùng.
- Tái hiện, xử lý và kiểm tra deadlock bằng hai session Oracle.

> **Phạm vi ví dụ:** Cú pháp theo Oracle Database 19c. Tất cả bảng có hậu tố _LAB chỉ dùng trong schema thực hành riêng. Không cố tình tạo deadlock trên hệ thống production. Thử nghiệm cần hai session độc lập, không phải hai tab dùng chung một connection.

## 1. Blocking và deadlock khác nhau thế nào?

### 1.1. Blocking: một session chờ session khác

Giả sử Session A cập nhật tài khoản 10 nhưng chưa COMMIT. Session B muốn cập nhật cùng tài khoản:

~~~sql
-- Session A
UPDATE account_lab
SET balance = balance - 10
WHERE account_id = 10;
-- Chua COMMIT.
~~~

~~~sql
-- Session B
UPDATE account_lab
SET balance = balance + 20
WHERE account_id = 10;
-- B cho A giai phong khoa.
~~~

Đây là blocking. A đang giữ khóa hàng; B chờ A COMMIT hoặc ROLLBACK. Nếu A kết thúc transaction, B có thể tiếp tục. Không có chu trình chờ nên chưa phải deadlock.

### 1.2. Deadlock: các session chờ lẫn nhau theo chu trình

Deadlock xảy ra khi A chờ tài nguyên do B giữ, đồng thời B chờ tài nguyên do A giữ:

~~~text
Session A                         Session B
---------                         ---------
Khoa hang 1                       Khoa hang 2
       |                                  |
       v                                  v
Can hang 2                         Can hang 1
       |                                  |
       +------------ cho nhau ------------+
                         |
                         v
                      DEADLOCK
                         |
                         v
             Oracle phat hien ORA-00060
~~~

Không có session nào có thể tự tiến triển nếu không một phần khóa được giải phóng. Oracle phát hiện chu trình và rollback một statement để phá deadlock. Vì thế deadlock thường được phát hiện và trả lỗi thay vì để các session chờ vô hạn.

### 1.3. So sánh nhanh

| Tình huống | Blocking | Deadlock |
| --- | --- | --- |
| Có session chờ khóa | Có | Có |
| Có chu trình chờ | Không | Có |
| Có thể tự hết khi blocker commit/rollback | Có | Chu trình cần được phá |
| Lỗi đặc trưng | Có thể không có lỗi; chờ đến khi timeout nếu được cấu hình | ORA-00060 |
| Hướng xử lý | Xác định blocker, rút ngắn transaction, chờ hoặc timeout hợp lý | Xác định chu trình, sửa thứ tự khóa, rollback/retry đúng phạm vi |

Một transaction chạy lâu có thể gây blocking mà không có deadlock. Ngược lại, deadlock có thể xảy ra rất nhanh khi hai session lấy khóa theo thứ tự đối nghịch.

## 2. Ví dụ kinh điển: cập nhật hai hàng theo thứ tự ngược

Giả sử bảng tài khoản có hai hàng:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 1 | 1.000 |
| 2 | 1.000 |

Session A chuyển tiền hoặc cập nhật theo thứ tự 1 rồi 2. Session B cập nhật theo thứ tự 2 rồi 1.

### 2.1. Các bước tạo deadlock

| Thứ tự | Session A | Session B |
| ---: | --- | --- |
| 1 | UPDATE hàng 1, giữ khóa 1 | |
| 2 | | UPDATE hàng 2, giữ khóa 2 |
| 3 | UPDATE hàng 2, chờ B | |
| 4 | | UPDATE hàng 1, chờ A |
| 5 | Oracle phát hiện chu trình và báo ORA-00060 cho một statement | |

Mỗi câu UPDATE đều hợp lệ khi chạy riêng. Vấn đề nằm ở thứ tự lấy khóa khi hai transaction chạy đồng thời.

### 2.2. Điều kiện hình thành deadlock

Một deadlock cần có chu trình phụ thuộc tài nguyên. Trong ví dụ:

- A giữ khóa trên hàng 1.
- B giữ khóa trên hàng 2.
- A yêu cầu hàng 2 mà B đang giữ.
- B yêu cầu hàng 1 mà A đang giữ.

Nếu A chỉ yêu cầu hàng 2 và B không bao giờ yêu cầu hàng 1, đó là blocking, không phải deadlock. Chu trình chỉ xuất hiện khi có đường chờ quay trở lại transaction ban đầu.

## 3. Oracle khóa những tài nguyên nào?

### 3.1. Row lock và transaction lock

Khi UPDATE hoặc DELETE một hàng, Oracle khóa hàng bị thay đổi. Khóa hàng được giữ cho đến khi transaction kết thúc bằng COMMIT hoặc ROLLBACK.

Oracle quản lý khóa hàng thông qua thông tin transaction và các cấu trúc khóa nội bộ. Trong các công cụ chẩn đoán, bạn thường gặp:

- TX enqueue: khóa liên quan transaction, thường xuất hiện trong tranh chấp hàng hoặc tài nguyên transaction.
- TM enqueue: khóa DML ở cấp bảng, phục vụ phối hợp truy cập bảng và bảo vệ các thao tác DML/DDL.

Không nên suy ra mọi TX wait đều là deadlock. Một TX wait có thể chỉ là blocking thông thường; phải xem chu trình và deadlock graph mới kết luận.

### 3.2. Khóa được giữ qua nhiều câu lệnh

~~~sql
UPDATE account_lab
SET balance = balance - 100
WHERE account_id = 1;

UPDATE account_lab
SET balance = balance + 100
WHERE account_id = 2;

-- Ca hai khoa van duoc giu den COMMIT hoac ROLLBACK.
~~~

Oracle không tự giải phóng khóa hàng sau khi câu UPDATE hoàn tất. Nếu transaction tiếp tục chạy thêm câu SQL, các khóa trước vẫn có thể còn được giữ.

Đây là lý do transaction dài làm tăng nguy cơ blocking và tạo điều kiện cho deadlock. Một transaction giữ càng nhiều tài nguyên càng có nhiều khả năng xung đột với transaction khác.

### 3.3. SELECT thông thường và SELECT FOR UPDATE

SELECT thông thường dùng read consistency và không lấy row lock giống UPDATE. SELECT FOR UPDATE chủ động khóa các hàng được chọn để bảo vệ quy trình đọc rồi cập nhật:

~~~sql
SELECT account_id, balance
FROM account_lab
WHERE account_id = 1
FOR UPDATE;
~~~

Nếu nhiều transaction dùng SELECT FOR UPDATE trên nhiều hàng, thứ tự khóa vẫn rất quan trọng. Việc thêm SELECT FOR UPDATE không tự loại bỏ deadlock; nếu hai session khóa cùng tập hàng theo thứ tự ngược nhau, deadlock vẫn có thể xảy ra.

## 4. Các nguyên nhân deadlock thường gặp

### 4.1. Hai transaction truy cập hàng theo thứ tự ngược nhau

Đây là nguyên nhân dễ nhận ra nhất:

~~~text
Flow A: row 10 -> row 20
Flow B: row 20 -> row 10
~~~

Ví dụ:

- Hai lệnh chuyển tiền A→B và B→A.
- Hai đơn hàng cùng trừ tồn kho của hai sản phẩm nhưng duyệt sản phẩm theo thứ tự khác nhau.
- Hai batch job cập nhật cùng nhóm bản ghi nhưng sắp xếp theo các khóa khác nhau.

**Cách xử lý:** chuẩn hóa thứ tự khóa theo một khóa ổn định, ví dụ account_id tăng dần, product_id tăng dần hoặc theo một thứ bậc tài nguyên thống nhất.

### 4.2. Truy cập nhiều bảng theo thứ tự khác nhau

Giả sử nghiệp vụ cập nhật CUSTOMER, ORDER và INVENTORY. Một luồng thực hiện:

~~~text
CUSTOMER -> ORDER -> INVENTORY
~~~

Luồng khác lại thực hiện:

~~~text
INVENTORY -> ORDER -> CUSTOMER
~~~

Nếu hai luồng giữ khóa ở các bảng khác nhau rồi yêu cầu khóa của nhau, có thể tạo chu trình chờ.

**Cách xử lý:** định nghĩa lock hierarchy dùng chung cho toàn ứng dụng. Mọi luồng phải tuân theo cùng thứ tự bảng/tài nguyên, kể cả khi một số bước nằm trong stored procedure khác.

### 4.3. Trigger hoặc procedure lấy thêm khóa ngoài dự kiến

Một câu UPDATE có thể kích hoạt trigger. Trigger lại cập nhật bảng audit, bảng tổng hợp hoặc bảng liên quan. Người gọi chỉ nhìn thấy một câu UPDATE, nhưng transaction thực tế đã lấy thêm khóa ở nhiều bảng.

Ví dụ:

~~~text
UPDATE ORDER
   |
   +--> trigger cập nhật CUSTOMER_STAT
   |
   +--> trigger ghi AUDIT_LOG
~~~

Nếu một luồng khác cập nhật CUSTOMER_STAT trước rồi mới cập nhật ORDER, thứ tự khóa giữa hai luồng không còn nhất quán.

**Cách xử lý:** lập sơ đồ các bảng bị chạm bởi trigger, cascade, procedure và package. Lock hierarchy phải bao gồm cả tài nguyên được truy cập gián tiếp.

### 4.4. Batch job xử lý các tập hàng giao nhau

Hai worker có thể nhận các nhóm bản ghi khác nhau lúc đầu nhưng sau đó cùng cập nhật một số tài nguyên phụ. Nếu mỗi worker xử lý các ID theo thứ tự khác nhau, deadlock có thể xảy ra.

Ví dụ:

- Worker A xử lý đơn 100 rồi 200.
- Worker B xử lý đơn 200 rồi 100.
- Cả hai cùng cập nhật tồn kho hoặc trạng thái đối soát.

**Cách xử lý:** phân vùng công việc theo khóa, sắp xếp ID nhất quán, tránh hai worker cùng sở hữu một nhóm nghiệp vụ và giữ transaction ngắn.

### 4.5. Khóa ngoại không có index phù hợp

Oracle không tự động tạo index trên cột khóa ngoại. Khi xóa hoặc thay đổi khóa ở bảng cha, nếu cột khóa ngoại phía bảng con không có index phù hợp, Oracle có thể cần khóa bảng con ở phạm vi rộng hơn để bảo vệ kiểm tra tham chiếu. Điều này làm tăng blocking và có thể góp phần vào deadlock với DML đồng thời trên bảng con.

Ví dụ:

~~~sql
CREATE TABLE order_header_lab (
    order_id NUMBER PRIMARY KEY
);

CREATE TABLE order_line_lab (
    line_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    CONSTRAINT fk_order_line_lab
        FOREIGN KEY (order_id)
        REFERENCES order_header_lab(order_id)
);
~~~

Nếu workload thường xuyên xóa/cập nhật khóa cha hoặc có DML đồng thời trên bảng con, hãy đánh giá index:

~~~sql
CREATE INDEX ix_order_line_order_id_lab
ON order_line_lab(order_id);
~~~

Index khóa ngoại thường giúp giảm phạm vi khóa và chi phí kiểm tra quan hệ. Tuy nhiên, nó không bảo đảm loại bỏ mọi deadlock; thứ tự khóa và các tài nguyên khác vẫn phải được kiểm soát.

### 4.6. Unique constraint và index entry

Hai transaction cùng thao tác các giá trị có liên quan đến unique index có thể phải chờ kết quả commit/rollback của nhau. Nếu mỗi transaction thay đổi nhiều khóa duy nhất hoặc nhiều bảng theo thứ tự khác nhau, các chờ đợi có thể kết hợp thành deadlock.

Không nên kết luận mọi ORA-00060 đều là hai UPDATE cùng một hàng. Deadlock graph có thể chỉ ra TX/TM enqueue hoặc tài nguyên index. Hãy đọc trace để xác định đối tượng thực sự.

### 4.7. DDL và DML tranh chấp

Các thao tác DDL cần khóa metadata/table ở những phạm vi nhất định. Nếu một session đang giữ DML lock và một session khác chạy DDL hoặc thao tác phụ thuộc vào metadata lock, có thể phát sinh chờ khóa phức tạp.

Không chạy DDL xen giữa các bước của transaction nghiệp vụ. Oracle DDL còn có implicit commit, nên đây vừa là vấn đề khóa vừa là vấn đề ranh giới transaction.

## 5. Quy tắc cốt lõi: thứ tự khóa nhất quán

### 5.1. Chọn một thứ tự toàn cục

Với nhiều tài nguyên, hãy định nghĩa một thứ tự cố định, chẳng hạn:

~~~text
1. CUSTOMER
2. ACCOUNT
3. ORDER
4. INVENTORY
5. LEDGER
6. OUTBOX
~~~

Mọi transaction cần nhiều loại tài nguyên phải lấy khóa theo cùng thứ tự. Nếu một luồng không cần CUSTOMER, nó có thể bắt đầu từ ACCOUNT; nhưng không được lấy ORDER rồi quay ngược lại CUSTOMER nếu luồng khác đang đi theo CUSTOMER → ORDER.

Thứ tự này là quy ước kiến trúc của ứng dụng, không phải thứ tự bắt buộc của Oracle. Nó phải được áp dụng ở mọi tầng: SQL trực tiếp, PL/SQL, trigger, batch và job nền.

### 5.2. Sắp xếp khóa hàng theo ID

Nếu một transaction cần khóa nhiều tài khoản, dùng account_id tăng dần trong mọi luồng. Với hai ID:

~~~text
min(account_id) -> max(account_id)
~~~

Nhờ vậy, chuyển A→B và chuyển B→A đều khóa cùng hai hàng theo cùng một thứ tự vật lý.

### 5.3. Ví dụ chuyển tiền khóa theo thứ tự tăng dần

Bảng lab:

~~~sql
CREATE TABLE deadlock_account_lab (
    account_id NUMBER PRIMARY KEY,
    account_name VARCHAR2(50 CHAR) NOT NULL,
    balance NUMBER(18,2) NOT NULL,
    CONSTRAINT ck_deadlock_balance_lab CHECK (balance >= 0)
);

INSERT INTO deadlock_account_lab VALUES (10, 'Account A', 1000);
INSERT INTO deadlock_account_lab VALUES (20, 'Account B', 1000);
COMMIT;
~~~

Procedure sau khóa cả hai hàng theo account_id tăng dần, bất kể hướng chuyển tiền:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_ordered_lab (
    p_from_id IN NUMBER,
    p_to_id   IN NUMBER,
    p_amount  IN NUMBER
) AS
    v_first_balance  NUMBER(18,2);
    v_second_balance NUMBER(18,2);
    v_from_balance   NUMBER(18,2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Amount must be positive');
    END IF;

    IF p_from_id = p_to_id THEN
        RAISE_APPLICATION_ERROR(-20002, 'Accounts must be different');
    END IF;

    -- Luon khoa account_id nho hon truoc.
    IF p_from_id < p_to_id THEN
        SELECT balance
        INTO v_first_balance
        FROM deadlock_account_lab
        WHERE account_id = p_from_id
        FOR UPDATE;

        SELECT balance
        INTO v_second_balance
        FROM deadlock_account_lab
        WHERE account_id = p_to_id
        FOR UPDATE;

        v_from_balance := v_first_balance;
    ELSE
        SELECT balance
        INTO v_first_balance
        FROM deadlock_account_lab
        WHERE account_id = p_to_id
        FOR UPDATE;

        SELECT balance
        INTO v_second_balance
        FROM deadlock_account_lab
        WHERE account_id = p_from_id
        FOR UPDATE;

        v_from_balance := v_second_balance;
    END IF;

    IF v_from_balance < p_amount THEN
        RAISE_APPLICATION_ERROR(-20003, 'Insufficient funds');
    END IF;

    UPDATE deadlock_account_lab
    SET balance = balance - p_amount
    WHERE account_id = p_from_id;

    UPDATE deadlock_account_lab
    SET balance = balance + p_amount
    WHERE account_id = p_to_id;
END;
/
~~~

Gọi procedure:

~~~sql
BEGIN
    transfer_ordered_lab(10, 20, 100);
END;
/

COMMIT;
~~~

Procedure không COMMIT. Transaction owner quyết định COMMIT khi toàn bộ đơn vị công việc hoàn tất hoặc ROLLBACK nếu có lỗi.

Điểm quan trọng: cả chuyển 10→20 và 20→10 đều khóa tài khoản 10 trước rồi 20. Nếu mọi đường cập nhật hai tài khoản đều tuân thủ quy tắc này, chúng không tạo chu trình do đảo thứ tự hai khóa đó.

### 5.4. Với nhiều hàng, không dựa vào thứ tự ngẫu nhiên

Một câu UPDATE nhiều hàng có thể được optimizer thực hiện theo access path và kế hoạch khác nhau khi index, thống kê hoặc dữ liệu thay đổi. Không nên dựa vào thứ tự vật lý tình cờ của một lần chạy để làm lock order.

Khi cần kiểm soát chặt, có thể:

- Chọn các khóa cần xử lý theo thứ tự ổn định.
- Khóa từng hàng theo thứ tự đó, hoặc dùng cursor FOR UPDATE được đọc theo khóa ổn định.
- Sau khi đã khóa đủ tập cần thiết, thực hiện các thay đổi.
- Đảm bảo mọi luồng khác dùng cùng thứ tự.

Việc khóa từng hàng có chi phí riêng; hãy cân nhắc số lượng hàng, index và độ dài transaction. Với tập rất lớn, phân vùng công việc hoặc thiết kế lại để giảm vùng giao nhau thường tốt hơn một transaction giữ hàng nghìn khóa.

## 6. Phạm vi rollback khi Oracle phát hiện deadlock

Đây là phần cần nhớ chính xác khi viết ứng dụng.

### 6.1. Oracle rollback statement gây deadlock, không tự động rollback toàn transaction

Khi Oracle phát hiện deadlock, nó chọn một statement tham gia chu trình và rollback statement đó để phá deadlock. Session nhận lỗi ORA-00060.

Các DML thành công trước statement bị rollback có thể vẫn còn trong transaction. Những khóa được lấy từ các statement trước đó cũng có thể vẫn được giữ.

Ví dụ:

~~~sql
UPDATE deadlock_account_lab
SET balance = balance - 10
WHERE account_id = 10;

-- Statement thu hai gap deadlock va nhan ORA-00060.
UPDATE deadlock_account_lab
SET balance = balance + 10
WHERE account_id = 20;
~~~

Nếu statement thứ hai là statement bị rollback, statement thứ nhất không tự động bị rollback theo. Transaction vẫn có thể đang mở.

### 6.2. Vì sao không nên chỉ bắt ORA-00060 rồi tiếp tục COMMIT?

Giả sử một nghiệp vụ cần:

1. Trừ số dư tài khoản A.
2. Cộng số dư tài khoản B.
3. Ghi lịch sử chuyển tiền.

Nếu bước 2 gặp deadlock và bị rollback, bước 1 có thể vẫn pending. Nếu ứng dụng bắt lỗi rồi COMMIT, số dư A có thể bị trừ mà B chưa được cộng và lịch sử chưa được ghi. Đó là trạng thái nghiệp vụ không hoàn chỉnh.

Với một đơn vị công việc cần atomicity, xử lý phù hợp thường là:

1. Bắt ORA-00060.
2. ROLLBACK toàn transaction.
3. Ghi nhận lỗi và thông tin tương quan ở ngoài transaction đã rollback nếu cần.
4. Chờ một khoảng backoff có giới hạn.
5. Bắt đầu transaction mới và chạy lại toàn bộ nghiệp vụ nếu có thể retry an toàn.

### 6.3. So sánh các phạm vi rollback

| Thao tác | Phạm vi thay đổi bị hoàn tác | Transaction có kết thúc không? |
| --- | --- | --- |
| Statement-level rollback khi statement lỗi | Các thay đổi của statement lỗi | Không |
| ROLLBACK TO SAVEPOINT | Thay đổi sau savepoint được chỉ định | Không |
| ROLLBACK | Toàn bộ thay đổi chưa commit trong transaction hiện tại | Có |
| COMMIT | Không hoàn tác; xác nhận thay đổi transaction | Có |

Deadlock statement rollback không giống ROLLBACK toàn transaction. Cũng không nên nhầm với ROLLBACK TO SAVEPOINT do ứng dụng chủ động gọi.

### 6.4. Savepoint không tự giải quyết mọi deadlock

Ví dụ:

~~~sql
UPDATE deadlock_account_lab
SET balance = balance - 10
WHERE account_id = 10;

SAVEPOINT before_second_step;

UPDATE deadlock_account_lab
SET balance = balance + 10
WHERE account_id = 20;
~~~

Nếu statement thứ hai gặp deadlock, Oracle rollback statement đó. Ứng dụng vẫn cần quyết định số phận statement đầu tiên. ROLLBACK TO SAVEPOINT có thể hữu ích cho nhánh công việc tùy chọn, nhưng nếu bước thứ hai là bắt buộc của chuyển tiền, rollback toàn transaction là lựa chọn đúng để giữ atomicity.

### 6.5. COMMIT và ROLLBACK giải phóng khóa

- COMMIT xác nhận mọi thay đổi đang pending và giải phóng khóa transaction.
- ROLLBACK hoàn tác mọi thay đổi chưa commit và giải phóng khóa transaction.
- ROLLBACK TO SAVEPOINT hoàn tác phần sau mốc và giải phóng các khóa tương ứng với phần thay đổi được rollback theo quy tắc Oracle.

Đừng để session nhận ORA-00060 giữ transaction mở trong khi ứng dụng tiếp tục chờ người dùng hoặc gọi dịch vụ khác.

## 7. Bài lab hai session: tái hiện ORA-00060

### 7.1. Chuẩn bị bảng

Chạy một lần trong schema lab:

~~~sql
CREATE TABLE deadlock_lab (
    id NUMBER PRIMARY KEY,
    value_no NUMBER NOT NULL
);

INSERT INTO deadlock_lab VALUES (1, 100);
INSERT INTO deadlock_lab VALUES (2, 200);
COMMIT;
~~~

Mở hai session Oracle độc lập. Không COMMIT giữa các bước được ghi là chưa commit.

### 7.2. Session A khóa hàng 1

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 1;
~~~

Chưa COMMIT. Session A đang giữ khóa hàng 1.

### 7.3. Session B khóa hàng 2

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 2;
~~~

Chưa COMMIT. Session B đang giữ khóa hàng 2.

### 7.4. Session A yêu cầu hàng 2

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 10
WHERE id = 2;
~~~

A phải chờ vì B đang giữ khóa hàng 2. Giữ câu lệnh này đang chờ.

### 7.5. Session B yêu cầu hàng 1

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 10
WHERE id = 1;
~~~

B phải chờ A. Lúc này tồn tại chu trình: A chờ B và B chờ A. Oracle phát hiện deadlock; một statement nhận ORA-00060.

### 7.6. Kết thúc transaction của cả hai session

Trong session nhận ORA-00060, chạy:

~~~sql
ROLLBACK;
~~~

Nếu statement còn lại đang chờ, nó có thể tiếp tục sau khi khóa được giải phóng. Trong session còn lại, chạy ROLLBACK để hủy toàn bộ thay đổi của bài lab:

~~~sql
ROLLBACK;
~~~

Kiểm tra:

~~~sql
SELECT id, value_no
FROM deadlock_lab
ORDER BY id;
~~~

Kết quả phải trở về 100 và 200. Lưu ý thứ tự session nào nhận ORA-00060 không phải một quy tắc ứng dụng có thể dựa vào; Oracle chọn statement để phá chu trình.

### 7.7. Thử lại theo cùng thứ tự khóa

Trong cả hai luồng, hãy cập nhật hàng 1 trước, hàng 2 sau. Nếu A và B vẫn xung đột, một session có thể chờ session kia, nhưng không tạo chu trình chỉ do hai hàng này vì cả hai cùng lấy hàng 1 trước hàng 2.

Session A:

~~~sql
UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 1;

UPDATE deadlock_lab
SET value_no = value_no + 1
WHERE id = 2;
~~~

Session B cũng thực hiện theo đúng thứ tự đó. Một session có thể chờ ở hàng 1; sau khi session kia COMMIT/ROLLBACK, nó tiếp tục. Đây là blocking có thể giải quyết, không phải deadlock do thứ tự khóa ngược.

Kết thúc mỗi session bằng COMMIT hoặc ROLLBACK.

### 7.8. Dọn bảng lab

~~~sql
-- Chi chay sau khi ca hai session da ket thuc transaction.
DROP TABLE deadlock_lab PURGE;
~~~

DROP TABLE là DDL và có implicit commit theo quy tắc Oracle. Chỉ chạy khi chắc chắn đây là bảng lab do bạn tạo và không cần dữ liệu nữa.

## 8. Chẩn đoán deadlock trong Oracle

### 8.1. ORA-00060 và deadlock graph

Thông báo thường gặp:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

Oracle ghi thông tin chẩn đoán vào trace file theo cơ chế diagnostic infrastructure. Deadlock graph thường thể hiện:

- Các session liên quan.
- Loại enqueue/resource.
- Session đang giữ và session đang yêu cầu tài nguyên.
- ID tài nguyên và mode khóa.
- Các câu SQL liên quan khi thông tin có sẵn.

Trace giúp xác định chu trình thực tế, nhưng cần kết hợp với code path và transaction timeline để tìm nguyên nhân nghiệp vụ.

### 8.2. Xác định thư mục trace

Với quyền truy cập phù hợp:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

Default Trace File thường là trace file của session hiện tại; deadlock có thể được ghi ở trace/session liên quan và alert/diagnostic location tùy cấu hình. DBA có thể dùng ADRCI hoặc công cụ quản trị để tìm trace theo thời điểm và process.

### 8.3. Quan sát session đang chờ khóa

Khi blocking còn đang diễn ra, có thể xem:

~~~sql
SELECT
    sid,
    serial#,
    username,
    event,
    blocking_session,
    seconds_in_wait,
    wait_class
FROM v$session
WHERE blocking_session IS NOT NULL;
~~~

View này phản ánh session đang chờ tại thời điểm truy vấn. Deadlock thường đã được Oracle phá ngay khi phát hiện, nên sau ORA-00060 có thể không còn chuỗi chờ để quan sát trong V$SESSION. Khi đó trace file là nguồn quan trọng hơn.

Trong RAC, xem xét GV$SESSION và các cột instance tương ứng để không bỏ sót session ở instance khác.

### 8.4. Quan sát TX/TM lock

~~~sql
SELECT
    s.sid,
    s.serial#,
    s.username,
    l.type,
    l.id1,
    l.id2,
    l.lmode,
    l.request,
    l.block
FROM v$lock l
JOIN v$session s
  ON s.sid = l.sid
WHERE l.type IN ('TX', 'TM')
  AND (l.request > 0 OR l.block = 1)
ORDER BY s.sid, l.type;
~~~

Các cột LMODE và REQUEST biểu diễn mode đang giữ và mode đang yêu cầu. Muốn diễn giải chính xác resource, hãy đối chiếu V$LOCK_TYPE, V$SESSION và deadlock graph; không suy luận nguyên nhân chỉ từ một dòng TX wait.

### 8.5. Quy trình đọc trace

Khi nhận ORA-00060:

1. Ghi lại thời điểm, service/module/action, request ID và SQL ID nếu có.
2. Lấy deadlock graph từ trace.
3. Xác định các session và resource trong chu trình.
4. Đối chiếu object ID, row/resource và SQL liên quan.
5. Tìm đường gọi ứng dụng, trigger và procedure tạo thứ tự khóa.
6. So sánh thứ tự lấy khóa giữa các transaction.
7. Sửa lock order hoặc giảm vùng giao nhau, rồi tái hiện trong môi trường test.

Không nên chỉ tăng timeout. Timeout kéo dài thời gian chờ nhưng không phá được chu trình deadlock.

## 9. Phòng tránh deadlock trong thiết kế và code

### 9.1. Quy định lock hierarchy

Tài liệu hóa thứ tự khóa cho các bảng/tài nguyên được cập nhật cùng nhau. Ví dụ:

~~~text
CUSTOMER -> ACCOUNT -> ORDER -> ORDER_LINE -> INVENTORY -> LEDGER
~~~

Nếu code path mới cần khóa theo thứ tự ngược, phải thiết kế lại hoặc chứng minh không thể giao nhau với luồng khác.

### 9.2. Chuẩn hóa thứ tự khóa hàng

Với nhiều ID, dùng cùng quy tắc sắp xếp, chẳng hạn tăng dần theo primary key. Không phụ thuộc thứ tự tình cờ của full scan, index scan hoặc execution plan.

### 9.3. Giảm số lượng và thời gian giữ khóa

- Chỉ khóa những hàng cần thiết.
- Thực hiện kiểm tra không cần khóa trước khi vào transaction nếu an toàn.
- Không chờ người dùng, gọi REST, gửi email hoặc tải file trong lúc giữ khóa.
- Commit/rollback ngay khi đơn vị công việc kết thúc.
- Tránh xử lý một batch quá lớn trong một transaction nếu có thể chia thành đơn vị nghiệp vụ độc lập.

Chia transaction chỉ hợp lệ khi nghiệp vụ cho phép các phần được xác nhận riêng. Không commit giữa hai bước phải thành công cùng nhau chỉ để giảm lock time.

### 9.4. Kiểm tra trigger và procedure gián tiếp

Mỗi khi thêm trigger hoặc gọi procedure mới, xem nó có cập nhật thêm bảng nào và thứ tự khóa thay đổi ra sao. Nên tránh các trigger có side effect rộng và khó nhìn thấy từ câu SQL gốc.

### 9.5. Index đúng cho predicate và khóa ngoại

Index có thể giảm số hàng phải đọc và thời gian giữ tài nguyên, đặc biệt với UPDATE/DELETE có điều kiện. Đánh giá index khóa ngoại ở bảng con nếu workload xóa/cập nhật khóa cha. Index không thay thế lock order; nó chỉ giúp giảm một số loại contention.

### 9.6. Phân vùng công việc

Với worker queue hoặc batch, phân vùng theo tenant, account range hoặc khóa nghiệp vụ để giảm khả năng hai worker đụng cùng tập hàng. SELECT FOR UPDATE SKIP LOCKED có thể hữu ích cho queue, nhưng chỉ khi bỏ qua hàng đang bị khóa đúng với semantics công việc. Nó không phải giải pháp tổng quát cho mọi deadlock.

### 9.7. Tránh transaction mở trong lúc gọi dịch vụ bên ngoài

Nếu cần gọi dịch vụ thanh toán hoặc gửi thông điệp, hãy thiết kế outbox/saga hoặc quy trình trạng thái phù hợp. Giữ transaction database mở qua network call làm tăng thời gian khóa và không tạo atomicity với hệ thống ngoài.

## 10. Xử lý ORA-00060 và retry

### 10.1. Rollback toàn bộ đơn vị công việc khi cần atomicity

Mẫu xử lý ở application service:

~~~text
BEGIN TRANSACTION
    execute step A
    execute step B
    execute step C
    COMMIT

ON ORA-00060
    ROLLBACK WHOLE TRANSACTION
    wait with bounded backoff
    retry whole business operation if safe
~~~

Điểm quyết định là rollback toàn transaction trước retry. Nếu chỉ chạy lại statement lỗi, các thay đổi trước đó có thể còn pending và logic nghiệp vụ có thể dựa trên dữ liệu đã cũ.

### 10.2. Retry có giới hạn và backoff

Không retry liên tục ngay lập tức. Một chính sách có thể gồm:

- Giới hạn số lần thử.
- Backoff tăng dần, có jitter.
- Ghi log số lần retry, SQL ID, request ID và thời lượng chờ.
- Chỉ retry các lỗi được phân loại là xung đột tạm thời.
- Sau khi hết retry, trả lỗi có thể xử lý/đối soát.

Backoff làm giảm khả năng các transaction va chạm lặp lại cùng thời điểm. Nó không thay thế sửa nguyên nhân thứ tự khóa ngược.

### 10.3. Retry phải idempotent

Một client có thể mất kết nối sau khi database đã COMMIT nhưng trước khi nhận phản hồi. Khi gửi lại request, ứng dụng cần nhận ra đó là cùng một yêu cầu nghiệp vụ.

Ví dụ bảng request:

~~~sql
CREATE TABLE transfer_request_lab (
    request_id VARCHAR2(64 CHAR) PRIMARY KEY,
    transfer_id NUMBER NOT NULL UNIQUE,
    from_account_id NUMBER NOT NULL,
    to_account_id NUMBER NOT NULL,
    amount NUMBER(18,2) NOT NULL,
    status VARCHAR2(12 CHAR) NOT NULL
);
~~~

Request ID duy nhất được ghi trong cùng transaction với thay đổi số dư và lịch sử. Nếu cùng request đến lần nữa, ứng dụng trả kết quả đã lưu thay vì thực hiện chuyển tiền lần hai.

### 10.4. Phân biệt lỗi có thể retry

| Lỗi | Cách xử lý thường cân nhắc |
| --- | --- |
| ORA-00060 | Rollback toàn transaction; sửa lock order; retry có giới hạn nếu nghiệp vụ an toàn |
| ORA-08177 | Rollback và chạy lại toàn transaction SERIALIZABLE nếu phù hợp |
| ORA-00054 hoặc timeout khóa | Chờ/backoff hoặc báo bận theo chính sách |
| ORA-00001 unique violation | Kiểm tra request đã tồn tại hay dữ liệu vi phạm; không retry vô điều kiện |
| ORA-02290 check violation | Sửa dữ liệu/logic; thường không retry cùng input |
| Lỗi kết nối quanh COMMIT | Trạng thái commit có thể không xác định ở client; kiểm tra bằng request/idempotency key |

Không phải mọi lỗi database đều là transient. Retry lỗi constraint hoặc lỗi logic không thay thế việc sửa dữ liệu/điều kiện.

## 11. Deadlock trong JDBC

### 11.1. Bắt lỗi và rollback connection

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateFirstResource(connection);
        updateSecondResource(connection);
        writeBusinessHistory(connection);
        connection.commit();
    } catch (SQLException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Với ORA-00060, rollback toàn transaction trước khi connection được trả về pool. Không chỉ bắt exception rồi tiếp tục dùng connection và commit những câu DML trước đó.

### 11.2. Nhận diện mã lỗi Oracle

Oracle JDBC driver thường cung cấp vendor error code trong SQLException:

~~~java
catch (SQLException ex) {
    if (ex.getErrorCode() == 60) {
        // ORA-00060: deadlock detected
    }
    throw ex;
}
~~~

Có thể kiểm tra SQLState và chained exceptions theo driver, nhưng error code Oracle là dấu hiệu cụ thể cho ORA-00060. Không dựa duy nhất vào việc so khớp chuỗi thông báo đã bản địa hóa.

### 11.3. Retry ở tầng sở hữu transaction

Pseudocode:

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        try {
            executeWholeBusinessUnit(connection, request);
            connection.commit();
            return;
        } catch (SQLException ex) {
            connection.rollback();
            if (ex.getErrorCode() != 60 || attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    sleepWithBackoffAndJitter(attempt);
}
~~~

Đây là pseudocode: triển khai thực tế cần xử lý lỗi rollback, lỗi close/connection pool, interruption, transaction outcome không xác định quanh COMMIT và idempotency. Mỗi lần retry phải lấy transaction/connection sạch và thực hiện lại toàn bộ nghiệp vụ.

### 11.4. Không commit trong DAO con

DAO hoặc repository con không nên tự COMMIT nếu nó là một phần của đơn vị công việc lớn hơn. Tầng service sở hữu transaction, điều phối tất cả DAO trên cùng connection và quyết định commit/rollback. Nếu mỗi DAO lấy connection riêng, chúng không còn cùng transaction và atomicity bị phá vỡ.

## 12. Những cách xử lý sai cần tránh

| Cách làm | Vì sao nguy hiểm | Cách phù hợp hơn |
| --- | --- | --- |
| Chỉ tăng timeout | Chu trình deadlock vẫn tồn tại | Sửa thứ tự khóa |
| Bắt ORA-00060 rồi COMMIT | DML trước statement lỗi có thể vẫn pending | Rollback toàn đơn vị công việc nếu bước lỗi làm nghiệp vụ không hoàn chỉnh |
| Chỉ retry statement lỗi | Các bước trước có thể đã dùng snapshot/trạng thái cũ | Retry toàn transaction sau rollback |
| Thêm COMMIT giữa các UPDATE để giải phóng khóa | Phá atomicity nghiệp vụ | Rút ngắn transaction nhưng giữ các bước bắt buộc cùng transaction |
| Chỉ sắp xếp một luồng | Luồng khác vẫn có thể khóa theo thứ tự ngược | Áp dụng lock hierarchy ở mọi code path |
| Dựa vào thứ tự scan tình cờ | Execution plan có thể đổi | Khóa theo thứ tự khóa được thiết kế rõ |
| Bỏ qua mọi hàng đang khóa bằng SKIP LOCKED | Có thể làm sai semantics công việc | Chỉ dùng cho queue/worker khi bỏ qua là hợp lệ |
| Xóa trigger để hết deadlock mà không phân tích | Có thể bỏ mất bất biến/audit | Phân tích side effect và thiết kế lại thứ tự |
| Tạo index tùy tiện | Tăng DML/storage cost mà không giải quyết chu trình | Đọc deadlock graph và đánh giá index theo workload |

## 13. Bài lab nâng cao: chuyển tiền hai chiều

Sau khi chạy lab ở Mục 7, có thể so sánh hai cách.

### 13.1. Cách gây deadlock

Hai luồng cùng cập nhật hai tài khoản nhưng khóa theo hướng chuyển:

~~~text
Transfer 10 -> 20: lock 10, then 20
Transfer 20 -> 10: lock 20, then 10
~~~

Khi chạy đồng thời, chúng có thể tạo chu trình.

### 13.2. Cách khóa theo thứ tự chuẩn

~~~text
Transfer 10 -> 20: lock 10, then 20
Transfer 20 -> 10: lock 10, then 20
~~~

Cả hai cùng khóa ID nhỏ trước. Một transaction có thể chờ, nhưng không tạo chu trình chỉ từ cặp hàng đó.

### 13.3. Câu hỏi quan sát

- Session nào nhận ORA-00060?
- Statement nào bị rollback?
- DML trước statement đó còn pending không?
- Khóa trước đó được giữ đến khi nào?
- Session còn lại tiếp tục ra sao sau khi victim rollback?
- Sau khi cả hai rollback, số dư có trở về ban đầu không?
- Khi cả hai dùng thứ tự khóa tăng dần, kết quả thay đổi thế nào?

Ghi lại timeline theo mili giây nếu cần. Việc xác định đúng statement rollback và transaction còn mở giúp tránh hiểu nhầm rằng Oracle tự rollback mọi thay đổi.

## 14. Checklist thiết kế và vận hành

Trước khi đưa một luồng DML nhiều bảng vào production, hãy kiểm tra:

1. Các bảng/hàng cần khóa đã được liệt kê chưa?
2. Có lock hierarchy chung cho toàn hệ thống không?
3. Các hàng trong cùng bảng có được khóa theo thứ tự ID ổn định không?
4. Trigger, cascade và procedure có lấy thêm khóa không?
5. Foreign key có index phù hợp khi workload cần không?
6. Transaction có giữ khóa trong lúc gọi mạng/chờ người dùng không?
7. Batch job có vùng dữ liệu giao nhau không?
8. Ứng dụng có rollback toàn transaction sau ORA-00060 không?
9. Retry có giới hạn và có idempotency không?
10. Trace/SQL ID/request ID có đủ để điều tra không?
11. Có bài test đồng thời với hai session hoặc nhiều worker không?
12. Sau khi thay đổi execution plan/index/trigger, đã kiểm tra lại deadlock behavior chưa?

## 15. Câu hỏi tự kiểm tra

1. Deadlock khác blocking thông thường ở điểm nào?
2. Vì sao hai UPDATE riêng lẻ đều đúng vẫn có thể deadlock?
3. Chu trình chờ trong ví dụ hai hàng gồm những cạnh nào?
4. Oracle báo lỗi nào khi phát hiện deadlock?
5. Khi ORA-00060 xảy ra, Oracle rollback statement hay toàn bộ transaction?
6. Những DML thành công trước statement bị rollback có thể còn tồn tại không?
7. Vì sao ứng dụng thường cần rollback toàn transaction sau deadlock?
8. COMMIT có tác động gì đến các khóa hàng đang giữ?
9. Tại sao thứ tự khóa theo account_id tăng dần giúp giảm deadlock?
10. Vì sao lock hierarchy phải tính cả trigger và procedure được gọi gián tiếp?
11. Foreign key không có index có thể làm tăng phạm vi khóa như thế nào?
12. ORA-00060 có luôn chỉ ra hai UPDATE trên cùng một bảng không?
13. Deadlock graph có thể cung cấp thông tin gì?
14. Vì sao tăng timeout không giải quyết deadlock?
15. Khi nào SKIP LOCKED phù hợp?
16. Vì sao retry chỉ statement lỗi có thể tạo kết quả nghiệp vụ sai?
17. Retry có giới hạn và backoff giúp ích gì?
18. Idempotency key xử lý tình huống client mất phản hồi COMMIT như thế nào?
19. Tại sao không nên COMMIT giữa các bước chuyển tiền bắt buộc?
20. Cần kiểm tra gì sau khi sửa lock order?

**Gợi ý trả lời:**

1. Blocking có một đường chờ có thể được giải phóng; deadlock có chu trình chờ.
2. Vì mỗi transaction có thể giữ một khóa rồi yêu cầu khóa mà transaction kia đang giữ.
3. A chờ hàng 2 do B giữ; B chờ hàng 1 do A giữ.
4. ORA-00060.
5. Statement được chọn để phá chu trình; không tự động rollback toàn transaction.
6. Có, chúng có thể còn pending cho đến COMMIT/ROLLBACK.
7. Để không commit trạng thái nghiệp vụ dở dang và giải phóng các khóa còn lại.
8. Xác nhận thay đổi và giải phóng khóa transaction.
9. Hai transaction cùng lấy khóa theo một thứ tự, loại bỏ chu trình do đảo thứ tự của cặp hàng đó.
10. Vì side effect gián tiếp cũng lấy khóa và có thể đảo thứ tự.
11. Parent delete/update có thể cần khóa child table ở phạm vi rộng hơn, làm tăng blocking.
12. Không; tài nguyên có thể liên quan TX/TM enqueue, index hoặc nhiều bảng.
13. Session, resource, mode khóa, quan hệ giữ/yêu cầu và SQL liên quan khi có sẵn.
14. Timeout chỉ thay đổi thời gian chờ; chu trình không tự biến mất.
15. Với worker queue khi bỏ qua hàng đang được worker khác khóa là đúng semantics.
16. Vì các bước trước có thể vẫn pending và quyết định nghiệp vụ có thể dựa trên dữ liệu cũ.
17. Giảm va chạm lặp lại và tránh retry vô hạn làm tăng tải.
18. Nhận diện request đã xử lý và trả kết quả cũ thay vì thực hiện tác động lần hai.
19. Commit sớm làm các thay đổi một phần trở thành vĩnh viễn và không thể rollback cùng nhau.
20. Tái hiện đồng thời, đọc trace, xác nhận lock order, transaction rollback và kết quả dữ liệu.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): khóa, xử lý đồng thời và read consistency.
- [Oracle Database 19c Concepts — Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html): transaction, commit, rollback và statement-level failure.
- [Oracle Database 19c Administrator's Guide — Managing Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-data-concurrency-and-consistency.html): quản lý khóa và concurrency.
- [Oracle Database 19c Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): thông tin lock/enqueue.
- [Oracle Database 19c Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): trạng thái session và blocking session.
- [Oracle Database 19c Administrator's Guide — Automatic Diagnostic Repository](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/monitoring-the-database.html): diagnostic information và trace.
- [Oracle Database Error Messages — ORA-00060](https://docs.oracle.com/en/error-help/db/ora-00060/): deadlock detected while waiting for resource.
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE và locking clauses.

**Nguyên tắc cần nhớ:** deadlock thường bắt nguồn từ một chu trình khóa, đặc biệt khi các transaction lấy nhiều hàng hoặc nhiều bảng theo thứ tự khác nhau. Oracle phát hiện chu trình và rollback statement được chọn, nhưng các thay đổi trước đó trong transaction có thể vẫn còn pending. Với một đơn vị công việc cần atomicity, hãy rollback toàn transaction, sửa thứ tự khóa ở mọi đường gọi và chỉ retry toàn nghiệp vụ khi có giới hạn cùng cơ chế chống xử lý trùng.
