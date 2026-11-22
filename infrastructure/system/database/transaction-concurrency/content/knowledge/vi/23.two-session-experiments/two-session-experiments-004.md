# Tái hiện mất cập nhật bằng chuỗi đọc–tính toán–ghi

**Mất cập nhật (lost update)** xảy ra khi hai giao dịch cùng đọc một giá trị cũ, mỗi giao dịch tự tính giá trị mới ở phía ứng dụng rồi ghi lại toàn bộ giá trị. Giao dịch ghi sau có thể ghi đè kết quả của giao dịch ghi trước, khiến một phần thay đổi bị mất dù cả hai giao dịch đều commit thành công.

Bài thực nghiệm này dùng hai session database độc lập để tái hiện lỗi theo đúng thứ tự: **đọc → tính toán → ghi**. Sau đó, ta thay đổi cách ghi bằng phép cập nhật nguyên tử, khóa bi quan hoặc kiểm tra version để thấy cách ngăn lỗi. Trọng tâm là quan sát thứ tự xen kẽ giữa hai session và hiểu vì sao một câu `UPDATE` hợp lệ vẫn có thể ghi đè dữ liệu nếu giá trị gửi lên đã được tính từ một lần đọc cũ.

## 1. Mục tiêu và điều kiện thực nghiệm

Sau bài thực hành, có thể:

- Mở hai session độc lập và điều phối từng bước của hai transaction.
- Tạo một interleaving xác định để cả hai session đọc cùng một giá trị ban đầu.
- Tính giá trị mới ở phía ứng dụng rồi ghi bằng giá trị tuyệt đối để tái hiện lost update.
- Tính kết quả đúng và so sánh với kết quả thực tế sau hai lần commit.
- Sửa lỗi bằng phép cập nhật dựa trên giá trị hiện tại trong database.
- Sửa lỗi bằng `SELECT ... FOR UPDATE` hoặc cơ chế khóa tương ứng.
- Dùng optimistic version để phát hiện lần ghi dựa trên dữ liệu cũ.
- Nhận biết isolation level có thể thay đổi kết quả của cùng một lịch thực thi.

Ta dùng PostgreSQL với isolation level `READ COMMITTED` cho thí nghiệm chính vì hành vi dễ quan sát: một `SELECT` thông thường không giữ row lock sau khi câu lệnh kết thúc, còn mỗi câu lệnh ở `READ COMMITTED` lấy snapshot mới. Có thể chạy bằng hai cửa sổ `psql`, hai tab SQL client hoặc hai kết nối vật lý khác nhau.

**Quan trọng:** hai cửa sổ phải dùng hai connection/session khác nhau. Hai tab ứng dụng cùng chia sẻ một connection hoặc một transaction không tạo ra thí nghiệm đồng thời như mong muốn.

## 2. Chuẩn bị bảng thử nghiệm

Chạy phần khởi tạo một lần trong một session quản trị trước khi mở hai session A và B:

```sql
DROP TABLE IF EXISTS account_demo;

CREATE TABLE account_demo (
    account_id INTEGER PRIMARY KEY,
    balance    INTEGER NOT NULL CHECK (balance >= 0),
    version    INTEGER NOT NULL DEFAULT 0
);

INSERT INTO account_demo (account_id, balance, version)
VALUES (1, 100, 0);

SELECT * FROM account_demo;
```

Kết quả ban đầu:

| account_id | balance | version |
|---:|---:|---:|
| 1 | 100 | 0 |

Giả sử hai yêu cầu nghiệp vụ độc lập cùng rút tiền từ tài khoản này:

- T1 muốn trừ 10.
- T2 muốn trừ 20.

Nếu cả hai thành công, số dư đúng phải là:

```text
100 - 10 - 20 = 70
```

`balance` dùng số nguyên để bài thực hành tập trung vào concurrency, không bị nhiễu bởi quy tắc làm tròn tiền tệ. Trong hệ thống thực tế, kiểu dữ liệu tiền cần được chọn theo đơn vị nhỏ nhất hoặc `NUMERIC/DECIMAL` phù hợp.

## 3. Mở hai session độc lập

Mở hai cửa sổ terminal và kết nối cùng một database. Ví dụ với `psql`:

```bash
psql "host=localhost port=5432 dbname=demo user=demo_user"
```

Chạy lệnh trên hai lần để có hai kết nối riêng. Có thể đặt nhãn để dễ nhận diện:

```sql
-- Chạy trong session A
SET application_name = 'lost-update-session-A';

-- Chạy trong session B
SET application_name = 'lost-update-session-B';
```

Không chạy cả hai luồng trong cùng một connection. Ta cần giữ trạng thái transaction và giá trị đọc độc lập giữa hai session.

## 4. Thực nghiệm 1: tái hiện lost update

Trong thí nghiệm này, mỗi session đọc số dư, tự tính số dư mới rồi gửi một giá trị tuyệt đối vào `UPDATE`. Không session nào khóa dòng trong lúc đọc thông thường.

### Bước 1: Session A đọc và tính toán

Chạy trong session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_demo
WHERE account_id = 1;
```

Kết quả là `100`. Ứng dụng A giữ giá trị này trong bộ nhớ và tính:

```text
balance_A_new = 100 - 10 = 90
```

Tạm dừng session A tại đây. Chưa chạy `UPDATE` và chưa commit.

### Bước 2: Session B cũng đọc và tính toán

Chạy trong session B:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_demo
WHERE account_id = 1;
```

Session B cũng nhận `100`, vì A chưa ghi thay đổi. Ứng dụng B tính:

```text
balance_B_new = 100 - 20 = 80
```

Tạm dừng B. Lúc này cả hai ứng dụng đều tin rằng giá trị hiện tại là 100, dù mỗi ứng dụng đang giữ một phép tính khác nhau.

### Bước 3: Session A ghi và commit

Quay lại session A:

```sql
UPDATE account_demo
SET balance = 90
WHERE account_id = 1;

COMMIT;
```

Database lưu `balance = 90`.

### Bước 4: Session B ghi giá trị đã tính từ dữ liệu cũ

Quay lại session B:

```sql
UPDATE account_demo
SET balance = 80
WHERE account_id = 1;

COMMIT;
```

Database lưu `balance = 80`. Câu lệnh của B ghi đè 90 bằng 80, bởi ứng dụng gửi lên một giá trị tuyệt đối được tính từ lần đọc ban đầu.

### Bước 5: Kiểm tra kết quả

Chạy trong một session bất kỳ:

```sql
SELECT account_id, balance
FROM account_demo
WHERE account_id = 1;
```

Kết quả:

| Kết quả | Số dư |
|---|---:|
| Giá trị ban đầu | 100 |
| T1 trừ 10 theo tính toán của T1 | 90 |
| T2 trừ 20 theo tính toán của T2 | 80 |
| Giá trị đúng nếu cả hai lần rút được tính | **70** |
| Giá trị thực tế sau lost update | **80** |

Tác động của T1 đã bị mất. T1 và T2 đều báo commit thành công, nhưng hệ thống chỉ phản ánh lần trừ 20. `CHECK (balance >= 0)` không phát hiện lỗi này vì 80 vẫn là giá trị hợp lệ theo constraint.

## 5. Lịch thực thi của hai session

Có thể mô tả thứ tự xen kẽ vừa thực hiện như sau:

```text
Session A                         Session B
------------------------------    ------------------------------
BEGIN                             BEGIN
SELECT balance -> 100             SELECT balance -> 100
Tính 100 - 10 = 90                Tính 100 - 20 = 80
UPDATE balance = 90
COMMIT
                                  UPDATE balance = 80
                                  COMMIT

Kết quả cuối: balance = 80
```

Vấn đề nằm ở chỗ mỗi ứng dụng thực hiện phép tính từ một bản sao giá trị đã đọc. Câu `UPDATE balance = 80` không nói với database rằng “hãy trừ 20 khỏi giá trị hiện tại”; nó nói “hãy đặt balance thành 80”. Vì thế, nếu giá trị hiện tại đã đổi từ 100 thành 90, câu lệnh vẫn có thể thay nó bằng 80.

Đây là lost update theo mô hình đọc–tính toán–ghi ở tầng ứng dụng. Không cần hai câu `UPDATE` thực sự chạy cùng một thời điểm. Chỉ cần lần đọc của B xảy ra trước khi A commit, còn lần ghi của B xảy ra sau khi A commit, B vẫn có thể ghi đè kết quả của A.

## 6. Thực nghiệm 2: dùng phép cập nhật nguyên tử

Một cách sửa là để database thực hiện phép biến đổi trên giá trị hiện tại thay vì gửi lại giá trị đã tính từ lần đọc trước.

Đặt lại dữ liệu trong một session sau khi cả hai transaction trước đã kết thúc:

```sql
UPDATE account_demo
SET balance = 100,
    version = 0
WHERE account_id = 1;
```

Session A chạy:

```sql
BEGIN;

UPDATE account_demo
SET balance = balance - 10
WHERE account_id = 1;

COMMIT;
```

Session B chạy cùng lúc hoặc sau đó:

```sql
BEGIN;

UPDATE account_demo
SET balance = balance - 20
WHERE account_id = 1;

COMMIT;
```

Khi cả hai câu `UPDATE` cùng tranh chấp trên một dòng, PostgreSQL điều phối việc ghi bằng row lock. Ở `READ COMMITTED`, nếu một câu `UPDATE` phải chờ transaction kia, nó tiếp tục áp dụng biểu thức trên phiên bản dòng hiện tại sau khi lock được giải phóng. Vì biểu thức là `balance - amount`, cả hai lần trừ đều được tính:

```text
100 - 10 = 90
90 - 20  = 70
```

Kết quả cuối là `70`, bất kể transaction nào lấy row lock trước, miễn cả hai thao tác đều hợp lệ và commit.

### 6.1. Thêm điều kiện đủ số dư

Với tài khoản, không chỉ cần tránh lost update mà còn phải ngăn số dư âm. Hãy đưa điều kiện vào cùng câu `UPDATE`:

```sql
UPDATE account_demo
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
```

Ứng dụng phải kiểm tra số dòng bị cập nhật:

- `1`: cập nhật thành công; số dư đủ tại thời điểm database thực hiện ghi.
- `0`: tài khoản không tồn tại hoặc số dư không đủ (có thể đọc thêm trong transaction để phân biệt nếu cần).

Ví dụ nếu hai session cùng rút 80 và 50 từ số dư 100, chỉ một thao tác có thể thành công. Sau khi thao tác đầu commit, thao tác còn lại đánh giá điều kiện trên số dư hiện tại 20 hoặc 50 và không cập nhật nếu không đủ tiền.

### 6.2. Khi nào atomic update chưa đủ?

Phép cập nhật nguyên tử phù hợp khi nghiệp vụ có thể biểu diễn trực tiếp bằng một biểu thức trên dòng hiện tại, ví dụ tăng/giảm bộ đếm hoặc trừ số lượng tồn kho. Nếu ứng dụng cần đọc nhiều cột, áp dụng quy tắc phức tạp hoặc cập nhật nhiều dòng có quan hệ, có thể cần transaction và khóa tường minh để bảo vệ toàn bộ quyết định.

## 7. Thực nghiệm 3: khóa dòng trước khi đọc bằng SELECT FOR UPDATE

Một cách khác là lấy khóa độc quyền trên dòng trước khi đọc số dư. Session thứ hai phải chờ và chỉ đọc sau khi session thứ nhất hoàn tất.

Đặt lại dữ liệu:

```sql
UPDATE account_demo
SET balance = 100,
    version = 0
WHERE account_id = 1;
```

### Bước 1: Session A lấy khóa và đọc

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_demo
WHERE account_id = 1
FOR UPDATE;
```

A đọc `100` và giữ row lock đến khi transaction kết thúc. Ứng dụng A tính số dư mới là `90`.

### Bước 2: Session B yêu cầu cùng khóa

Trong session B:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_demo
WHERE account_id = 1
FOR UPDATE;
```

Lệnh của B sẽ chờ vì A đang giữ khóa dòng. B chưa thể đọc và tính toán trên cùng dòng cho đến khi A kết thúc transaction.

### Bước 3: A ghi và commit

Trong session A:

```sql
UPDATE account_demo
SET balance = 90
WHERE account_id = 1;

COMMIT;
```

Sau commit, khóa được giải phóng.

### Bước 4: B tiếp tục và đọc giá trị mới

Lệnh `SELECT ... FOR UPDATE` đang chờ của B tiếp tục. Ở PostgreSQL `READ COMMITTED`, B khóa và nhận phiên bản dòng đã cập nhật, với `balance = 90`. B tính `90 - 20 = 70`:

```sql
UPDATE account_demo
SET balance = 70
WHERE account_id = 1;

COMMIT;
```

Kết quả cuối là `70`. B không ghi từ giá trị 100 cũ vì nó chỉ đọc sau khi lấy được khóa.

### 7.1. Vì sao phải khóa trước khi đọc?

Nếu ứng dụng đọc trước, tính toán trước rồi mới lấy khóa, một giao dịch khác vẫn có thể thay đổi dòng trong khoảng thời gian đó. Khóa cần được lấy trước khi đọc dữ liệu dùng để ra quyết định và phải được giữ đến khi ghi xong.

`SELECT FOR UPDATE` là cú pháp PostgreSQL và được InnoDB hỗ trợ với locking read tương ứng. SQL Server dùng hint như `UPDLOCK` hoặc cơ chế transaction/locking khác. Cần đọc tài liệu DBMS cụ thể về thời gian giữ khóa, isolation level và hành vi sau khi chờ.

## 8. Thực nghiệm 4: optimistic locking bằng version

Optimistic locking cho phép nhiều session đọc mà không khóa dòng dài hạn, nhưng yêu cầu câu `UPDATE` xác nhận rằng dữ liệu chưa bị thay đổi kể từ lần đọc.

Bảng đã có cột `version`. Đặt lại:

```sql
UPDATE account_demo
SET balance = 100,
    version = 0
WHERE account_id = 1;
```

### Bước 1: cả hai session đọc cùng version

Session A:

```sql
BEGIN;
SELECT balance, version
FROM account_demo
WHERE account_id = 1;
```

Session B:

```sql
BEGIN;
SELECT balance, version
FROM account_demo
WHERE account_id = 1;
```

Cả hai nhận `balance = 100`, `version = 0`. A tính 90; B tính 80.

### Bước 2: A cập nhật có điều kiện version

```sql
UPDATE account_demo
SET balance = 90,
    version = version + 1
WHERE account_id = 1
  AND version = 0;

COMMIT;
```

Một dòng được cập nhật; version trở thành 1.

### Bước 3: B thử cập nhật bằng version đã đọc

```sql
UPDATE account_demo
SET balance = 80,
    version = version + 1
WHERE account_id = 1
  AND version = 0;
```

Không có dòng nào được cập nhật vì version hiện tại là 1. Ứng dụng phát hiện xung đột thông qua row count bằng 0 và rollback transaction B:

```sql
ROLLBACK;
```

B phải đọc lại dữ liệu mới (`balance = 90`, `version = 1`), tính lại kết quả `70` rồi thử một transaction mới:

```sql
BEGIN;

UPDATE account_demo
SET balance = 70,
    version = version + 1
WHERE account_id = 1
  AND version = 1;

COMMIT;
```

Kết quả cuối là 70. Optimistic locking không ngăn hai session đọc cùng dữ liệu; nó ngăn session ghi dữ liệu dựa trên version đã lỗi thời mà không nhận ra xung đột.

### 8.1. Điều kiện quan trọng của version check

- Mọi đường cập nhật liên quan phải tăng version.
- Câu `UPDATE` phải có điều kiện `WHERE version = :version_read`.
- Ứng dụng phải kiểm tra số dòng tác động; không được bỏ qua kết quả 0.
- Khi xung đột, phải đọc lại và tính toán lại toàn bộ quyết định phụ thuộc dữ liệu cũ.
- Version nên có kiểu đủ lớn và không được reset tùy tiện khiến giá trị cũ trùng lại.

Optimistic version hữu ích khi xung đột ít và việc retry rẻ. Nếu cùng một dòng bị cập nhật liên tục, nhiều request có thể thất bại và retry; khóa bi quan hoặc tuần tự hóa theo tài nguyên có thể phù hợp hơn.

## 9. So sánh ba cách sửa

| Cách làm | Cách bảo vệ | Kết quả khi hai session cùng cập nhật |
|---|---|---|
| Atomic update | Database áp dụng biểu thức trên giá trị hiện tại | Cả hai phép cộng/trừ có thể được tính tuần tự trên cùng dòng |
| Pessimistic lock | Khóa dòng trước khi đọc và giữ đến khi ghi xong | Session sau chờ, rồi đọc giá trị mới nhất phù hợp |
| Optimistic version | Ghi chỉ thành công nếu version vẫn bằng version đã đọc | Một session thành công; session còn lại phát hiện xung đột và phải retry |

Không có một lựa chọn luôn tốt nhất. Atomic update đơn giản khi nghiệp vụ biểu diễn được bằng một câu lệnh. Pessimistic locking phù hợp khi cần đọc nhiều giá trị rồi ra quyết định trong critical section. Optimistic locking phù hợp khi tranh chấp hiếm và ứng dụng có thể xử lý retry.

## 10. Isolation level ảnh hưởng thế nào?

Kết quả của lịch đọc–tính toán–ghi phụ thuộc DBMS và isolation level. Cần phân biệt hành vi đọc snapshot với hành vi ghi và cơ chế phát hiện cập nhật xung đột.

### 10.1. PostgreSQL READ COMMITTED

Đây là mức dùng trong thí nghiệm chính. Mỗi câu lệnh có snapshot mới. Một `SELECT` thông thường không giữ row lock sau khi hoàn tất, nên hai session có thể cùng đọc 100. Nếu B sau đó chạy `UPDATE ... SET balance = 80` sau khi A đã commit, B có thể cập nhật phiên bản hiện tại bằng giá trị tuyệt đối 80. Lost update được tái hiện.

### 10.2. PostgreSQL REPEATABLE READ và SERIALIZABLE

Trong PostgreSQL, `REPEATABLE READ` dùng snapshot ổn định cho transaction. Nếu B đã đọc dòng ở snapshot cũ, rồi A cập nhật và commit dòng đó trước khi B cố cập nhật, B thường nhận lỗi:

```text
ERROR: could not serialize access due to concurrent update
```

Transaction B bị abort và phải chạy lại từ đầu với snapshot mới. `SERIALIZABLE` cũng có thể hủy transaction để bảo đảm lịch tuần tự hóa được. Đây là hành vi cụ thể của PostgreSQL; không nên suy rộng tên isolation level sang DBMS khác mà không kiểm tra tài liệu.

### 10.3. MySQL InnoDB

InnoDB mặc định thường dùng `REPEATABLE READ`. Một `SELECT` thông thường có thể đọc snapshot, trong khi `UPDATE` là current read và lấy khóa ghi trên phiên bản hiện tại. Nếu ứng dụng gửi một giá trị tuyệt đối đã tính từ snapshot cũ, lệnh update vẫn có thể ghi giá trị cũ đó lên phiên bản hiện tại. Vì vậy, việc chỉ dùng `REPEATABLE READ` không thay thế cho atomic expression, khóa trước khi đọc hoặc optimistic version.

### 10.4. SQL Server

Ở `READ COMMITTED` dạng locking, shared lock của một câu `SELECT` thông thường thường được giải phóng sau statement. Một ứng dụng đọc số dư, tính toán ở client rồi gửi `UPDATE SET balance = <giá trị cũ đã tính>` vẫn có thể ghi đè cập nhật khác. `READ_COMMITTED_SNAPSHOT` thay đổi cách đọc bằng row versioning nhưng không tự biến một giá trị tuyệt đối đã tính từ snapshot thành phép cập nhật an toàn.

SQL Server `SNAPSHOT` có cơ chế phát hiện update conflict và có thể hủy transaction khi một dòng đã bị transaction khác sửa sau snapshot. `rowversion` cũng thường được dùng làm optimistic concurrency token trong câu `UPDATE` có điều kiện.

## 11. Một biến thể: hai session cùng rút tiền và số dư âm

Lost update có thể che giấu một lỗi nghiệp vụ nghiêm trọng hơn. Giả sử số dư là 100, T1 muốn rút 80 và T2 muốn rút 50. Cả hai cùng đọc 100:

```text
T1 đọc 100 -> kiểm tra 100 >= 80 -> hợp lệ
T2 đọc 100 -> kiểm tra 100 >= 50 -> hợp lệ
```

Nếu mỗi session ghi số dư tuyệt đối theo phép tính riêng:

```text
T1 ghi 20
T2 ghi 50
```

Kết quả cuối 50 nhưng một khoản rút bị mất. Nếu thay bằng hai phép trừ không điều kiện:

```sql
UPDATE account_demo SET balance = balance - 80 WHERE account_id = 1;
UPDATE account_demo SET balance = balance - 50 WHERE account_id = 1;
```

số dư có thể thành `-30`. Cả hai cách đều sai nếu nghiệp vụ không cho phép thấu chi.

Phép ghi đúng phải bao gồm điều kiện tại database:

```sql
UPDATE account_demo
SET balance = balance - :amount
WHERE account_id = 1
  AND balance >= :amount;
```

Với hai transaction chạy đồng thời ở PostgreSQL `READ COMMITTED`, một câu lệnh có thể chờ câu kia; sau khi tiếp tục, điều kiện được đánh giá trên phiên bản dòng hiện tại. Chỉ một lần rút có thể thành công nếu tổng số tiền vượt số dư. Ứng dụng cần kiểm tra row count và trả lỗi cho lần rút không đủ tiền.

## 12. Phân biệt lost update với các anomaly khác

Lost update không giống mọi lỗi đồng thời:

| Hiện tượng | Mô tả | Ví dụ |
|---|---|---|
| Lost update | Một lần ghi dựa trên dữ liệu cũ ghi đè kết quả của lần ghi khác | Hai session cùng đọc 100 rồi ghi 90 và 80 |
| Dirty read | Đọc dữ liệu chưa commit của transaction khác | T2 đọc giá trị T1 ghi rồi T1 rollback |
| Non-repeatable read | Đọc lại cùng dòng trong một transaction nhưng thấy giá trị đã commit khác | T1 đọc 100, T2 cập nhật 90 và commit, T1 đọc lại 90 ở isolation cho phép |
| Phantom read | Chạy lại truy vấn điều kiện và thấy tập dòng thay đổi | T2 chèn một dòng thỏa predicate giữa hai lần đọc của T1 |
| Write skew | Các transaction ghi các dòng khác nhau dựa trên cùng snapshot, kết hợp lại làm sai quy tắc | Hai bác sĩ cùng tắt ca trực của mình vì mỗi người thấy người kia vẫn trực |

Thí nghiệm này tập trung vào lost update ở một dòng. Các anomaly khác có thể cần range lock, predicate protection hoặc mức cô lập mạnh hơn.

## 13. Dọn và chạy lại thí nghiệm

Sau mỗi biến thể, đưa bảng về trạng thái ban đầu khi không còn transaction đang mở:

```sql
UPDATE account_demo
SET balance = 100,
    version = 0
WHERE account_id = 1;
```

Nếu một session đang ở trạng thái `idle in transaction` do bỏ dở bài thực hành, hãy `COMMIT` hoặc `ROLLBACK` trong đúng session trước khi reset. Không chạy lệnh reset giữa lúc session khác còn giữ khóa hoặc đang thực hiện thí nghiệm.

Có thể xác nhận trạng thái bằng:

```sql
SELECT * FROM account_demo WHERE account_id = 1;
```

Để tránh ảnh hưởng dữ liệu thật, luôn dùng database/schema thử nghiệm và không thực hiện các lệnh `DROP TABLE` trên môi trường có dữ liệu nghiệp vụ.

## 14. Câu hỏi tự kiểm tra

1. Vì sao hai session có thể cùng đọc `balance = 100` dù mỗi session đều nằm trong transaction riêng?
2. Trong thí nghiệm đầu, câu `UPDATE balance = 80` biểu đạt điều gì khác với `UPDATE balance = balance - 20`?
3. Tại sao unique constraint hoặc `CHECK (balance >= 0)` không tự ngăn lost update?
4. Nếu B đọc trước nhưng chỉ lấy `FOR UPDATE` sau khi A commit, B có đang bảo vệ phép tính dựa trên giá trị cũ không?
5. Vì sao `SELECT ... FOR UPDATE` phải xảy ra trước khi ứng dụng đọc dữ liệu dùng để tính toán?
6. Optimistic version phát hiện xung đột bằng điều kiện nào và ứng dụng phải làm gì khi row count bằng 0?
7. Vì sao PostgreSQL `REPEATABLE READ` có thể abort B trong khi `READ COMMITTED` cho phép lịch ghi đè ở thí nghiệm này?
8. Khi nào một atomic `UPDATE` là đủ, và khi nào cần khóa nhiều dòng hoặc bảo vệ predicate?

## 15. Kết luận

Lost update có thể tái hiện ổn định bằng hai session độc lập: cả hai đọc cùng một giá trị, tính các giá trị mới riêng ở ứng dụng, sau đó lần ghi thứ hai đặt giá trị tuyệt đối được tính từ dữ liệu cũ. Cả hai transaction có thể commit nhưng một thay đổi bị mất.

Để ngăn lỗi, hãy chọn cơ chế phù hợp với nghiệp vụ: biểu diễn phép biến đổi bằng một câu cập nhật nguyên tử, khóa dòng trước khi đọc và giữ khóa đến khi ghi xong, hoặc dùng version check để phát hiện và retry khi dữ liệu đã đổi. Đồng thời, kiểm tra isolation semantics của DBMS đang dùng; tên isolation level giống nhau không bảo đảm mọi sản phẩm xử lý lịch giao dịch giống nhau.
