# Đọc nhất quán, thao tác ghi và các tình huống phải chờ nhau trong Oracle Database

Trong Oracle Database, nhiều session có thể cùng đọc và ghi một bảng. Một câu SELECT có thể đang chạy trong khi session khác UPDATE cùng những hàng đó; hai transaction cũng có thể cùng muốn sửa một hàng. Oracle cần bảo đảm người đọc nhìn thấy một trạng thái dữ liệu nhất quán, đồng thời kiểm soát xung đột giữa các thao tác ghi.

Cần tách ba cơ chế có liên quan:

- **Read consistency:** câu truy vấn đọc dữ liệu theo một snapshot logic, không nhìn thấy thay đổi chưa commit của transaction khác.
- **MVCC và undo:** Oracle dùng undo để dựng lại phiên bản đã commit phù hợp với snapshot khi block hiện tại đã bị thay đổi.
- **Locking:** khóa bảo vệ các thay đổi ghi và các thao tác chủ động yêu cầu khóa. Khi hai writer muốn sửa cùng một hàng, một bên có thể phải chờ.

Vì vậy, một SELECT thông thường thường không phải chờ UPDATE trên cùng hàng; nó có thể đọc phiên bản cũ bằng undo. Nhưng một UPDATE thứ hai trên chính hàng đó thường phải chờ transaction đang giữ khóa. Đây là điểm cốt lõi để hiểu vì sao Oracle vừa hỗ trợ đọc đồng thời vừa phải xử lý blocking giữa các writer.

Bài học trình bày cách Oracle đọc nhất quán, khóa hàng và khóa bảng, những trường hợp phải chờ, SELECT FOR UPDATE, các lựa chọn WAIT/NOWAIT/SKIP LOCKED, lost update, write consistency, deadlock, cách quan sát session bị chặn và các bài thực hành hai session.

## 1. Đọc nhất quán khi có nhiều session

### 1.1. Ví dụ về một hàng đang được cập nhật

Giả sử bảng tài khoản có dữ liệu:

| ACCOUNT_ID | BALANCE |
| ---: | ---: |
| 101 | 5.000 |
| 202 | 8.000 |

Session A chạy:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;

-- Chưa COMMIT.
```

Giá trị 4.000 là thay đổi của A nhưng chưa được commit. Session B chạy SELECT thông thường:

```sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id = 101;
```

B nhìn thấy giá trị đã commit trước đó là 5.000. Oracle không cho B đọc giá trị chưa commit 4.000 của A. Nếu block hiện tại đã chứa phiên bản do A sửa, Oracle có thể dùng undo để dựng lại phiên bản phù hợp với snapshot của B.

### 1.2. SELECT thông thường không khóa hàng chỉ để đọc

Một câu SELECT thông thường không lấy row lock trên mỗi hàng mà nó đọc. Vì thế, trong trường hợp DML thông thường:

- Reader có thể đọc phiên bản đã commit trước đó.
- Writer có thể tiếp tục thay đổi hàng.
- Reader không cần chờ writer commit chỉ để thực hiện SELECT.
- Writer không cần chờ các SELECT thông thường nhả row lock, vì các SELECT đó không giữ row lock.

Đây là một đặc điểm quan trọng của MVCC trong Oracle. Tuy nhiên, không nên kết luận rằng SELECT không bao giờ chờ: truy vấn vẫn có thể phải đợi I/O, latches, metadata locks, DDL hoặc tài nguyên khác. Các câu SELECT có `FOR UPDATE` cũng chủ động yêu cầu khóa.

### 1.3. Snapshot ở cấp statement

Với isolation level mặc định READ COMMITTED, mỗi câu SQL có snapshot nhất quán riêng tại thời điểm statement bắt đầu.

Ví dụ:

1. Session B chạy SELECT và thấy balance 5.000.
2. Session A UPDATE balance thành 4.000 rồi COMMIT.
3. Session B chạy một SELECT mới.
4. SELECT mới có thể thấy balance 4.000.

Hai câu SELECT thuộc cùng một transaction của B nhưng có thể nhìn thấy hai trạng thái đã commit khác nhau. Đây là hành vi bình thường của READ COMMITTED.

Ngược lại, nếu một câu SELECT đang chạy và A commit trong lúc B vẫn fetch kết quả, câu SELECT đang chạy tiếp tục đọc theo snapshot của chính statement đó. Statement tiếp theo mới có thể thấy commit mới.

### 1.4. Không đọc dữ liệu chưa commit

Oracle không cung cấp dirty read trong các mức cô lập transaction thông thường. Một transaction không thể dùng SELECT thông thường để nhìn thấy thay đổi chưa commit của transaction khác.

Điều này không ngăn hai transaction nhìn thấy kết quả khác nhau theo thời điểm snapshot. Nó chỉ bảo đảm dữ liệu được đọc là dữ liệu phù hợp với quy tắc nhất quán, không phải một thay đổi đang dang dở của session khác.

## 2. Undo và MVCC hỗ trợ reader như thế nào?

### 2.1. Undo lưu thông tin phiên bản trước

Khi transaction UPDATE, DELETE hoặc INSERT, Oracle tạo undo information để có thể rollback và phục vụ consistent read. Undo record được quản lý trong undo segment thuộc undo tablespace.

Ví dụ:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;
```

Nếu giá trị trước đó là 5.000, undo chứa thông tin cần thiết để khôi phục trạng thái cũ. Khi session khác cần đọc snapshot trước thay đổi, Oracle có thể áp dụng undo để dựng lại phiên bản 5.000.

### 2.2. Hình dung cơ chế consistent read

```text
Giá trị đã commit trước đó: BALANCE = 5.000
                  |
                  | Session A UPDATE
                  v
Giá trị hiện tại trong block: BALANCE = 4.000 (chưa commit)
                  |
                  | Session B cần snapshot cũ
                  v
Oracle dùng undo để dựng phiên bản đọc: BALANCE = 5.000
```

Phiên bản nhất quán được dựng từ block và undo cần thiết. Oracle không cần tạo một bản sao toàn bộ bảng cho từng reader.

### 2.3. Reader và writer khác writer và writer

| Tình huống | Hành vi điển hình |
| --- | --- |
| SELECT thường đọc hàng đang bị UPDATE | Đọc phiên bản nhất quán bằng undo; thường không chờ row lock |
| UPDATE cùng hàng đang bị UPDATE bởi transaction khác | Chờ transaction giữ khóa kết thúc |
| DELETE hàng đang bị UPDATE bởi transaction khác | Có thể chờ khóa hàng |
| SELECT FOR UPDATE trên hàng đang bị writer khóa | Có thể chờ, hoặc xử lý theo NOWAIT/WAIT/SKIP LOCKED |
| Hai INSERT tạo cùng khóa duy nhất nhưng một khóa chưa commit | Có thể chờ kết quả transaction kia để xác định vi phạm uniqueness |

MVCC chủ yếu giải quyết xung đột giữa reader và writer. Nó không loại bỏ nhu cầu khóa khi nhiều writer cùng thay đổi dữ liệu.

## 3. Khóa trong Oracle: row lock và table lock

### 3.1. Row-level lock

Khi DML thay đổi một hàng, Oracle khóa hàng đó để ngăn transaction khác đồng thời sửa/xóa cùng hàng theo cách xung đột.

Ví dụ:

```sql
UPDATE employees
SET salary = salary + 1000
WHERE employee_id = 100;
```

Transaction giữ khóa trên hàng bị thay đổi cho đến khi COMMIT hoặc ROLLBACK. Các transaction khác muốn thay đổi hàng đó có thể phải chờ.

Khóa hàng được quản lý gắn với transaction; Oracle dùng transaction enqueue (thường quan sát dưới loại TX) để điều phối xung đột. Ứng dụng không cần tự quản lý row lock bằng câu lệnh riêng cho mỗi UPDATE.

### 3.2. Table-level DML lock

DML cũng lấy khóa ở cấp bảng để bảo vệ cấu trúc truy cập và phối hợp với các thao tác khác. Một INSERT/UPDATE/DELETE thông thường lấy table lock ở chế độ Row Exclusive (RX, thường được thể hiện là TM mode 3).

Các DML thông thường trên cùng bảng có thể cùng giữ Row Exclusive table lock. Vì vậy, việc hai session cùng UPDATE hai hàng khác nhau trong một bảng không tự động khiến chúng chặn nhau ở cấp bảng.

Khóa bảng ở chế độ mạnh hơn, DDL hoặc thao tác explicit LOCK TABLE có thể xung đột với các DML này.

### 3.3. Khóa hàng và khóa bảng không phải cùng một thứ

- **Row lock** bảo vệ các hàng cụ thể mà transaction đang sửa hoặc khóa bằng FOR UPDATE.
- **Table lock** điều phối quyền truy cập ở cấp đối tượng và tương tác với DDL/explicit table lock.
- Có nhiều DML cùng hoạt động trên một bảng vẫn là tình huống bình thường.
- Một table lock mạnh có thể làm nhiều DML khác phải chờ dù chúng định sửa các hàng khác nhau.

### 3.4. Khóa được giữ đến khi nào?

Với DML thông thường và SELECT FOR UPDATE, khóa được giữ đến khi transaction kết thúc bằng COMMIT hoặc ROLLBACK. Kết thúc một câu UPDATE không đồng nghĩa khóa được nhả nếu transaction vẫn chưa commit.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;

-- Hàng vẫn bị khóa sau khi câu UPDATE kết thúc.
-- Khóa được giải phóng khi COMMIT hoặc ROLLBACK.
```

Đây là lý do transaction dài có thể gây blocking dù session không còn đang chạy một câu SQL.

## 4. Khi nào hai thao tác phải chờ nhau?

### 4.1. Hai session UPDATE cùng một hàng

Session A:

```sql
UPDATE accounts
SET balance = 4000
WHERE account_id = 101;

-- Chưa COMMIT.
```

Session B:

```sql
UPDATE accounts
SET balance = 4500
WHERE account_id = 101;
```

B cần khóa hàng 101 nhưng A đang giữ khóa, vì vậy B thường chuyển sang trạng thái chờ. Khi A COMMIT hoặc ROLLBACK, B có thể tiếp tục và Oracle áp dụng quy tắc nhất quán ghi cho statement của B.

Nếu A COMMIT, B làm việc với trạng thái mới đã commit. Nếu A ROLLBACK, thay đổi của A bị hủy và B có thể cập nhật trên trạng thái trước đó.

### 4.2. Hai session UPDATE hai hàng khác nhau

Session A:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

Session B:

```sql
UPDATE accounts
SET balance = balance + 100
WHERE account_id = 202;
```

Nếu không có trigger, constraint, khóa bảng hoặc tài nguyên chung gây xung đột, hai câu lệnh có thể chạy đồng thời vì chúng sửa hai hàng khác nhau. Cùng một bảng không có nghĩa mọi DML đều phải chờ nhau.

### 4.3. DELETE và UPDATE cùng hàng

Nếu A UPDATE một hàng nhưng chưa commit, B DELETE chính hàng đó có thể phải chờ. Tương tự, nếu A DELETE một hàng, B UPDATE hoặc DELETE cùng hàng cũng phải chờ transaction A kết thúc.

Sau khi chờ, Oracle xác định trạng thái hiện tại và áp dụng điều kiện statement theo quy tắc nhất quán ghi. Nếu hàng đã bị xóa hoặc không còn thỏa WHERE, statement của B có thể ảnh hưởng 0 hàng.

### 4.4. INSERT trùng khóa duy nhất chưa commit

Session A:

```sql
INSERT INTO employees(employee_id, name)
VALUES (9001, 'New Employee');

-- Chưa COMMIT.
```

Session B thử insert cùng khóa:

```sql
INSERT INTO employees(employee_id, name)
VALUES (9001, 'Another Employee');
```

B có thể phải chờ vì Oracle chưa thể kết luận khóa duy nhất đó sẽ tồn tại sau khi transaction A kết thúc. Nếu A COMMIT, B nhận lỗi vi phạm unique/primary key. Nếu A ROLLBACK, B có thể tiếp tục insert.

Đây là một trường hợp chờ không xuất phát từ UPDATE cùng hàng theo cách thông thường, nhưng vẫn do xung đột dữ liệu và constraint.

### 4.5. Khóa bảng tường minh

Ví dụ:

```sql
LOCK TABLE accounts IN EXCLUSIVE MODE;
```

Khóa bảng EXCLUSIVE có thể chặn DML khác trên bảng cho đến khi transaction kết thúc. Đây là khóa mạnh; không sử dụng chỉ vì muốn bảo vệ một hàng cụ thể.

Nếu chỉ cần khóa các hàng được chọn, `SELECT ... FOR UPDATE` thường diễn đạt mục tiêu chính xác hơn.

### 4.6. DDL cần khóa metadata

Các thao tác DDL như ALTER TABLE cần khóa đối tượng phù hợp và có thể phải chờ transaction đang sử dụng bảng kết thúc. Ngược lại, DDL có thể làm các DML khác chờ. DDL Oracle cũng có implicit commit trước/sau theo quy tắc của lệnh, vì vậy không trộn DDL vào transaction nghiệp vụ với kỳ vọng có thể rollback như DML.

## 5. Thí nghiệm hai session: SELECT không chờ, UPDATE phải chờ

Thực hiện trong hai session độc lập, chẳng hạn hai worksheet trong SQL Developer. Dùng schema học tập.

### 5.1. Chuẩn bị dữ liệu

Chạy một lần:

```sql
CREATE TABLE demo_write_wait (
    item_id NUMBER(10) PRIMARY KEY,
    quantity NUMBER(10) NOT NULL
);

INSERT INTO demo_write_wait VALUES (1, 10);
INSERT INTO demo_write_wait VALUES (2, 20);
COMMIT;
```

### 5.2. Session A: khóa hàng bằng UPDATE

```sql
UPDATE demo_write_wait
SET quantity = 9
WHERE item_id = 1;

-- Chưa COMMIT.
```

Session A đã sửa hàng 1 và đang giữ khóa.

### 5.3. Session B: SELECT hàng đang bị khóa

```sql
SELECT item_id, quantity
FROM   demo_write_wait
WHERE  item_id = 1;
```

Kết quả vẫn là quantity 10. B đọc phiên bản đã commit trước đó bằng cơ chế consistent read; SELECT thường không phải chờ A chỉ vì A đang giữ row lock.

### 5.4. Session B: UPDATE cùng hàng

```sql
UPDATE demo_write_wait
SET quantity = 8
WHERE item_id = 1;
```

B sẽ phải chờ A kết thúc transaction vì hai writer đang tranh chấp cùng hàng. Giữ B ở trạng thái chờ để quan sát, sau đó quay lại session A.

### 5.5. Session A: COMMIT

```sql
COMMIT;
```

Sau commit, khóa được giải phóng. Session B tiếp tục. Giá trị cuối cùng phụ thuộc biểu thức UPDATE và điều kiện WHERE; trong ví dụ gán hằng số 8 nên nếu hàng vẫn thỏa điều kiện, giá trị cuối cùng là 8.

### 5.6. Thử lại với ROLLBACK

Đặt lại dữ liệu:

```sql
UPDATE demo_write_wait SET quantity = 10 WHERE item_id = 1;
COMMIT;
```

Lặp lại bước A nhưng kết thúc bằng:

```sql
ROLLBACK;
```

Session B sau khi hết chờ sẽ cập nhật trên trạng thái đã tồn tại trước thay đổi của A. So sánh hai trường hợp để thấy COMMIT và ROLLBACK ảnh hưởng ra sao tới writer đang chờ.

## 6. Write consistency: điều gì xảy ra sau khi writer phải chờ?

### 6.1. Điều kiện UPDATE phải được đánh giá trên trạng thái thích hợp

DML không chỉ cần khóa hàng; nó còn phải đảm bảo điều kiện WHERE và thay đổi được áp dụng trên trạng thái dữ liệu hợp lệ sau khi transaction trước kết thúc.

Ví dụ bảng tồn kho có một sản phẩm còn 1 đơn vị:

| SKU | QTY |
| --- | ---: |
| A-100 | 1 |

Hai session cùng chạy:

```sql
UPDATE inventory
SET qty = qty - 1
WHERE sku = 'A-100'
AND   qty >= 1;
```

Session A lấy khóa hàng và giảm quantity từ 1 xuống 0 nhưng chưa commit. Session B chạy cùng câu lệnh và phải chờ.

Nếu A COMMIT, B tiếp tục trên trạng thái mới. Điều kiện `qty >= 1` không còn đúng, nên B không được trừ tiếp xuống -1; số hàng bị cập nhật có thể là 0. Oracle duy trì write consistency bằng cách xử lý lại điều kiện/statement cần thiết sau xung đột khóa theo ngữ nghĩa READ COMMITTED.

### 6.2. Kiểm tra số hàng bị ảnh hưởng

Ứng dụng nên kiểm tra row count của DML:

```sql
UPDATE inventory
SET qty = qty - :requested_qty
WHERE sku = :sku
AND   qty >= :requested_qty;

-- Trong ứng dụng, kiểm tra SQL%ROWCOUNT.
```

Nếu số hàng cập nhật bằng 0, có thể sản phẩm không tồn tại hoặc số lượng hiện tại không đủ. Ứng dụng cần xác định phản hồi nghiệp vụ phù hợp thay vì giả định UPDATE luôn thành công.

### 6.3. Atomic UPDATE giảm khoảng trống giữa đọc và ghi

Cách dễ tạo race condition:

1. SELECT quantity.
2. Ứng dụng tính quantity mới.
3. Một session khác thay đổi hàng.
4. Ứng dụng UPDATE bằng giá trị đã tính từ dữ liệu cũ.

Có thể diễn đạt điều kiện và phép tính trong cùng một UPDATE để Oracle khóa và áp dụng thay đổi nguyên tử trên hàng:

```sql
UPDATE inventory
SET qty = qty - :requested_qty
WHERE sku = :sku
AND   qty >= :requested_qty;
```

Đây là mẫu hữu ích cho các thao tác trừ tồn kho hoặc kiểm tra hạn mức. Vẫn cần xử lý row count, transaction và các quy tắc nghiệp vụ khác.

### 6.4. Không phải mọi race condition đều tự được giải quyết

Nếu ứng dụng đọc giá trị rồi ghi một giá trị tuyệt đối được tính bên ngoài, Oracle không thể tự suy ra ý định nghiệp vụ. Ví dụ hai session cùng đọc balance 100, mỗi bên tính số dư mới 90 và chạy:

```sql
UPDATE accounts
SET balance = 90
WHERE account_id = 101;
```

Cả hai có thể lần lượt thành công, nhưng kết quả cuối là 90 thay vì 80. Đây là lost update do logic ứng dụng đọc–tính–ghi. MVCC bảo đảm read consistency, không tự bảo vệ mọi quyết định nhiều bước của ứng dụng.

## 7. Lost update và cách phòng tránh

### 7.1. Kịch bản lost update

Giả sử balance ban đầu là 100:

```text
Session A                         Session B
---------                         ---------
SELECT balance -> 100
                                  SELECT balance -> 100
Tính số mới: 90
                                  Tính số mới: 90
UPDATE balance = 90
COMMIT
                                  UPDATE balance = 90
                                  COMMIT

Kết quả cuối: 90
Mong đợi nếu cả hai trừ 10: 80
```

Hai transaction không ghi đè đồng thời theo nghĩa row lock bị bỏ qua; chúng ghi tuần tự sau khi lấy được khóa. Vấn đề là session B đã tính giá trị 90 từ một lần đọc cũ, nên lần ghi sau làm mất tác động của A.

### 7.2. Cách 1: dùng phép cập nhật tương đối

Nếu nghiệp vụ là trừ 10, hãy để phép tính trong SQL:

```sql
UPDATE accounts
SET balance = balance - 10
WHERE account_id = 101;
```

Hai UPDATE được tuần tự hóa trên cùng hàng và mỗi lệnh tính trên giá trị hiện tại phù hợp khi đến lượt thực hiện. Kết quả là 80 nếu cả hai đều thành công.

### 7.3. Cách 2: SELECT FOR UPDATE trước khi đọc

```sql
SELECT balance
FROM   accounts
WHERE  account_id = 101
FOR UPDATE;

-- Tính toán và UPDATE trong cùng transaction.
```

Session lấy khóa trước khi đọc để quyết định. Session khác muốn khóa/cập nhật cùng hàng phải chờ. Sau khi tính và cập nhật xong, COMMIT hoặc ROLLBACK để giải phóng khóa.

Dùng cách này khi logic nghiệp vụ thực sự cần đọc nhiều thuộc tính rồi tính toán trước khi cập nhật. Không giữ khóa lâu trong lúc gọi dịch vụ bên ngoài hoặc chờ người dùng thao tác.

### 7.4. Cách 3: optimistic locking bằng version column

Có thể thêm cột phiên bản:

```sql
ALTER TABLE accounts
ADD version_no NUMBER DEFAULT 0 NOT NULL;
```

Ứng dụng đọc balance và version_no. Khi cập nhật:

```sql
UPDATE accounts
SET balance = :new_balance,
    version_no = version_no + 1
WHERE account_id = :account_id
AND   version_no = :old_version;
```

Nếu một transaction khác đã cập nhật trước, version_no thay đổi và UPDATE sau có thể ảnh hưởng 0 hàng. Ứng dụng nhận biết xung đột, đọc lại và quyết định thử lại hoặc báo người dùng.

Optimistic locking hữu ích khi xung đột ít và không muốn khóa hàng trong suốt thời gian xử lý dài.

## 8. SELECT FOR UPDATE và các tùy chọn chờ

### 8.1. Khóa các hàng sẽ được xử lý

```sql
SELECT account_id,
       balance
FROM   accounts
WHERE  account_id = 101
FOR UPDATE;
```

Câu lệnh đọc các hàng thỏa điều kiện và khóa chúng để transaction hiện tại có thể cập nhật an toàn. Khóa được giữ cho tới COMMIT hoặc ROLLBACK.

Có thể chỉ rõ bảng có cột được khóa trong truy vấn join:

```sql
SELECT e.employee_id,
       e.salary,
       d.department_name
FROM   employees e
JOIN   departments d
       ON d.department_id = e.department_id
WHERE  e.employee_id = 100
FOR UPDATE OF e.salary;
```

Mệnh đề OF xác định bảng/cột thuộc bảng mà câu lệnh cần khóa theo cú pháp Oracle. Cần kiểm tra giới hạn của SELECT FOR UPDATE khi truy vấn có view, aggregate, DISTINCT, GROUP BY hoặc các cấu trúc không thể khóa trực tiếp.

### 8.2. NOWAIT

```sql
SELECT *
FROM   accounts
WHERE  account_id = 101
FOR UPDATE NOWAIT;
```

Nếu hàng đang bị session khác khóa, câu lệnh không chờ mà trả lỗi ngay (thường là ORA-00054 trong tình huống resource busy). Ứng dụng có thể thông báo bận hoặc thử lại theo chính sách.

### 8.3. WAIT n

```sql
SELECT *
FROM   accounts
WHERE  account_id = 101
FOR UPDATE WAIT 5;
```

Oracle chờ tối đa 5 giây để lấy khóa. Nếu hết thời gian mà không lấy được khóa, câu lệnh trả lỗi. Giá trị n được tính bằng giây.

### 8.4. SKIP LOCKED

```sql
SELECT task_id,
       status
FROM   job_queue
WHERE  status = 'READY'
FOR UPDATE SKIP LOCKED;
```

Nếu một hàng đã bị session khác khóa, session hiện tại bỏ qua hàng đó và tiếp tục lấy những hàng khác có thể khóa. Cách này thường được dùng trong mô hình queue/work distribution để nhiều worker xử lý các hàng khác nhau.

SKIP LOCKED không bảo đảm công bằng thứ tự tuyệt đối và không thay thế việc quản lý trạng thái job. Ứng dụng cần cập nhật trạng thái, commit và xử lý lỗi worker chết giữa chừng.

### 8.5. Chọn tùy chọn theo yêu cầu

| Tùy chọn | Hành vi khi hàng bị khóa | Trường hợp thường dùng |
| --- | --- | --- |
| Mặc định | Chờ theo hành vi khóa thông thường | Giao dịch có thể chờ |
| NOWAIT | Trả lỗi ngay | Cần phản hồi bận tức thì |
| WAIT n | Chờ tối đa n giây | Cho phép chờ có giới hạn |
| SKIP LOCKED | Bỏ qua hàng đang khóa | Worker lấy việc từ queue |

Không chọn SKIP LOCKED cho màn hình cần bảo đảm hiển thị đầy đủ tất cả hàng phù hợp; kết quả có thể thiếu những hàng đang bị khóa bởi session khác.

## 9. Deadlock: hai transaction chờ lẫn nhau

### 9.1. Deadlock là gì?

Deadlock xảy ra khi các transaction giữ tài nguyên mà transaction khác cần, tạo thành vòng chờ không thể tự giải quyết.

Ví dụ:

```text
Session A                         Session B
---------                         ---------
UPDATE hàng 1                     UPDATE hàng 2
giữ khóa hàng 1                   giữ khóa hàng 2

muốn UPDATE hàng 2                muốn UPDATE hàng 1
chờ B                             chờ A

        A chờ B  <---->  B chờ A
```

Không session nào có thể tiến tiếp nếu không có một transaction nhả khóa.

### 9.2. Oracle phát hiện deadlock

Oracle phát hiện deadlock và trả lỗi:

```text
ORA-00060: deadlock detected while waiting for resource
```

Oracle thường giải quyết bằng cách rollback statement liên quan của một transaction để phá vòng chờ và giải phóng khóa cần thiết. Không nên giả định toàn bộ transaction tự động được rollback trong mọi trường hợp; ứng dụng cần xử lý lỗi, đánh giá trạng thái transaction và rollback đơn vị nghiệp vụ nếu không thể tiếp tục an toàn.

### 9.3. Ví dụ tạo deadlock trong môi trường thử nghiệm

Chuẩn bị bảng:

```sql
CREATE TABLE demo_deadlock (
    id NUMBER PRIMARY KEY,
    value NUMBER
);

INSERT INTO demo_deadlock VALUES (1, 10);
INSERT INTO demo_deadlock VALUES (2, 20);
COMMIT;
```

Session A:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 1;
-- Chưa COMMIT.
```

Session B:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 2;
-- Chưa COMMIT.
```

Tiếp theo, A chạy:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 2;
```

A chờ khóa hàng 2 do B giữ. Sau đó B chạy:

```sql
UPDATE demo_deadlock SET value = value + 1 WHERE id = 1;
```

B chờ hàng 1 do A giữ. Oracle phát hiện chu trình chờ và một statement nhận ORA-00060.

Đây là bài thực hành có chủ đích, chỉ chạy trên bảng demo. Sau khi quan sát, kiểm tra trạng thái từng session và ROLLBACK/COMMIT để giải phóng transaction.

### 9.4. Cách giảm nguy cơ deadlock

- Cập nhật nhiều hàng theo cùng một thứ tự khóa trong mọi transaction.
- Giữ transaction ngắn.
- Tránh chờ người dùng hoặc gọi dịch vụ mạng khi đang giữ khóa.
- Không khóa hàng rộng hơn nhu cầu.
- Thiết kế batch để các worker ít đụng cùng tập hàng.
- Xử lý ORA-00060 bằng cách rollback/ retry toàn bộ đơn vị nghiệp vụ phù hợp, có giới hạn và backoff.

Deadlock không phải lúc nào cũng chỉ do lập trình sai; các thao tác phức tạp với trigger, FK, index và nhiều bảng cũng có thể tạo thứ tự khóa bất ngờ. Khi xảy ra, xem deadlock graph trong trace để xác định tài nguyên và câu SQL liên quan.

## 10. Khóa bảng và DDL có thể gây blocking

### 10.1. DML thông thường cùng bảng

Nhiều transaction có thể cùng giữ Row Exclusive table lock và sửa các hàng khác nhau. Table lock loại này tương thích với các DML thông thường khác trong nhiều trường hợp.

### 10.2. LOCK TABLE

Ví dụ:

```sql
LOCK TABLE demo_write_wait
IN EXCLUSIVE MODE;
```

Khóa EXCLUSIVE có thể ngăn DML khác trên bảng cho đến khi transaction kết thúc. Câu lệnh LOCK TABLE cần được dùng có chủ đích; khóa bảng thường làm giảm concurrency đáng kể.

Một số chế độ khóa bảng khác nhau có mức tương thích khác nhau. Cần đọc tài liệu Oracle về LOCK TABLE trước khi dùng trong hệ thống thật.

### 10.3. DDL và metadata lock

ALTER TABLE, DROP TABLE và một số DDL cần khóa đối tượng để thay đổi metadata. Nếu transaction khác đang sử dụng đối tượng và giữ khóa liên quan, DDL có thể chờ hoặc thất bại tùy cấu hình wait. DDL cũng có implicit commit theo quy tắc Oracle.

Không thực hiện DDL trong transaction cần khả năng rollback như DML. Hãy lên lịch thay đổi schema và kiểm tra session đang sử dụng bảng trước khi triển khai.

## 11. Quan sát session đang chờ khóa

### 11.1. V$SESSION

DBA hoặc tài khoản có quyền phù hợp có thể quan sát session:

```sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       blocking_session,
       seconds_in_wait,
       sql_id
FROM   v$session
WHERE  blocking_session IS NOT NULL
ORDER  BY seconds_in_wait DESC;
```

Các cột hữu ích:
- `SID` và `SERIAL#` định danh session trong instance.
- `EVENT` mô tả sự kiện chờ.
- `BLOCKING_SESSION` cho biết session đang chặn nếu Oracle xác định được.
- `SECONDS_IN_WAIT` cho biết thời gian chờ theo view.
- `SQL_ID` giúp tìm câu SQL liên quan.

Quyền truy cập V$SESSION thường được DBA cấp qua các quyền phù hợp; không cần cấp quyền rộng cho ứng dụng người dùng cuối chỉ để chạy báo cáo.

### 11.2. V$LOCK

Có thể quan sát các lock đang được giữ hoặc yêu cầu:

```sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM   v$lock
WHERE  type IN ('TX', 'TM')
ORDER  BY type, sid;
```

- `TX` thường liên quan transaction enqueue.
- `TM` thường liên quan DML/table enqueue.
- `LMODE` là mode đang giữ.
- `REQUEST` là mode đang yêu cầu; giá trị khác 0 cho thấy session đang chờ lock đó.
- `BLOCK` là thông tin về khả năng chặn session khác theo view.

Cách diễn giải ID1/ID2 và lock mode cần đối chiếu tài liệu Oracle; không kết luận chỉ từ một dòng V$LOCK mà chưa ghép với V$SESSION và SQL liên quan.

### 11.3. Kiểm tra đối tượng bị chờ

Có thể kết hợp V$SESSION với DBA_OBJECTS khi có quyền:

```sql
SELECT s.sid,
       s.serial#,
       s.event,
       s.blocking_session,
       o.owner,
       o.object_name,
       s.row_wait_file#,
       s.row_wait_block#,
       s.row_wait_row#
FROM   v$session s
LEFT JOIN dba_objects o
       ON o.object_id = s.row_wait_obj#
WHERE  s.blocking_session IS NOT NULL;
```

Các cột row_wait chỉ có ý nghĩa trong một số trạng thái chờ cụ thể. Không phải lúc nào chúng cũng xác định được một hàng bị chặn; cần kiểm tra event và trạng thái session.

### 11.4. Cách điều tra theo thứ tự

1. Xác định session đang chờ và blocking session.
2. Xem event, SQL_ID và thời gian chờ.
3. Lấy SQL text và transaction liên quan nếu có quyền.
4. Xác định hàng/bảng/tài nguyên xung đột.
5. Xác minh blocker còn cần transaction hay đã bị bỏ quên.
6. Phối hợp với chủ sở hữu ứng dụng trước khi kết thúc session.
7. Sau khi xử lý, theo dõi xem blocking có tái diễn không.

Không kill session chỉ vì nó xuất hiện trong cột blocking_session. Session có thể đang thực hiện một transaction hợp lệ; kết thúc cưỡng bức có thể gây rollback lớn và ảnh hưởng ứng dụng.

## 12. Tình huống nghiệp vụ: chuyển tiền giữa hai tài khoản

### 12.1. Thao tác phải nằm trong cùng transaction

Một chuyển tiền cần trừ tài khoản nguồn và cộng tài khoản đích:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :from_account
AND balance >= :amount;

-- Ứng dụng kiểm tra số hàng bị cập nhật.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :to_account;

-- Kiểm tra cả hai thao tác rồi mới COMMIT.
```

Hai UPDATE phải thuộc cùng transaction. Nếu thao tác thứ hai thất bại, ứng dụng ROLLBACK để không giữ trạng thái chỉ trừ tiền mà chưa cộng tiền.

### 12.2. Khóa theo thứ tự ổn định

Nếu hai session chuyển tiền ngược chiều giữa cùng hai tài khoản, một session có thể khóa tài khoản 101 rồi 202, session kia khóa 202 rồi 101. Thứ tự này có thể tạo deadlock.

Có thể giảm rủi ro bằng cách khóa hai tài khoản theo thứ tự khóa ổn định, chẳng hạn account_id tăng dần, trước khi cập nhật:

```sql
SELECT account_id, balance
FROM   accounts
WHERE  account_id IN (:from_account, :to_account)
ORDER  BY account_id
FOR UPDATE;
```

Sau khi khóa và kiểm tra số dư, thực hiện hai UPDATE trong cùng transaction. Cần xác nhận đủ hai hàng được khóa; nếu tài khoản không tồn tại thì hủy thao tác.

### 12.3. Không giữ khóa trong lúc chờ người dùng

Một quy trình không tốt là:
1. SELECT FOR UPDATE.
2. Hiển thị màn hình xác nhận.
3. Chờ người dùng vài phút.
4. Mới UPDATE và COMMIT.

Trong thời gian chờ, hàng bị khóa và các giao dịch khác có thể bị chặn. Nên thu thập xác nhận từ người dùng trước, sau đó mở transaction ngắn để khóa, kiểm tra lại điều kiện và thực hiện cập nhật.

## 13. Tình huống queue: nhiều worker lấy việc

### 13.1. Mục tiêu

Một bảng job queue có các hàng READY. Nhiều worker cần lấy việc mà không cùng xử lý một hàng. `FOR UPDATE SKIP LOCKED` cho phép worker bỏ qua các hàng đang được worker khác khóa.

### 13.2. Ví dụ lấy một nhóm job

```sql
SELECT job_id,
       payload
FROM   job_queue
WHERE  status = 'READY'
ORDER  BY priority DESC, created_at
FOR UPDATE SKIP LOCKED;
```

Ứng dụng lấy các hàng đã khóa, cập nhật trạng thái PROCESSING và COMMIT. Cú pháp lấy số lượng hàng có thể phụ thuộc phiên bản và cách viết query; cần thử nghiệm trong môi trường đúng release trước khi dùng trong production.

### 13.3. Các điều cần thiết ngoài SKIP LOCKED

- Ghi nhận worker/lease hoặc thời điểm nhận việc.
- Có cơ chế phục hồi job nếu worker chết.
- Cập nhật trạng thái và commit nhất quán.
- Thiết kế xử lý idempotent để retry không gây tác dụng phụ trùng.
- Theo dõi job bị kẹt ở PROCESSING.
- Không hiểu kết quả SKIP LOCKED là danh sách đầy đủ mọi job READY.

SKIP LOCKED là cơ chế phân phối công việc đồng thời, không phải một hệ thống queue hoàn chỉnh.

## 14. Các lỗi và nhầm lẫn thường gặp

| Dấu hiệu hoặc hiểu nhầm | Giải thích |
| --- | --- |
| SELECT thường chờ UPDATE cùng hàng | Thường không; SELECT dùng consistent read, nhưng có ngoại lệ do khóa/tài nguyên khác |
| UPDATE thứ hai chạy mãi | Có thể đang chờ transaction đầu commit/rollback |
| Câu UPDATE đã kết thúc nhưng hàng vẫn bị khóa | Transaction chưa COMMIT/ROLLBACK |
| Hai UPDATE trên hai hàng khác nhau vẫn chờ | Kiểm tra trigger, FK, table lock, index/constraint hoặc tài nguyên chung |
| SELECT FOR UPDATE giống SELECT thường | Sai; FOR UPDATE yêu cầu khóa hàng |
| NOWAIT trả dữ liệu cũ | Không; NOWAIT thay đổi cách chờ lấy khóa |
| SKIP LOCKED luôn trả mọi hàng thỏa WHERE | Sai; hàng đang bị khóa bị bỏ qua |
| MVCC ngăn lost update mọi trường hợp | Sai; ứng dụng có thể ghi giá trị tính từ snapshot cũ |
| ORA-00060 là lỗi undo | Không; đó là deadlock |
| COMMIT sau mỗi câu SQL luôn tốt | Có thể phá ranh giới nghiệp vụ và làm thay đổi thời gian giữ khóa |
| Khóa bảng EXCLUSIVE chỉ khóa một hàng | Sai; nó tác động ở cấp bảng |
| Kill blocker luôn an toàn | Sai; transaction có thể phải rollback và ảnh hưởng ứng dụng |

### 14.1. Phân biệt các tình huống

- **Row lock wait:** writer chờ writer đang giữ khóa hàng.
- **Table lock wait:** thao tác cần khóa bảng không tương thích với khóa hiện có.
- **Deadlock:** có vòng chờ giữa nhiều transaction; Oracle phát hiện và báo ORA-00060.
- **Snapshot too old:** thiếu undo cần thiết cho consistent read; không phải lỗi khóa.
- **Serialization conflict:** transaction SERIALIZABLE có thể nhận ORA-08177.

Chẩn đoán đúng loại vấn đề trước khi thay đổi timeout, undo hoặc code ứng dụng.

## 15. Quy trình thiết kế và vận hành

Khi thiết kế thao tác đọc/ghi đồng thời, xác định:

1. **Reader cần snapshot nào?** Một statement hay nhiều statement trong transaction?
2. **Có writer cạnh tranh không?** Những hàng nào có thể bị nhiều session sửa?
3. **Có cần khóa chủ động?** SELECT FOR UPDATE hay UPDATE nguyên tử?
4. **Điều kiện cập nhật có an toàn không?** Có thể đặt điều kiện nghiệp vụ trong WHERE không?
5. **Có nguy cơ lost update không?** Dùng phép tính trong SQL, khóa pessimistic hay version column?
6. **Có nguy cơ deadlock không?** Mọi transaction có khóa theo cùng thứ tự không?
7. **Có cần timeout không?** Chọn mặc định, NOWAIT hoặc WAIT n theo UX.
8. **Có cần bỏ qua hàng bận không?** SKIP LOCKED chỉ phù hợp với queue/work distribution.
9. **Transaction dài bao lâu?** Giảm thời gian giữ row/table locks.
10. **Có quan sát được blocking không?** Theo dõi V$SESSION, V$LOCK, SQL_ID và deadlock trace.

Một số nguyên tắc thực hành:
- Giữ transaction ngắn và có ranh giới nghiệp vụ rõ.
- Dùng SELECT thường khi chỉ đọc dữ liệu.
- Dùng SELECT FOR UPDATE khi phải khóa hàng trước khi đọc và quyết định.
- Ưu tiên UPDATE có điều kiện nguyên tử cho thao tác đơn giản.
- Kiểm tra số hàng bị ảnh hưởng sau DML.
- Khóa nhiều hàng theo thứ tự ổn định để giảm deadlock.
- Xử lý timeout và retry có giới hạn.
- Không kết thúc blocker khi chưa hiểu transaction của nó.

## 16. Bài tập thực hành

### Bài 1 — Reader đọc phiên bản cũ

Session A UPDATE quantity từ 10 xuống 9 nhưng chưa commit. Session B SELECT hàng đó.

**Kỳ vọng:** B thấy 10 qua consistent read.

### Bài 2 — Writer phải chờ

Trong khi A chưa commit, B UPDATE cùng hàng.

**Kỳ vọng:** B chờ row lock. A COMMIT/ROLLBACK thì B mới tiếp tục.

### Bài 3 — Hai hàng khác nhau

A UPDATE item_id=1, B UPDATE item_id=2 trong cùng bảng.

**Kỳ vọng:** không có row conflict trực tiếp; hai session có thể chạy đồng thời nếu không có tài nguyên khác xung đột.

### Bài 4 — INSERT trùng khóa

A INSERT khóa chính mới nhưng chưa commit. B INSERT cùng khóa.

**Kỳ vọng:** B có thể chờ kết quả transaction A; A commit thì B vi phạm uniqueness, A rollback thì B có thể tiếp tục.

### Bài 5 — SELECT FOR UPDATE NOWAIT

A khóa hàng bằng UPDATE. B chạy SELECT FOR UPDATE NOWAIT.

**Kỳ vọng:** B trả lỗi ngay thay vì chờ.

### Bài 6 — SELECT FOR UPDATE WAIT

Lặp lại nhưng dùng WAIT 3.

**Kỳ vọng:** B chờ tối đa 3 giây rồi trả lỗi nếu khóa chưa được giải phóng.

### Bài 7 — SKIP LOCKED

A khóa một số hàng READY trong queue. B chạy SELECT FOR UPDATE SKIP LOCKED.

**Kỳ vọng:** B bỏ qua hàng A khóa và có thể lấy các hàng READY khác.

### Bài 8 — Lost update

Hai session cùng SELECT balance 100, mỗi bên tính 90 rồi UPDATE balance=90.

**Kỳ vọng:** giá trị cuối có thể là 90. Lặp lại bằng UPDATE balance=balance-10 để quan sát kết quả 80.

### Bài 9 — Optimistic locking

Thêm version_no. Hai session đọc cùng version, session đầu cập nhật tăng version, session thứ hai UPDATE với version cũ.

**Kỳ vọng:** UPDATE thứ hai ảnh hưởng 0 hàng và ứng dụng nhận biết xung đột.

### Bài 10 — Deadlock

Dùng bảng demo_deadlock: A khóa hàng 1, B khóa hàng 2, sau đó A cần hàng 2 và B cần hàng 1.

**Kỳ vọng:** Oracle phát hiện deadlock và một statement nhận ORA-00060.

### Bài 11 — Quan sát V$SESSION

Khi một session đang chờ, truy vấn V$SESSION để tìm blocking_session, event, seconds_in_wait và SQL_ID.

**Mục tiêu:** hiểu cách xác định blocker và waiter.

### Bài 12 — Chuyển tiền an toàn

Viết transaction trừ tiền tài khoản nguồn, cộng tiền tài khoản đích, kiểm tra số dư và khóa tài khoản theo thứ tự account_id.

**Mục tiêu:** bảo đảm atomicity và giảm nguy cơ deadlock.

## 17. Tài liệu Oracle tham khảo

- [Oracle Database Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): read consistency, concurrency và transaction.
- [Oracle Database Concepts — Data Concurrency and Consistency: Locking](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): cơ chế khóa dữ liệu.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT FOR UPDATE, WAIT, NOWAIT và SKIP LOCKED.
- [Oracle Database SQL Language Reference — LOCK TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LOCK-TABLE.html): khóa bảng và các chế độ lock.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị session, transaction và các tài nguyên database.
- [Oracle Database Reference — V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html): thông tin session và blocking.
- [Oracle Database Reference — V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-LOCK.html): thông tin lock đang giữ hoặc được yêu cầu.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/): ORA-00054, ORA-00060 và các lỗi liên quan.

Trong Oracle, read consistency cho phép SELECT thông thường đọc một snapshot đã commit bằng undo trong khi writer thay đổi hàng. Các thao tác ghi cạnh tranh trên cùng hàng cần row lock và có thể phải chờ; SELECT FOR UPDATE cũng chủ động lấy khóa. Hãy phân biệt blocking bình thường, lost update và deadlock, chọn cách cập nhật nguyên tử hoặc khóa phù hợp với nghiệp vụ, đồng thời giữ transaction ngắn và theo dõi session đang chờ để vận hành hệ thống an toàn.
