# Chuyển tiền: tổng số dư, thứ tự khóa và ranh giới giao dịch

Chuyển tiền giữa hai tài khoản là ví dụ điển hình cho bài toán **bất biến nghiệp vụ trong giao dịch đồng thời**. Một thao tác phải trừ tiền ở tài khoản nguồn, cộng đúng số tiền đó vào tài khoản đích và ghi nhận lịch sử. Nếu chỉ một phần được commit, hệ thống có thể làm mất tiền hoặc tạo tiền. Nếu hai giao dịch cùng đọc số dư cũ rồi cập nhật, tài khoản có thể bị âm hoặc một lần chuyển bị ghi đè.

Để chuyển tiền an toàn, ứng dụng cần phối hợp ba điều:

1. **Bất biến dữ liệu:** xác định những điều luôn phải đúng, chẳng hạn số dư không âm và tổng ghi nợ bằng tổng ghi có theo từng loại tiền.
2. **Thứ tự khóa:** khóa các tài khoản liên quan theo cùng một thứ tự ở mọi luồng để giảm deadlock.
3. **Ranh giới transaction:** đặt kiểm tra, trừ tiền, cộng tiền và ghi sổ trong cùng một transaction để tất cả cùng commit hoặc cùng rollback.

Các phần dưới đây dùng ví dụ chuyển tiền nội bộ giữa hai tài khoản cùng loại tiền. Chuyển đổi ngoại tệ, phí, hệ thống thanh toán bên ngoài và sổ cái phân tán cần thêm quy tắc riêng.

## 1. Những bất biến của một lần chuyển tiền

Giả sử tài khoản A chuyển số tiền (x) cho tài khoản B. Trước giao dịch, số dư là (A_0) và (B_0). Sau khi chuyển thành công:

\[
A_1 = A_0 - x, \qquad B_1 = B_0 + x
\]

Với hai tài khoản cùng loại tiền và không tính phí, tổng số dư phải được bảo toàn:

\[
A_1 + B_1 = (A_0 - x) + (B_0 + x) = A_0 + B_0
\]

Một thao tác chuyển tiền thường phải duy trì các bất biến sau:

- **Bảo toàn giá trị:** số tiền bị trừ ở nguồn bằng số tiền được cộng ở đích, theo cùng loại tiền và quy tắc làm tròn.
- **Không âm:** số dư nguồn không thấp hơn 0, trừ khi sản phẩm cho phép thấu chi theo hạn mức riêng.
- **Tính nguyên tử:** hoặc cả khoản ghi nợ và ghi có đều có hiệu lực, hoặc không phần nào có hiệu lực.
- **Tính nhất quán:** tài khoản tồn tại, đang ở trạng thái cho phép giao dịch, cùng loại tiền nếu đây là chuyển nội tệ, và dữ liệu sổ cái khớp với số dư.
- **Không xử lý lặp:** cùng một yêu cầu chuyển tiền được gửi lại do timeout không được trừ tiền lần thứ hai.
- **Tính truy vết:** có mã giao dịch và các bút toán ghi nợ/ghi có để kiểm toán, đối soát và điều tra sai lệch.

Không nên kiểm tra tổng số dư toàn hệ thống bằng cách chạy `SUM(balance)` trước rồi sau mỗi lần chuyển. Phép kiểm tra đó có thể tốn kém và không tự bảo vệ được giao dịch khỏi thay đổi đồng thời. Thay vào đó, mỗi transaction phải ghi nhận hai phía một cách nguyên tử, còn đối soát tổng thể được thực hiện bằng sổ cái và quy trình kiểm tra chuyên biệt.

Nếu có phí (f), tổng số dư của hai tài khoản khách hàng sẽ giảm (f). Để bảo toàn giá trị trong sổ cái, khoản phí cần được ghi có vào tài khoản phí hoặc tài khoản doanh thu tương ứng. Nếu chuyển đổi ngoại tệ, không thể cộng trực tiếp số dư của hai loại tiền; cần các bút toán cân bằng theo từng loại tiền và tài khoản clearing/FX phù hợp.

## 2. Mô hình dữ liệu cơ bản

Ví dụ schema đơn giản cho tài khoản và sổ giao dịch:

```sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    currency   CHAR(3) NOT NULL,
    balance    NUMERIC(19, 4) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    CONSTRAINT ck_account_balance_nonnegative CHECK (balance >= 0)
);

CREATE TABLE transfer (
    transfer_id     BIGINT PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    from_account_id BIGINT NOT NULL REFERENCES account(account_id),
    to_account_id   BIGINT NOT NULL REFERENCES account(account_id),
    amount          NUMERIC(19, 4) NOT NULL,
    currency        CHAR(3) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    CONSTRAINT ck_transfer_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_transfer_distinct_accounts
        CHECK (from_account_id <> to_account_id)
);

CREATE TABLE ledger_entry (
    entry_id    BIGINT PRIMARY KEY,
    transfer_id BIGINT NOT NULL REFERENCES transfer(transfer_id),
    account_id  BIGINT NOT NULL REFERENCES account(account_id),
    direction   VARCHAR(6) NOT NULL,
    amount      NUMERIC(19, 4) NOT NULL,
    currency    CHAR(3) NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    CONSTRAINT ck_ledger_direction
        CHECK (direction IN ('DEBIT', 'CREDIT')),
    CONSTRAINT ck_ledger_amount_positive CHECK (amount > 0)
);
```

Đây là mô hình minh họa; kiểu ID, timestamp, độ chính xác tiền tệ và cấu trúc sổ cái phải được điều chỉnh theo DBMS và nghiệp vụ. `NUMERIC`/`DECIMAL` phù hợp với số tiền hơn kiểu dấu phẩy động nhị phân như `FLOAT` hoặc `DOUBLE`, vì phép tính tiền cần quy tắc thập phân có thể dự đoán.

`CHECK (balance >= 0)` là hàng rào bổ sung ở cấp dòng. Nó không thay thế việc khóa và kiểm tra đủ tiền trước khi ghi. `CHECK` cũng không thể tự đảm bảo tổng hai bút toán ở nhiều dòng bằng 0; điều đó phải được bảo đảm bằng transaction, thiết kế sổ cái và có thể cả quy trình đối soát.

Trong hệ thống tài chính, số dư có thể là giá trị tổng hợp từ sổ cái thay vì nguồn dữ liệu gốc. Dù lưu số dư hiện tại để đọc nhanh, ledger vẫn cần giữ các bút toán bất biến hoặc có cơ chế điều chỉnh bằng bút toán đảo, không sửa lịch sử một cách tùy tiện.

## 3. Vì sao phải dùng một transaction cho cả hai phía?

Giả sử số dư A là 500, số dư B là 200 và A chuyển 100 cho B. Nếu ứng dụng chạy hai câu lệnh ngoài transaction:

```sql
UPDATE account SET balance = balance - 100 WHERE account_id = 1;
UPDATE account SET balance = balance + 100 WHERE account_id = 2;
```

Sau câu đầu tiên, A còn 400 nhưng B vẫn 200. Nếu tiến trình bị dừng, mất kết nối hoặc câu lệnh thứ hai lỗi, trạng thái có thể bị lưu một nửa. Tổng số dư giảm từ 700 xuống 600.

Ranh giới transaction phải bao trùm toàn bộ thao tác:

```text
BEGIN
  khóa tài khoản nguồn và đích
  kiểm tra tài khoản và số dư
  trừ tiền nguồn
  cộng tiền đích
  ghi giao dịch và hai bút toán
COMMIT
```

Nếu bất kỳ bước nào thất bại trước commit:

```text
ROLLBACK
  hoàn tác khoản trừ nguồn
  hoàn tác khoản cộng đích (nếu đã chạy)
  hoàn tác bản ghi transfer và ledger chưa commit
```

Các transaction khác chỉ nhìn thấy trạng thái đã commit theo isolation semantics của DBMS. Một giao dịch đọc thông thường không được nhìn thấy trạng thái trung gian chỉ có khoản trừ mà chưa có khoản cộng.

Không được commit sau khi trừ nguồn rồi mở transaction mới để cộng đích nếu nghiệp vụ yêu cầu chuyển tiền nội bộ nguyên tử. Hai transaction riêng biệt sẽ tạo một khoảng thời gian mà tiền đã rời tài khoản nguồn nhưng chưa đến tài khoản đích.

## 4. Rủi ro khi không khóa hoặc không cập nhật có điều kiện

### 4.1. Hai lần rút cùng đọc một số dư cũ

Tài khoản A có 100. Hai giao dịch đồng thời muốn chuyển lần lượt 80 và 50:

```text
Ban đầu: A.balance = 100

T1: SELECT balance -> 100
T2: SELECT balance -> 100

T1: kiểm tra 100 >= 80 -> đúng
T2: kiểm tra 100 >= 50 -> đúng

T1: UPDATE balance = 20 -> COMMIT
T2: UPDATE balance = 50 -> COMMIT
```

Nếu T2 ghi giá trị tính từ snapshot cũ, khoản trừ của T1 có thể bị ghi đè. Nếu T2 dùng phép trừ trên giá trị hiện tại nhưng không có điều kiện đủ tiền, số dư có thể thành âm. Hai trường hợp đều cho thấy việc đọc số dư rồi quyết định ở phía ứng dụng cần được phối hợp với thao tác ghi.

### 4.2. Chỉ khóa tài khoản nguồn

Khóa nguồn giúp ngăn hai lần rút cùng tài khoản chạy qua bước kiểm tra cùng lúc, nhưng tài khoản đích vẫn có thể bị nhiều transaction cùng cập nhật. DBMS thường sẽ phối hợp các thao tác ghi trên cùng dòng đích, nhưng ứng dụng vẫn phải xử lý các quy tắc liên quan đến trạng thái, loại tiền, giới hạn nhận tiền và ledger. Cách dễ hiểu và nhất quán hơn là khóa tất cả tài khoản liên quan trong cùng một transaction.

### 4.3. Cập nhật không điều kiện

Lệnh:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :source_id;
```

không tự đảm bảo đủ tiền. Nên đặt điều kiện trong câu lệnh:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :source_id
  AND status = 'ACTIVE'
  AND balance >= :amount;
```

Ứng dụng phải kiểm tra đúng một dòng được cập nhật. Nếu không có dòng nào, có thể tài khoản không tồn tại, không hoạt động hoặc không đủ số dư; transaction cần rollback và trả kết quả nghiệp vụ thích hợp. Có thể đã khóa và đọc tài khoản trước đó để phân biệt nguyên nhân một cách rõ ràng.

## 5. Khóa hai tài khoản theo cùng một thứ tự

Một giao dịch chuyển tiền cần khóa cả tài khoản nguồn và đích để kiểm tra và thay đổi trạng thái nhất quán. Nếu các transaction lấy khóa theo thứ tự khác nhau, deadlock có thể xảy ra.

Giả sử T1 chuyển từ A sang B và T2 chuyển từ B sang A:

```text
T1                              T2
---------------------------     ---------------------------
LOCK(A)                         LOCK(B)
                                LOCK(A) -> phải chờ T1
LOCK(B) -> phải chờ T2
```

T1 giữ A và chờ B; T2 giữ B và chờ A. Mỗi transaction chờ tài nguyên do transaction kia giữ, tạo thành chu trình deadlock. DBMS phải chọn một transaction làm nạn nhân để rollback.

### 5.1. Quy tắc thứ tự toàn cục

Giải pháp thông dụng là khóa các tài khoản theo thứ tự tăng dần của `account_id`, bất kể tài khoản nào là nguồn hoặc đích.

```text
T1 chuyển A -> B, giả sử A.id = 10 và B.id = 20:
  LOCK(10)
  LOCK(20)

T2 chuyển B -> A:
  LOCK(10)
  LOCK(20)
```

T2 cũng khóa 10 trước rồi mới khóa 20. Nó có thể chờ ngay tại tài khoản 10, nhưng không giữ tài khoản 20 trong lúc chờ 10. Nhờ thứ tự thống nhất, chu trình chờ do hai tài khoản này bị giảm đáng kể.

Quy tắc cần được áp dụng ở mọi luồng có thể khóa cùng tập tài nguyên: chuyển tiền, hoàn tiền, điều chỉnh số dư, đóng tài khoản, chuyển trạng thái hoặc tác vụ quản trị. Nếu một luồng khóa tài khoản rồi mới khóa bản ghi transfer, còn luồng khác khóa transfer rồi mới khóa tài khoản, deadlock vẫn có thể xuất hiện giữa hai loại tài nguyên.

### 5.2. Khóa theo ID đã sắp xếp

Một cách triển khai dễ kiểm soát là tính danh sách ID duy nhất rồi khóa từng tài khoản theo thứ tự tăng dần. Pseudocode:

```text
ids = sort(unique([source_account_id, destination_account_id]))

for id in ids:
    SELECT account_id, balance, currency, status
    FROM account
    WHERE account_id = :id
    FOR UPDATE
```

Đây là pseudocode; `FOR UPDATE` là cú pháp phổ biến ở PostgreSQL và MySQL InnoDB. Các DBMS khác có cú pháp khóa tương ứng. Nếu hai ID giống nhau, `unique` chỉ giữ một ID, nhưng nghiệp vụ chuyển tiền thường nên từ chối chuyển từ tài khoản sang chính nó hoặc xử lý như một thao tác no-op được định nghĩa rõ.

Không nên chỉ dựa vào thứ tự nguồn/đích được gửi từ client. Nếu T1 khóa nguồn rồi đích, T2 khóa nguồn rồi đích nhưng hướng chuyển ngược lại, thứ tự tài nguyên thực tế vẫn ngược nhau. Thứ tự phải dựa trên một khóa ổn định, chẳng hạn ID tài khoản.

### 5.3. `ORDER BY ... FOR UPDATE` có luôn đủ không?

Một số DBMS cho phép truy vấn nhiều dòng với `ORDER BY account_id FOR UPDATE`. Cách này thường hữu ích, nhưng chi tiết thứ tự lấy khóa và tương tác với kế hoạch thực thi khác nhau theo sản phẩm. Khi yêu cầu kiểm soát thứ tự khóa thật chặt, hãy kiểm tra tài liệu DBMS và lock behavior của phiên bản đang dùng. Vòng lặp khóa từng ID theo thứ tự rõ ràng giúp ý định dễ thấy hơn, dù có thêm round trip nếu không được tối ưu bằng stored procedure hoặc batch phù hợp.

## 6. Ranh giới transaction của thao tác chuyển tiền

Một transaction an toàn thường bao gồm các bước sau:

1. Bắt đầu transaction.
2. Nhận diện yêu cầu bằng idempotency key và đảm bảo request chưa được xử lý.
3. Khóa các tài khoản nguồn/đích theo thứ tự ID tăng dần.
4. Kiểm tra cả hai tài khoản tồn tại, đang hoạt động, có loại tiền tương thích và không bị hạn chế giao dịch.
5. Xác nhận số tiền dương, hợp lệ về độ chính xác và nguồn đủ số dư.
6. Trừ tiền nguồn với điều kiện `balance >= amount`; kiểm tra số dòng tác động.
7. Cộng tiền đích.
8. Ghi transfer record, bút toán debit/credit và outbox event nếu cần phát sự kiện.
9. Commit.
10. Sau commit, trả kết quả và để worker riêng phát sự kiện từ outbox.

```text
BEGIN TRANSACTION
       |
       v
Kiểm tra idempotency key
       |
       v
Khóa account ID nhỏ hơn
       |
       v
Khóa account ID lớn hơn
       |
       v
Kiểm tra trạng thái, tiền tệ, số dư
       |
       v
DEBIT nguồn + CREDIT đích
       |
       v
Ghi transfer + ledger + outbox
       |
       v
COMMIT
       |
       v
Phát event sau commit
```

Mọi lỗi trước commit phải dẫn đến rollback. Không trả thành công cho client trước khi commit được xác nhận.

## 7. Ví dụ SQL với khóa tường minh

Ví dụ dưới đây dùng cú pháp gần PostgreSQL. Ứng dụng đã kiểm tra đầu vào cơ bản và tính `low_id`, `high_id` bằng cách sắp xếp hai account ID. Các câu lệnh phải chạy trên cùng một connection và cùng một transaction.

```sql
BEGIN;

-- Bước 1: khóa theo thứ tự ID tăng dần.
SELECT account_id, currency, balance, status
FROM account
WHERE account_id = :low_id
FOR UPDATE;

SELECT account_id, currency, balance, status
FROM account
WHERE account_id = :high_id
FOR UPDATE;

-- Bước 2: ứng dụng kiểm tra:
--   * có đủ hai tài khoản
--   * cả hai ACTIVE
--   * currency giống nhau
--   * amount > 0 và hợp lệ theo scale tiền tệ
--   * source balance >= amount

-- Bước 3: ghi nợ có điều kiện như hàng rào cuối cùng.
UPDATE account
SET balance = balance - :amount
WHERE account_id = :source_id
  AND status = 'ACTIVE'
  AND balance >= :amount;

-- Ứng dụng yêu cầu row count = 1; nếu khác 1 thì ROLLBACK.

-- Bước 4: ghi có tài khoản đích.
UPDATE account
SET balance = balance + :amount
WHERE account_id = :destination_id
  AND status = 'ACTIVE';

-- Ứng dụng yêu cầu row count = 1; nếu khác 1 thì ROLLBACK.

-- Bước 5: ghi transfer và hai ledger entries trong cùng transaction.
INSERT INTO ledger_entry (...)
VALUES (...), (...);

COMMIT;
```

Phần `INSERT INTO ledger_entry` là placeholder vì cấu trúc ID, direction, reference và số bút toán phụ thuộc schema thực tế. Nếu update nguồn thành công nhưng update đích không thành công, ứng dụng phải rollback toàn bộ transaction; không được commit phần debit.

Với cùng tài khoản nguồn và đích, hai câu khóa có thể khóa cùng một dòng hai lần trong cùng transaction, nhưng phép chuyển không có ý nghĩa. Nên từ chối sớm bằng validation và có `CHECK (from_account_id <> to_account_id)` trong bảng transfer để bảo vệ thêm.

## 8. Cập nhật có điều kiện thay cho đọc rồi ghi mù

Ngay cả khi đã dùng `SELECT ... FOR UPDATE`, câu `UPDATE` có điều kiện vẫn hữu ích. Nó làm cho điều kiện “đủ số dư và tài khoản đang hoạt động” được kiểm tra tại điểm ghi, nơi DBMS điều phối cập nhật dòng.

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :source_id
  AND balance >= :amount
  AND status = 'ACTIVE';
```

Nếu số dòng bị tác động là 0, không thể tiếp tục ghi có. Cần rollback và trả lỗi nghiệp vụ như không đủ tiền, tài khoản bị khóa hoặc tài khoản không tồn tại. Nếu đã khóa và đọc trạng thái trước đó, ứng dụng có thể phân biệt nguyên nhân mà không tạo khoảng race mới.

Với nhiều loại giới hạn, ví dụ hạn mức chuyển trong ngày, cần bảo vệ cả dữ liệu thể hiện hạn mức đã dùng. Khóa hai account không tự khóa một bản ghi tổng hợp theo ngày nếu nó nằm ở bảng khác. Hãy xác định tất cả resource tham gia bất biến và khóa chúng theo một thứ tự toàn cục.

## 9. Tổng số dư và sổ cái kép

Trong ví dụ chuyển cùng loại tiền, hai bút toán phải cân bằng:

| Tài khoản | Hướng | Số tiền |
|---|---|---:|
| A | DEBIT | 100 |
| B | CREDIT | 100 |
| **Tổng ghi nợ / ghi có** | | **100 / 100** |

Nếu biểu diễn số tiền có dấu, tổng hai entry bằng 0:

\[
-100 + 100 = 0
\]

Sổ cái kép giúp truy vết giá trị di chuyển. Số dư tài khoản có thể được cập nhật đồng thời như một projection để đọc nhanh, nhưng ledger entries là bằng chứng nghiệp vụ về khoản chuyển. Nếu hệ thống dùng ledger làm nguồn dữ liệu gốc, số dư được tính từ các bút toán hoặc từ snapshot đã đối soát.

Một thiết kế tốt nên đảm bảo transfer ID duy nhất và liên kết hai bút toán với cùng transfer. Có thể dùng constraint để ngăn một transfer có nhiều bút toán cùng loại cho cùng tài khoản, ví dụ `UNIQUE(transfer_id, account_id, direction)` nếu phù hợp với nghiệp vụ. Quy tắc tổng debit bằng tổng credit qua nhiều dòng thường cần transaction logic, stored procedure hoặc quy trình kiểm tra ledger; `CHECK` trên một dòng không thể tự kiểm tra tổng các dòng khác.

Đối soát định kỳ có thể so sánh:

- Số dư materialized của từng tài khoản.
- Tổng các bút toán ledger theo tài khoản và loại tiền.
- Tổng debit và credit theo từng transfer hoặc batch.
- Tổng số dư theo loại tiền và tài khoản clearing phù hợp.

Đối soát phát hiện lỗi hoặc sai lệch; nó không thay thế transaction atomic khi chuyển tiền.

## 10. Isolation level và vai trò của row lock

Với hai tài khoản đã biết trước, một transaction ở `READ COMMITTED` kết hợp khóa tường minh trên các dòng tài khoản thường đủ để tuần tự hóa các thao tác chuyển tiền có cùng tài khoản, miễn là mọi luồng cập nhật tuân thủ cùng giao thức và các điều kiện được kiểm tra đúng.

`SELECT ... FOR UPDATE` khóa các dòng được chọn cho đến khi transaction kết thúc. Giao dịch khác muốn cập nhật hoặc khóa xung đột trên các dòng đó phải chờ. Sau khi T1 commit, T2 tiếp tục và phải đánh giá số dư hiện tại theo hành vi isolation của DBMS.

`SERIALIZABLE` có thể cung cấp bảo vệ mạnh hơn cho quy tắc phụ thuộc nhiều dòng hoặc predicate, nhưng có thể làm transaction bị abort do serialization failure. Ứng dụng phải có retry toàn bộ transaction. Chọn `SERIALIZABLE` không loại bỏ nhu cầu viết đúng transaction boundary, unique constraint hoặc xử lý deadlock.

Không nên cho rằng `REPEATABLE READ` có cùng hành vi ở mọi DBMS. Các hệ quản trị có thể dùng MVCC, khóa phạm vi hoặc cơ chế SSI khác nhau. Với chuyển tiền giữa hai ID đã biết, khóa dòng rõ ràng thường dễ hiểu và ít phụ thuộc hơn việc suy đoán một snapshot có tự bảo vệ bất biến hay không.

## 11. Deadlock vẫn có thể xảy ra

Khóa theo ID tăng dần làm giảm deadlock do hai transaction khóa cặp tài khoản theo hướng ngược nhau, nhưng không đảm bảo toàn hệ thống không bao giờ deadlock. Deadlock vẫn có thể xuất hiện do:

- Một luồng khác khóa tài nguyên theo thứ tự khác.
- Trigger hoặc foreign key khiến DBMS khóa thêm dòng/index entry.
- Transaction khóa tài khoản rồi khóa bảng hạn mức, trong khi luồng khác khóa bảng hạn mức rồi khóa tài khoản.
- Nhiều transfer khóa tập tài khoản có phần giao nhau và còn dùng resource phụ.
- Lock escalation hoặc cơ chế nội bộ của DBMS làm thay đổi footprint khóa.

Vì vậy:

1. Định nghĩa thứ tự khóa toàn cục cho mọi loại tài nguyên tham gia chuyển tiền.
2. Giữ transaction ngắn và tránh chờ dịch vụ ngoài khi đang giữ khóa.
3. Xử lý deadlock victim bằng cách rollback và retry toàn bộ transaction với giới hạn.
4. Theo dõi deadlock graph hoặc báo cáo deadlock để tìm thứ tự khóa xung đột thực tế.
5. Không retry vô hạn; dùng backoff có jitter để tránh các giao dịch va chạm lại cùng lúc.

Deadlock khác với việc số dư không đủ. Deadlock là xung đột điều phối tạm thời có thể retry; không đủ số dư là kết quả nghiệp vụ cần trả về, không nên retry lặp vô ích.

## 12. Idempotency: chống chuyển tiền hai lần khi client gửi lại

Một tình huống khó là server đã commit chuyển tiền nhưng response bị mất trên mạng. Client không biết giao dịch đã thành công hay chưa và gửi lại cùng yêu cầu. Nếu server tạo transfer mới, tài khoản nguồn có thể bị trừ hai lần.

Ứng dụng nên yêu cầu một **idempotency key** duy nhất cho mỗi ý định chuyển tiền. Khóa này phải được lưu bằng unique constraint trong cùng transaction với transfer và ledger.

Luồng xử lý:

```text
Client gửi transfer với idempotency_key = K
                 |
                 v
Server bắt đầu transaction
                 |
                 v
Thử tạo transfer request với K
                 |
       +---------+----------+
       |                    |
       v                    v
   K mới                K đã tồn tại
       |                    |
       v                    v
Khóa tài khoản        Đọc trạng thái transfer cũ
       |                    |
Trừ/cộng + ledger      Trả lại kết quả đã lưu
       |
COMMIT
```

Nếu một transaction khác đang xử lý cùng key, unique constraint sẽ điều phối cạnh tranh. Request thứ hai phải đợi kết quả của request đầu hoặc xử lý conflict theo transaction semantics. Khi key đã tồn tại, ứng dụng nên kiểm tra fingerprint của payload: cùng key nhưng khác tài khoản hoặc số tiền phải bị từ chối, không được trả kết quả của một yêu cầu khác.

Ví dụ PostgreSQL cho bước nhận diện:

```sql
INSERT INTO transfer (
    transfer_id, idempotency_key,
    from_account_id, to_account_id,
    amount, currency, status, created_at
)
VALUES (
    :transfer_id, :key,
    :from_id, :to_id,
    :amount, :currency, 'PENDING', CURRENT_TIMESTAMP
)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING transfer_id;
```

Nếu `RETURNING` có dòng, transaction này đã nhận quyền xử lý yêu cầu mới và có thể tiếp tục khóa tài khoản, cập nhật số dư, ghi ledger rồi chuyển trạng thái sang `COMPLETED`. Nếu không có dòng, đọc transfer đã lưu và so sánh payload. Không được tiếp tục trừ tiền lần nữa.

Việc tạo transfer, cập nhật account, ghi ledger và đánh dấu hoàn tất phải nằm trong cùng transaction. Nếu bước debit/credit thất bại và transaction rollback, bản ghi idempotency cũng rollback; một lần thử sau có thể xử lý lại đúng yêu cầu.

## 13. Ranh giới với dịch vụ bên ngoài và transactional outbox

Nếu chuyển tiền chỉ cập nhật các bảng trong cùng một database, một transaction database có thể bao trùm toàn bộ thay đổi. Nhưng nếu thao tác còn phải gọi ngân hàng đối tác, gửi email, phát message hoặc cập nhật hệ thống khác, không nên giữ transaction và khóa tài khoản trong suốt lời gọi mạng.

Lời gọi bên ngoài có thể chậm, timeout hoặc trả kết quả không rõ ràng. Một database transaction không thể tự rollback một khoản tiền mà ngân hàng đối tác đã nhận nếu không có giao thức bù trừ.

Với event nội bộ, có thể ghi outbox event trong cùng transaction:

```sql
BEGIN;

-- Khóa tài khoản, kiểm tra, ghi nợ và ghi có.
-- Ghi transfer và ledger entries.

INSERT INTO outbox_event (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :event_id, :transfer_id, 'TransferCompleted', :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
```

Worker riêng đọc outbox và phát event sau commit. Consumer cần idempotent vì message có thể được gửi lại. Nhờ vậy, dữ liệu chuyển tiền và ý định phát sự kiện được commit cùng nhau; không có trường hợp tiền đã chuyển nhưng event bị mất chỉ vì tiến trình chết giữa hai thao tác.

Với hệ thống thanh toán bên ngoài, cần state machine như `PENDING`, `SUBMITTED`, `CONFIRMED`, `FAILED`, cùng idempotency key phía đối tác, timeout/reconciliation và thao tác bù trừ nếu cần. Không nên giả vờ rằng một transaction SQL đơn lẻ có thể tạo atomic commit xuyên qua nhiều tổ chức hoặc hệ thống độc lập.

## 14. Xử lý lỗi và retry

Không phải mọi lỗi khi chuyển tiền đều được xử lý giống nhau:

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Không đủ số dư | Rollback và trả lỗi nghiệp vụ; không retry tự động |
| Tài khoản không hoạt động hoặc khác loại tiền | Rollback và trả lỗi nghiệp vụ |
| Unique conflict trên idempotency key | Đọc kết quả đã lưu, xác minh payload và trả lại kết quả cũ |
| Deadlock victim | Rollback và retry toàn bộ transaction có giới hạn |
| Serialization failure | Rollback và retry toàn bộ transaction nếu thao tác còn hợp lệ |
| Lock timeout | Tùy chính sách tải: retry có giới hạn hoặc trả lỗi tạm thời |
| Mất kết nối trước khi biết kết quả COMMIT | Kết quả có thể chưa rõ; truy vấn bằng idempotency key trước khi quyết định thử lại |
| Constraint violation do dữ liệu sai | Điều tra/ trả lỗi; không retry vô hạn |

Retry phải chạy lại từ đầu với transaction mới: nhận diện idempotency key, khóa lại các tài khoản, đọc trạng thái mới, kiểm tra số dư và tính toán lại. Không tiếp tục từ câu lệnh cuối cùng của transaction đã rollback vì các quyết định trước đó có thể đã lỗi thời.

Nếu client mất kết nối đúng lúc gửi `COMMIT`, không thể kết luận chỉ từ lỗi mạng rằng transaction đã rollback. Server có thể đã commit nhưng response không tới client. Idempotency key cho phép client hỏi lại kết quả của cùng một transfer mà không tạo khoản chuyển thứ hai.

## 15. Những tình huống biên cần xử lý

### 15.1. Chuyển từ tài khoản sang chính nó

Thông thường nên từ chối `source_account_id = destination_account_id`. Nếu cho phép, phải định nghĩa rõ đây là no-op, có tạo lịch sử hay không và có thu phí hay không. Không để hai câu update trừ/cộng cùng dòng làm logic khó hiểu.

### 15.2. Số tiền bằng 0 hoặc âm

Từ chối amount nhỏ hơn hoặc bằng 0. Nếu cho phép số tiền có phần thập phân, kiểm tra scale theo loại tiền và quy tắc làm tròn. Không dùng số dấu phẩy động cho số dư.

### 15.3. Hai tài khoản khác loại tiền

Không cộng trực tiếp số tiền 100 USD vào số dư VND. Cần exchange rate, thời điểm áp dụng, phí, quy tắc rounding và các bút toán cân bằng qua tài khoản FX/clearing. Tổng số dư chỉ có ý nghĩa khi xét theo từng currency hoặc quy đổi theo một chính sách định giá rõ ràng.

### 15.4. Tài khoản bị khóa giữa lúc kiểm tra

Trạng thái tài khoản phải được kiểm tra trong cùng transaction sau khi đã khóa dòng tài khoản. Nếu một thao tác quản trị có thể đổi trạng thái, nó cũng phải phối hợp qua cùng dòng khóa hoặc giao thức tương đương. Không kiểm tra status từ cache rồi dựa vào kết quả cũ để chuyển tiền.

### 15.5. Hạn mức ngày hoặc số lần chuyển

Nếu quy tắc là “tổng tiền chuyển trong ngày không vượt X”, khóa hai tài khoản có thể chưa đủ. Cần một resource đại diện cho hạn mức của tài khoản/ngày, cập nhật bộ đếm có điều kiện hoặc dùng cơ chế bảo vệ predicate/serializability phù hợp. Resource này cũng phải nằm trong thứ tự khóa toàn cục.

## 16. Cách kiểm tra thiết kế chuyển tiền

Khi review một luồng chuyển tiền, hãy lần theo toàn bộ đường đi:

1. Bất biến nào phải đúng sau commit: không âm, cân bằng ledger, cùng currency, giới hạn ngày?
2. Constraint nào bảo vệ từng bất biến ở cấp database?
3. Transaction bắt đầu trước bước đọc/kiểm tra nào và kết thúc sau bước ghi nào?
4. Tất cả tài khoản và resource liên quan có được khóa không?
5. Mọi luồng có khóa theo cùng thứ tự ổn định không?
6. Debit có điều kiện `balance >= amount` và kiểm tra row count không?
7. Credit, transfer record, ledger entries và outbox có cùng transaction không?
8. Có unique idempotency key và kiểm tra payload khi request gửi lại không?
9. Deadlock/serialization failure được retry toàn bộ transaction với giới hạn không?
10. Nếu kết quả COMMIT không rõ, ứng dụng truy vấn lại bằng idempotency key hay có nguy cơ chuyển lần hai?
11. Lời gọi dịch vụ ngoài có đang diễn ra trong lúc giữ khóa không?
12. Có metric và quy trình đối soát để phát hiện lệch số dư/ledger không?

Một thiết kế tốt không chỉ chạy đúng trong một request đơn lẻ. Nó phải duy trì bất biến khi hai hoặc nhiều giao dịch chuyển tiền chạy cùng lúc, khi một giao dịch bị rollback, khi deadlock xảy ra và khi client gửi lại yêu cầu sau timeout.

## 17. Tổng kết luồng an toàn

Chuyển tiền cùng loại tiền cần ghi nợ và ghi có bằng cùng một transaction. Các dòng tài khoản phải được khóa theo thứ tự ID ổn định để giảm deadlock; số dư nguồn phải được kiểm tra lại tại điểm ghi bằng điều kiện `balance >= amount`; transfer và ledger phải commit cùng thay đổi số dư. Unique idempotency key bảo vệ trường hợp request được gửi lại, còn outbox giúp phát sự kiện sau commit mà không giữ khóa trong lúc gọi dịch vụ bên ngoài.

Tổng số dư được bảo toàn bởi hai bút toán đối ứng, không phải bởi một phép `SUM` chạy trước giao dịch. Transaction bảo vệ ranh giới nguyên tử; thứ tự khóa điều phối các giao dịch cạnh tranh; constraint và ledger bảo vệ các bất biến có thể kiểm tra ở cấp dữ liệu. Khi ba phần này được thiết kế nhất quán, thao tác chuyển tiền có thể giữ đúng kết quả ngay cả khi nhiều giao dịch hoạt động đồng thời.
