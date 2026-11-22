# Phân tích ACID qua ví dụ chuyển tiền giữa hai tài khoản

## 1. Bài toán: chuyển 300 đơn vị tiền từ An sang Bình

Giả sử hệ thống ngân hàng thu nhỏ đang lưu số dư của hai tài khoản:

| Tài khoản | Chủ tài khoản | Số dư trước khi chuyển |
| --- | --- | ---: |
| 101 | An | 1.000 |
| 202 | Bình | 500 |
| **Tổng** | | **1.500** |

An muốn chuyển **300** đơn vị tiền sang tài khoản của Bình. Khi giao dịch thành công, kết quả phải là:

| Tài khoản | Số dư ban đầu | Thay đổi | Số dư sau khi chuyển |
| --- | ---: | ---: | ---: |
| An (101) | 1.000 | −300 | 700 |
| Bình (202) | 500 | +300 | 800 |
| **Tổng** | **1.500** | **0** | **1.500** |

Từ góc nhìn nghiệp vụ, đây là **một thao tác chuyển tiền**. Từ góc nhìn SQL, nó cần ít nhất **hai lần cập nhật dữ liệu**:

```sql
UPDATE accounts SET balance = balance - 300 WHERE account_id = 101;
UPDATE accounts SET balance = balance + 300 WHERE account_id = 202;
```

Nếu hai lệnh được thực hiện độc lập và hệ thống lỗi giữa chừng, tiền có thể bị trừ ở tài khoản An nhưng chưa được cộng cho Bình. Nếu hai yêu cầu chuyển tiền cùng chạy, cả hai có thể dựa vào số dư cũ để đưa ra quyết định sai. Nếu dữ liệu chỉ nằm trong bộ nhớ mà không được ghi bền vững, việc chuyển tiền đã báo thành công có thể biến mất sau sự cố.

Đó là lý do một hệ quản trị cơ sở dữ liệu giao dịch cần mô hình **ACID**:

- **A — Atomicity (Tính nguyên tử):** Hoặc toàn bộ thao tác chuyển tiền thành công, hoặc không thao tác nào được chấp nhận.
- **C — Consistency (Tính nhất quán):** Giao dịch hợp lệ đưa dữ liệu từ trạng thái thỏa quy tắc nghiệp vụ sang một trạng thái cũng thỏa các quy tắc đó.
- **I — Isolation (Tính cô lập):** Các giao dịch đồng thời được kiểm soát để tránh những tương tác gây sai lệch dữ liệu; mức bảo đảm cụ thể phụ thuộc *isolation level*.
- **D — Durability (Tính bền vững):** Khi hệ thống xác nhận `COMMIT` thành công, kết quả đã commit phải được giữ sau sự cố theo bảo đảm lưu trữ của hệ quản trị.

Bốn thuộc tính cùng bảo vệ một giao dịch, nhưng mỗi thuộc tính giải quyết **một loại vấn đề khác nhau**. Chúng ta sẽ dùng cùng ví dụ chuyển tiền để phân biệt rõ từng thuộc tính.

## 2. Mô hình dữ liệu và môi trường thực hành

Các lệnh dưới đây dùng **PostgreSQL 16** để minh họa. Người đọc có thể thực hành bằng một PostgreSQL đã cài đặt hoặc dùng Docker. Các ví dụ tập trung vào khái niệm ACID; cú pháp và cách khóa dữ liệu có thể khác ở MySQL, SQL Server, Oracle hoặc những hệ quản trị khác.

### 2.1. Tạo cơ sở dữ liệu bằng Docker (tùy chọn)

Nếu chưa có PostgreSQL, mở terminal trên máy có Docker đang chạy:

```powershell
docker run --name acid-transfer-lab -e POSTGRES_USER=lab_user -e POSTGRES_PASSWORD=lab_password -e POSTGRES_DB=acid_lab -p 127.0.0.1:55433:5432 -d postgres:16
```

Kiểm tra máy chủ đã sẵn sàng:

```powershell
docker exec acid-transfer-lab pg_isready -U lab_user -d acid_lab
```

Mở **Terminal A**:

```powershell
docker exec -it acid-transfer-lab psql -X -U lab_user -d acid_lab
```

Khi cần thử hai giao dịch đồng thời, mở thêm **Terminal B** và chạy lại lệnh kết nối tương tự. Hai cửa sổ phải là **hai kết nối PostgreSQL riêng**; có thể xác minh bằng cách chạy `SELECT pg_backend_pid();` trong mỗi cửa sổ rồi đối chiếu hai PID khác nhau.

Mật khẩu trên chỉ dành cho môi trường thực hành cục bộ, không dùng cho hệ thống thật. Nếu đã có PostgreSQL, chỉ cần dùng hai kết nối tới cùng một database, và bỏ qua các lệnh Docker.

### 2.2. Tạo bảng tài khoản và lịch sử chuyển tiền

Chạy SQL trong **một** cửa sổ `psql`:

```sql
-- Chỉ chạy trong database thực hành: các bảng cùng tên sẽ bị xóa.
DROP TABLE IF EXISTS transfer_log;
DROP TABLE IF EXISTS accounts;

CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

CREATE TABLE transfer_log (
    transfer_id TEXT PRIMARY KEY,
    from_account_id BIGINT NOT NULL REFERENCES accounts(account_id),
    to_account_id BIGINT NOT NULL REFERENCES accounts(account_id),
    amount BIGINT NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account_id <> to_account_id)
);

INSERT INTO accounts (account_id, owner_name, balance)
VALUES
    (101, 'An', 1000),
    (202, 'Binh', 500);

SELECT account_id, owner_name, balance
FROM accounts
ORDER BY account_id;
```

Ở đây, `balance` dùng `BIGINT` và lưu **đơn vị tiền nguyên** để tập trung vào giao dịch và tránh sai số dấu phẩy động. Trong ứng dụng thực tế, có thể dùng số nguyên theo đơn vị nhỏ nhất của tiền tệ hoặc kiểu `NUMERIC` với quy tắc làm tròn cụ thể.

Bảng `accounts` có ba ràng buộc đáng chú ý:

1. `PRIMARY KEY` bảo đảm mỗi tài khoản có một mã duy nhất.
2. `NOT NULL` ngăn số dư và chủ tài khoản bị bỏ trống.
3. `CHECK (balance >= 0)` ngăn cập nhật làm số dư âm.

Bảng `transfer_log` dùng `transfer_id` duy nhất để ghi nhận một yêu cầu chuyển tiền và hỗ trợ xử lý yêu cầu gửi lại. Đây là lịch sử giao dịch đơn giản phục vụ học tập, **chưa phải sổ cái kế toán đầy đủ**. Việc ghi lịch sử cũng cần nằm cùng giao dịch với việc trừ và cộng tiền.

> Các lệnh `DROP TABLE` trong ví dụ chỉ phù hợp với database thực hành. Không chạy chúng trên dữ liệu cần giữ.

## 3. Chuyển tiền trong một giao dịch: đường đi thành công

Nếu chỉ có hai lệnh `UPDATE` mà không dùng `BEGIN`, PostgreSQL trong chế độ autocommit thông thường sẽ commit **từng lệnh riêng lẻ**. Để gộp chúng thành một đơn vị công việc, dùng một giao dịch tường minh.

Trong phiên A, chạy lần lượt:

```sql
BEGIN;

-- Khóa trước cả hai tài khoản, theo cùng thứ tự account_id.
SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;

-- Trừ tiền; chỉ thực hiện khi số dư vẫn đủ.
UPDATE accounts
SET balance = balance - 300
WHERE account_id = 101
  AND balance >= 300
RETURNING account_id, balance;

-- Cộng đúng số tiền đã trừ vào tài khoản đích.
UPDATE accounts
SET balance = balance + 300
WHERE account_id = 202
RETURNING account_id, balance;

-- Ghi nhận yêu cầu chuyển tiền trong cùng giao dịch.
INSERT INTO transfer_log (
    transfer_id, from_account_id, to_account_id, amount
) VALUES (
    'transfer-demo-001', 101, 202, 300
);

COMMIT;
```

**Điều kiện bắt buộc để cho phép `COMMIT`:** Lệnh `SELECT ... FOR UPDATE` phải tìm thấy **đủ hai tài khoản**; cả hai lệnh `UPDATE ... RETURNING` phải tác động lên **đúng một hàng**; lệnh ghi lịch sử phải thành công. Nếu một trong các điều kiện không thỏa, ứng dụng phải chạy `ROLLBACK` thay vì `COMMIT`. Trong terminal thực hành, người học phải tự quan sát kết quả từng lệnh và quyết định; đoạn SQL trên minh họa **đường đi thành công**, chưa phải chương trình tự động kiểm tra và rẽ nhánh.

Sau khi commit thành công, kiểm tra:

```sql
SELECT account_id, balance
FROM accounts
ORDER BY account_id;

SELECT transfer_id, from_account_id, to_account_id, amount
FROM transfer_log;
```

Kết quả số dư dự kiến là `700` và `800`, tổng vẫn bằng `1500`; lịch sử có một bản ghi `transfer-demo-001`.

### 3.1. Vì sao khóa hai tài khoản?

`SELECT ... FOR UPDATE` yêu cầu PostgreSQL khóa những hàng được chọn. Khi giao dịch A chưa kết thúc, một giao dịch khác cố cập nhật chính những hàng đó sẽ phải chờ hoặc gặp lỗi timeout tùy cấu hình. Lấy khóa theo **thứ tự thống nhất** giúp giảm khả năng deadlock giữa các luồng chuyển tiền ngược chiều.

Khóa hàng là một cách tổ chức chuyển tiền đồng thời. Vẫn cần kiểm tra điều kiện `balance >= 300` ngay tại lệnh `UPDATE`, vì số dư có thể thay đổi giữa các lần yêu cầu hoặc vì một đường xử lý khác không tuân thủ quy trình khóa.

### 3.2. Ranh giới của giao dịch

```text
BEGIN
  |
  +-- Khóa tài khoản 101 và 202
  |
  +-- Trừ 300 ở tài khoản 101
  |
  +-- Cộng 300 ở tài khoản 202
  |
  +-- Ghi transfer_log
  |
  +-- Tất cả thành công?
          | Có  -> COMMIT    -> 700 / 800, có lịch sử
          | Không -> ROLLBACK -> 1000 / 500, không có lịch sử
```

Một giao dịch cơ sở dữ liệu có hiệu lực trong **phạm vi cơ sở dữ liệu và kết nối tham gia giao dịch đó**. Gửi email thông báo, gọi API sang ngân hàng khác hoặc ghi vào một dịch vụ độc lập không tự động được hoàn tác cùng `ROLLBACK`; những bước này cần thiết kế bổ sung.

## 4. A — Atomicity: hoặc trọn vẹn, hoặc không có gì

**Atomicity** xem việc trừ tiền, cộng tiền và ghi lịch sử là **một đơn vị không thể hoàn thành một phần**. DBMS phải bảo đảm rằng khi giao dịch bị hủy, những thay đổi của giao dịch không trở thành dữ liệu đã commit.

### 4.1. Thử tình huống lỗi sau khi đã trừ tiền

Đặt lại dữ liệu thử nghiệm bằng cách chạy trong một phiên, khi không có giao dịch nào khác đang mở:

```sql
TRUNCATE TABLE transfer_log;
UPDATE accounts SET balance = 1000 WHERE account_id = 101;
UPDATE accounts SET balance = 500  WHERE account_id = 202;
```

Sau đó thực hiện:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 300
WHERE account_id = 101
RETURNING account_id, balance;

-- Giả lập phát hiện lỗi trước khi cộng tiền:
ROLLBACK;

SELECT account_id, balance
FROM accounts
ORDER BY account_id;
```

Lệnh `UPDATE` trong giao dịch có thể trả về `700`. Điều này **không** đồng nghĩa khoản trừ đã được commit. Sau `ROLLBACK`, số dư lại là `1000` và `500`. Nếu giao dịch có thêm bản ghi `transfer_log` chưa commit, bản ghi ấy cũng bị hoàn tác.

Tình huống lỗi thực tế có thể là: tài khoản đích không tồn tại, ràng buộc bị vi phạm, chương trình hủy yêu cầu, phát sinh ngoại lệ hoặc một câu lệnh SQL thất bại. Trong PostgreSQL, khi câu lệnh gây lỗi trong một giao dịch tường minh, giao dịch thường vào trạng thái lỗi; cần `ROLLBACK` để thoát và loại bỏ các thay đổi chưa commit.

### 4.2. Nếu không có Atomicity sẽ ra sao?

Giả sử tài khoản ban đầu vẫn là `1000` và `500`:

| Bước | Trừ tiền ở An | Cộng tiền ở Bình | Kết quả |
| --- | --- | --- | --- |
| Trước chuyển tiền | Chưa | Chưa | 1000 / 500 |
| Lệnh trừ tiền đã commit riêng | Có | Chưa | 700 / 500 |
| Dịch vụ lỗi trước khi cộng tiền | Có | Không | **Tổng chỉ còn 1200** |
| Cả hai lệnh trong một giao dịch và `ROLLBACK` | Bị hoàn tác | Chưa chạy | **1000 / 500** |

Vấn đề không nằm ở việc mỗi câu lệnh `UPDATE` có hợp lệ hay không; từng câu lệnh đều có thể chạy đúng riêng lẻ. Atomicity bảo đảm **nhóm thao tác** được xử lý như một giao dịch duy nhất.

### 4.3. Atomicity không có nghĩa mọi câu lệnh tự phát hiện lỗi nghiệp vụ

Nếu lệnh trừ tiền không tác động hàng nào do tài khoản thiếu tiền, PostgreSQL không tự hiểu rằng toàn bộ yêu cầu chuyển tiền phải hủy. Ví dụ:

```sql
UPDATE accounts
SET balance = balance - 2000
WHERE account_id = 101
  AND balance >= 2000
RETURNING account_id, balance;
```

Kết quả là `UPDATE 0`, không nhất thiết là lỗi SQL. Nếu chương trình vẫn tiếp tục cộng `2000` vào tài khoản đích rồi `COMMIT`, chương trình đã tạo tiền mới dù các câu lệnh đều nằm trong một giao dịch. **Ứng dụng phải kiểm tra số hàng được cập nhật** và `ROLLBACK` nếu điều kiện chuyển tiền không đạt.

Đây là điểm nối giữa **Atomicity** và **Consistency**: DBMS có thể bảo đảm hoàn tác toàn bộ giao dịch, nhưng người viết chương trình phải xác định **khi nào giao dịch được phép commit**.

## 5. C — Consistency: bảo toàn quy tắc đúng của dữ liệu

**Consistency** nghĩa là mọi giao dịch **được chấp nhận** phải đưa cơ sở dữ liệu từ trạng thái hợp lệ ban đầu sang trạng thái hợp lệ mới, theo các ràng buộc cơ sở dữ liệu và quy tắc nghiệp vụ được thiết kế, kiểm tra và thực thi đúng.

Với ví dụ chuyển tiền nội bộ không có phí, có các bất biến (*invariants*):

```text
balance(101) >= 0
balance(202) >= 0
amount > 0
from_account_id != to_account_id
balance(101) + balance(202) = 1500
```

Bất biến cuối chỉ đúng cho hệ thống hai tài khoản đang xét, khi không có lệnh nạp tiền, rút tiền, phí hay giao dịch ngoài mô hình.

### 5.1. Ràng buộc do cơ sở dữ liệu thực thi

```sql
balance BIGINT NOT NULL CHECK (balance >= 0)
```

Ràng buộc `CHECK` bảo vệ **từng dòng tài khoản** khỏi số dư âm. Nếu cố trừ `2000` khỏi tài khoản có `1000` bằng lệnh không có điều kiện `balance >= 2000`, PostgreSQL từ chối lệnh vì vi phạm `CHECK`.

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 2000
WHERE account_id = 101;

-- PostgreSQL báo lỗi vi phạm CHECK; giao dịch bị lỗi.
ROLLBACK;
```

`PRIMARY KEY`, `FOREIGN KEY`, `NOT NULL`, `UNIQUE` và `CHECK` có thể ngăn nhiều trạng thái không hợp lệ. Tuy nhiên, một ràng buộc `CHECK` trên từng hàng **không tự bảo đảm** tổng số dư của hai tài khoản được bảo toàn.

### 5.2. Quy tắc nghiệp vụ do mã ứng dụng hoặc cơ chế phù hợp thực thi

Để bảo toàn tổng số dư trong ví dụ, chương trình phải trừ và cộng **cùng một lượng tiền**, chọn đúng tài khoản, kiểm tra cả hai tài khoản đều tồn tại, và chỉ commit khi tất cả các bước thành công.

| Quy tắc | Cách thực thi minh họa | Nếu thiếu |
| --- | --- | --- |
| Mỗi tài khoản tồn tại duy nhất | `PRIMARY KEY` | Có thể có mã tài khoản trùng |
| Số dư không âm | `CHECK (balance >= 0)` và điều kiện ở `UPDATE` | Có thể cho phép chi quá số dư |
| Số tiền chuyển dương | `CHECK (amount > 0)` và kiểm tra đầu vào | Yêu cầu `0` hoặc âm có thể lọt qua |
| Tài khoản nguồn, đích hợp lệ | `FOREIGN KEY`, kiểm tra `SELECT ... FOR UPDATE` và số hàng cập nhật | Có thể trừ tiền mà không cộng đúng đích |
| Tổng tiền nội bộ không đổi | Trừ và cộng bằng nhau trong **cùng giao dịch** | Có thể tự sinh hoặc làm mất tiền |
| Một yêu cầu không thực hiện hai lần | Khóa duy nhất `transfer_id` và xử lý gửi lại đúng cách | Yêu cầu retry có thể chuyển tiền hai lần |

Một giao dịch **vẫn có thể vi phạm nghiệp vụ** nếu ứng dụng viết sai logic nhưng không đụng ràng buộc nào. Vì vậy, Consistency là kết quả của **thiết kế dữ liệu + ràng buộc + logic giao dịch + kiểm soát đồng thời**, chứ không phải chỉ do có `BEGIN` và `COMMIT`.

### 5.3. Bất biến không phải một lần kiểm tra bên ngoài giao dịch

Giả sử chương trình đọc số dư `1000`, quyết định rằng đủ để chuyển `800`, rồi một lúc sau mới bắt đầu giao dịch trừ tiền. Trong khoảng trống giữa lúc kiểm tra và lúc cập nhật, giao dịch khác có thể đã trừ `300`. Dựa vào số dư cũ có thể dẫn đến quyết định sai.

Cần đặt quyết định dựa trên số dư đủ tiền **bên trong phạm vi đồng bộ hóa giao dịch**, ví dụ dùng `SELECT ... FOR UPDATE` và cập nhật có điều kiện:

```sql
UPDATE accounts
SET balance = balance - 800
WHERE account_id = 101
  AND balance >= 800
RETURNING balance;
```

Chương trình chỉ tiếp tục phần cộng tiền nếu lệnh trả về một hàng. Lệnh `UPDATE` kiểm tra điều kiện dựa trên trạng thái hàng được PostgreSQL xử lý cùng thao tác cập nhật, giúp tránh dựa vào một giá trị chỉ đọc ở bước trước.

## 6. I — Isolation: hai giao dịch chuyển tiền chạy cùng lúc

**Isolation** giải quyết câu hỏi: điều gì xảy ra nếu hai yêu cầu cùng truy cập những tài khoản đó tại cùng thời điểm?

Giả sử An hiện có `1000`:

- **Giao dịch A:** chuyển `300` từ An cho Bình.
- **Giao dịch B:** muốn chuyển thêm `800` từ An tới một tài khoản khác.

Nếu cả A và B đều độc lập đọc số dư ban đầu `1000` rồi cùng kết luận đủ tiền, cả hai yêu cầu có thể được chấp nhận dù tổng khoản trừ là `1100`. Hệ thống phải đồng bộ hóa việc kiểm tra và cập nhật, hoặc buộc một giao dịch thử lại, để quyết định dựa trên trạng thái hợp lệ.

### 6.1. Quan sát hai phiên với `SELECT ... FOR UPDATE`

Hãy đưa dữ liệu về `1000 / 500` như ở mục 4.1. Mở hai kết nối PostgreSQL riêng biệt. Trong ví dụ dưới đây, B chỉ **kiểm tra** khả năng trừ `800`; không cần tạo thêm tài khoản thứ ba.

| Thứ tự | Phiên A | Phiên B |
| ---: | --- | --- |
| 1 | `BEGIN;` | |
| 2 | `SELECT ... WHERE account_id IN (101, 202) ORDER BY account_id FOR UPDATE;` | |
| 3 | | `BEGIN;` |
| 4 | | `SELECT ... WHERE account_id = 101 FOR UPDATE;` → **chờ** |
| 5 | Trừ 300 ở An, cộng 300 cho Bình | Vẫn chờ khóa |
| 6 | `COMMIT;` | Được tiếp tục |
| 7 | | Nhìn thấy số dư mới `700` |
| 8 | | Muốn trừ 800 nhưng không đủ → `ROLLBACK;` |

Ở **phiên A**:

```sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (101, 202)
ORDER BY account_id
FOR UPDATE;
```

Giữ nguyên phiên A trong trạng thái chưa commit. Sau đó ở **phiên B**:

```sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;
```

Phiên B sẽ chờ hàng 101 đang do A khóa. Trở lại **phiên A**:

```sql
UPDATE accounts
SET balance = balance - 300
WHERE account_id = 101 AND balance >= 300;

UPDATE accounts
SET balance = balance + 300
WHERE account_id = 202;

COMMIT;
```

Lúc A commit, truy vấn đang chờ của B tiếp tục và trả về số dư `700` ở mức cô lập `READ COMMITTED` của PostgreSQL. B thử:

```sql
UPDATE accounts
SET balance = balance - 800
WHERE account_id = 101
  AND balance >= 800
RETURNING balance;

ROLLBACK;
```

Lệnh cập nhật tác động **0 hàng**, vì `700 < 800`. B từ chối yêu cầu chuyển tiền và rollback. Giao dịch A vẫn thành công; số dư sau cùng là `700 / 800`. Đó là hành vi cần có nếu không cho phép tài khoản âm.

### 6.2. Isolation không chỉ là “mọi thứ chạy lần lượt”

Trong thực tế, DBMS cố gắng cho nhiều giao dịch chạy **chồng lấn** để sử dụng tài nguyên hiệu quả. Một số thao tác được phép chạy song song; một số thao tác phải chờ khóa; một số giao dịch có thể gặp lỗi xung đột hoặc phải chạy lại.

**Isolation level** quy định mức hiện tượng đồng thời nào được cho phép hoặc ngăn chặn. Với PostgreSQL:

| Mức cô lập | Ý nghĩa quan trọng khi xét ví dụ chuyển tiền |
| --- | --- |
| `READ COMMITTED` | Mỗi câu lệnh nhận một ảnh chụp dữ liệu đã commit tại thời điểm câu lệnh bắt đầu; truy vấn sau trong cùng giao dịch có thể thấy commit mới từ phiên khác. |
| `REPEATABLE READ` | Dùng ảnh chụp nhất quán của giao dịch; tránh nhiều thay đổi quan sát được giữa các lần đọc nhưng có thể vẫn có bất thường không tương đương lịch chạy tuần tự. |
| `SERIALIZABLE` | Hướng tới kết quả tương đương một thứ tự chạy tuần tự hợp lệ; DBMS có thể hủy một giao dịch bằng lỗi serialization và ứng dụng cần retry toàn bộ giao dịch. |

PostgreSQL mặc định thường dùng `READ COMMITTED`. Có thể kiểm tra bằng:

```sql
SHOW default_transaction_isolation;
```

Để bắt đầu giao dịch ở mức cô lập cụ thể:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Thực hiện toàn bộ thao tác chuyển tiền.
COMMIT;
```

Ở `SERIALIZABLE`, chương trình phải có chiến lược thử lại **toàn bộ giao dịch** khi gặp lỗi serialization (SQLSTATE `40001`). Các cơ chế và hiện tượng ở mức cô lập khác nhau không thể suy ra đơn giản chỉ từ tên ACID.

### 6.3. Ba vấn đề đồng thời dễ nhầm lẫn

**Dirty read (đọc dữ liệu chưa commit):** Nếu B đọc được số dư `700` do A trừ `300` nhưng A sau đó rollback, B đã dựa vào dữ liệu chưa từng trở thành trạng thái chính thức. Truy vấn `SELECT` thông thường trong PostgreSQL `READ COMMITTED` không đọc thay đổi chưa commit của A.

**Lost update (mất cập nhật):** Hai chương trình cùng đọc số dư ban đầu rồi ghi lại số dư được tính sẵn; một kết quả ghi có thể đè lên thay đổi của chương trình khác. Ví dụ cả hai đọc `1000`; A tính `700`, B tính `200`, rồi cả hai dùng `UPDATE accounts SET balance = <giá trị đã tính>`. Nếu không kiểm soát đồng thời, số dư cuối có thể phản ánh một phép trừ và bỏ sót phép trừ còn lại. Tránh thiết kế dựa vào giá trị cũ; dùng phép cập nhật nguyên tử có điều kiện, khóa hoặc cơ chế phiên bản phù hợp.

**Write skew (lệch ghi):** Hai giao dịch đọc chung một điều kiện liên quan tới nhiều hàng, sau đó cập nhật **những hàng khác nhau**; từng cập nhật riêng có thể hợp lệ, nhưng điều kiện tổng thể bị phá vỡ. Ví dụ tổng số dư tối thiểu hoặc quy tắc luôn phải có ít nhất một tài khoản đủ dự phòng. Khóa đúng tập dữ liệu, dùng ràng buộc phù hợp hoặc `SERIALIZABLE` có retry để bảo vệ bất biến liên hàng, tùy bài toán.

Một giao dịch có tính Atomicity không nhất thiết đủ Isolation. **Trừ và cộng tiền đồng thời thành một khối** vẫn chưa bảo đảm quyết định “có đủ tiền hay không” chính xác nếu mọi giao dịch cùng dùng các lần đọc cũ.

## 7. D — Durability: `COMMIT` thành công rồi máy chủ gặp sự cố

Giả sử A chuyển `300` và nhận được phản hồi `COMMIT` thành công. Ngay sau đó, tiến trình ứng dụng kết thúc, kết nối mạng mất hoặc máy chủ cơ sở dữ liệu phải khởi động lại.

**Durability** yêu cầu trạng thái giao dịch đã commit vẫn tồn tại sau sự cố theo bảo đảm của hệ quản trị: An có `700`, Bình có `800`, lịch sử `transfer-demo-001` còn tồn tại. Một giao dịch chỉ thay đổi bộ nhớ tạm mà mất sau khởi động lại không đáp ứng kỳ vọng này.

### 7.1. PostgreSQL thực hiện độ bền bằng cách nào?

PostgreSQL sử dụng **Write-Ahead Logging (WAL)**. Nói đơn giản, thông tin cần cho khôi phục giao dịch được ghi vào nhật ký bền vững theo quy tắc ghi log trước các trang dữ liệu tương ứng. Sau một lần tắt đột ngột, PostgreSQL có thể phát lại thông tin WAL để khôi phục các thay đổi đã commit và xử lý những giao dịch dang dở.

Với cấu hình thông thường có `fsync = on` và `synchronous_commit = on`, máy chủ chờ đủ điều kiện ghi WAL bền vững trước khi xác nhận commit. Tuy nhiên, mức bảo đảm thực tế phụ thuộc cấu hình PostgreSQL, thiết bị lưu trữ, hệ điều hành và kiến trúc triển khai.

Có thể quan sát cấu hình:

```sql
SHOW fsync;
SHOW synchronous_commit;
```

Nếu tùy chỉnh để ưu tiên hiệu năng, chẳng hạn thay đổi chính sách đồng bộ ghi, khoảng thời gian có nguy cơ mất một số giao dịch đã được phản hồi có thể khác. Vì thế, không thể dùng một câu khẳng định tuyệt đối về bền vững mà bỏ qua cấu hình.

### 7.2. Quan sát sau khi khởi động lại

Nếu đang dùng container `acid-transfer-lab` và đã **commit** thành công:

1. Thoát các cửa sổ `psql` bằng `\q`.
2. Trong terminal hệ điều hành, chạy `docker restart acid-transfer-lab`.
3. Kết nối lại bằng `docker exec -it acid-transfer-lab psql -X -U lab_user -d acid_lab`.
4. Chạy truy vấn:

```sql
SELECT account_id, balance
FROM accounts
ORDER BY account_id;

SELECT transfer_id, amount
FROM transfer_log
ORDER BY created_at;
```

Nếu trước đó thực hiện giao dịch `transfer-demo-001` thành công và chưa đặt lại dữ liệu, bạn sẽ thấy `700 / 800` cùng lịch sử chuyển tiền. Đây là minh họa thực hành về **dữ liệu đã commit còn tồn tại sau khi khởi động lại tiến trình/container**; nó không phải phép kiểm chứng đầy đủ đối với mọi loại mất điện hoặc hỏng thiết bị lưu trữ.

**Lưu ý:** `docker restart` giữ lại filesystem của container hiện có. Ngược lại, xóa container không có cơ chế lưu trữ bền vững được cấu hình phù hợp có thể làm mất dữ liệu. Durability của một giao dịch không đồng nghĩa với việc dữ liệu tự tồn tại mãi mãi sau khi người vận hành chủ động xóa nơi lưu trữ, và cũng không thay thế sao lưu, nhân bản dữ liệu hay kế hoạch khôi phục thảm họa.

### 7.3. Chưa commit thì không được coi là bền vững

Nếu A đã trừ tiền nhưng chưa commit, rồi phiên A bị ngắt hoặc tiến trình PostgreSQL kết thúc, cơ sở dữ liệu phải xử lý giao dịch chưa hoàn tất như một giao dịch không được chấp nhận. Sau khi khôi phục, những thay đổi chưa commit **không được xuất hiện như một lần chuyển tiền thành công**.

Vì vậy:

- **Atomicity** xử lý việc giao dịch hoàn tất toàn bộ hay bị hoàn tác.
- **Durability** xử lý việc trạng thái *đã commit thành công* được lưu giữ sau sự cố.

Hai thuộc tính bổ sung cho nhau trong quá trình phục hồi.

## 8. Xem cùng một sự cố qua bốn thuộc tính ACID

Cùng một yêu cầu chuyển `300` có thể được kiểm tra từ bốn góc độ khác nhau:

| Sự cố hoặc tình huống | Thuộc tính liên quan | Điều kiện kết quả đúng |
| --- | --- | --- |
| Đã trừ ở An, nhưng lỗi trước khi cộng ở Bình | **Atomicity** | Rollback cả giao dịch, trả về `1000 / 500` |
| Chuyển quá số dư hoặc cộng không đúng số tiền đã trừ | **Consistency** | Không commit giao dịch vi phạm ràng buộc và bất biến nghiệp vụ |
| Hai yêu cầu cùng muốn trừ tiền của An | **Isolation** | Kiểm tra, cập nhật được đồng bộ; một yêu cầu có thể chờ, thất bại hoặc retry |
| Giao dịch đã commit, máy chủ khởi động lại | **Durability** | Giữ dữ liệu `700 / 800` và bản ghi chuyển tiền theo bảo đảm lưu trữ |
| Gửi lại cùng yêu cầu sau khi mạng rớt lúc nhận phản hồi | **Idempotency ở mức ứng dụng** | Không chuyển tiền hai lần; nhận diện yêu cầu bằng khóa duy nhất và kiểm tra kết quả trước đó |

Hàng cuối là một mở rộng quan trọng: ACID **không tự bảo đảm** yêu cầu từ phía khách hàng chỉ được xử lý đúng một lần khi mạng không đáng tin cậy. Nếu `COMMIT` thực sự thành công nhưng phản hồi tới ứng dụng bị mất, ứng dụng có thể không biết kết quả và gửi lại yêu cầu.

## 9. Từ ACID tới chuyển tiền an toàn khi ứng dụng phải retry

Giả sử ứng dụng gửi lệnh chuyển tiền với mã `transfer_id = 'transfer-demo-001'`. Sau khi gửi `COMMIT`, kết nối bị mất trước khi ứng dụng nhận thông báo thành công. Có hai khả năng:

1. Giao dịch đã commit: tiền đã chuyển, lịch sử đã ghi.
2. Giao dịch chưa commit thành công: tiền chưa chuyển.

Ứng dụng không nên mặc định gửi lại toàn bộ thao tác với **mã mới**, vì có thể chuyển tiền hai lần. Thay vào đó, nên dùng một **mã yêu cầu ổn định** và kiểm tra trạng thái của mã đó:

```sql
SELECT transfer_id, from_account_id, to_account_id, amount
FROM transfer_log
WHERE transfer_id = 'transfer-demo-001';
```

Nếu bản ghi tồn tại và khớp nội dung yêu cầu, đó là bằng chứng cho giao dịch đã commit trong mô hình thực hành này, do lịch sử được ghi **cùng giao dịch** với thay đổi số dư. Nếu không tìm thấy, ứng dụng có thể đánh giá lại điều kiện và thử thực hiện yêu cầu với **cùng mã định danh**; khóa duy nhất trên `transfer_id` sẽ khiến hai lần thử trùng mã không thể cùng commit hai bản ghi lịch sử.

Cần xử lý cả trường hợp mã đã tồn tại nhưng thông số tài khoản hoặc số tiền **khác** với yêu cầu hiện tại; không được coi đó là một lần retry hợp lệ. Trong hệ thống thực, ứng dụng có thể dùng thêm trạng thái yêu cầu, mã lỗi, giới hạn retry và bảo vệ trước race condition. Một khóa duy nhất chỉ là **mảnh ghép** của cơ chế idempotency.

### 9.1. Mẫu luồng nghiệp vụ ở tầng ứng dụng

```text
Nhận yêu cầu transferId, from, to, amount
      |
      v
Xác thực đầu vào (amount > 0, from != to, ...)
      |
      v
Kiểm tra transferId đã có kết quả commit chưa
      |
      +-- Có và khớp dữ liệu --> Trả lại kết quả cũ
      |
      +-- Có nhưng khác dữ liệu --> Từ chối trùng mã
      |
      v
BEGIN TRANSACTION
      |
      v
Khóa các tài khoản cần thiết theo thứ tự cố định
      |
      v
Kiểm tra hai tài khoản tồn tại và nguồn đủ tiền
      |
      +-- Không đạt --> ROLLBACK, trả lỗi nghiệp vụ
      |
      v
Trừ nguồn; cộng đích; ghi transferId
      |
      +-- Bất kỳ bước nào lỗi --> ROLLBACK
      |
      v
COMMIT
      |
      v
Trả kết quả cho người gọi
```

Kiểm tra mã trước giao dịch giúp giảm công việc thừa nhưng **không đủ để chặn đua tranh** giữa hai yêu cầu đồng thời. Khóa duy nhất `transfer_id` ở thời điểm ghi lịch sử và một giao dịch bao trùm tất cả thay đổi mới là điểm bảo vệ cuối cùng trong ví dụ này. Nếu nhận lỗi do mã trùng, ứng dụng cần rollback, truy vấn lại kết quả đã commit và so sánh nội dung trước khi phản hồi.

### 9.2. Một giao dịch ACID có thể bao trùm những gì?

Ví dụ trên đặt cả hai số dư và lịch sử trong **cùng một PostgreSQL database**, nên một giao dịch cục bộ có thể bao trùm mọi thao tác.

Nếu tiền rời khỏi cơ sở dữ liệu này để sang **cơ sở dữ liệu khác hoặc dịch vụ khác**, không thể mặc định rằng `COMMIT` ở PostgreSQL sẽ tự động commit hoặc rollback ở bên kia. Hệ thống có thể phải dùng giao dịch phân tán, Saga, outbox, cơ chế bù trừ và xử lý idempotency theo kiến trúc. ACID của một giao dịch cục bộ là nền tảng quan trọng, nhưng không tự giải quyết việc phối hợp nhiều hệ thống.

## 10. Bài thực hành tự suy luận

Dùng trạng thái ban đầu `An = 1000`, `Bình = 500`; giả sử không có khoản phí hoặc hoạt động khác. Hãy dự đoán kết quả trước khi xem giải thích.

### Tình huống A: trừ tiền rồi rollback

```sql
BEGIN;
UPDATE accounts SET balance = balance - 300 WHERE account_id = 101;
ROLLBACK;
```

**Kết quả:** An vẫn có `1000`; Bình vẫn có `500`. Thuộc tính thể hiện trực tiếp là **Atomicity**, vì các thay đổi của giao dịch bị hủy.

### Tình huống B: trừ 300, cộng 250 rồi commit

```sql
BEGIN;
UPDATE accounts SET balance = balance - 300 WHERE account_id = 101;
UPDATE accounts SET balance = balance + 250 WHERE account_id = 202;
COMMIT;
```

**Kết quả nếu không có ràng buộc hoặc kiểm tra bổ sung:** An có `700`, Bình có `750`, tổng bằng `1450`. Hai hàng đều có số dư không âm nên các ràng buộc `CHECK` hiện tại không chặn lỗi này. **Consistency ở mức nghiệp vụ bị vi phạm** dù giao dịch được commit nguyên tử. Muốn ngăn, chương trình phải bảo đảm số tiền trừ và cộng bằng nhau, hoặc sử dụng thiết kế sổ cái/ràng buộc liên quan phù hợp.

### Tình huống C: A và B cùng trừ dựa trên số dư cũ

Hai phiên đều thấy An có `1000`. A muốn trừ `300`; B muốn trừ `800`. Nếu ứng dụng tự tính số dư mới bằng dữ liệu đọc từ trước và ghi đè bằng giá trị tuyệt đối, có thể xảy ra mất cập nhật hoặc quyết định chi quá số dư. Cần **Isolation** và quy trình kiểm tra/cập nhật đồng bộ: khóa tài khoản, dùng `UPDATE ... WHERE balance >= amount` hoặc các kỹ thuật phù hợp với mức cô lập đang dùng.

### Tình huống D: báo commit thành công, sau đó máy chủ restart

Giao dịch đã trừ `300`, cộng `300` và ghi lịch sử, rồi `COMMIT` thành công. Khi máy chủ khởi động lại, dữ liệu đã commit phải còn tồn tại theo bảo đảm **Durability** của cơ sở dữ liệu và cấu hình lưu trữ. Bản sao lưu và chính sách lưu giữ vẫn cần thiết để xử lý xóa dữ liệu hoặc hỏng thiết bị.

### Tình huống E: khách hàng gửi lại đúng yêu cầu sau lỗi mạng

Đừng tạo một giao dịch chuyển tiền mới chỉ vì không nhận được phản hồi lần trước. Kiểm tra `transfer_id` gốc, xác định kết quả đã commit và dùng **idempotency** để tránh lặp thao tác. Đây là yêu cầu triển khai hệ thống đáng tin cậy nằm bên cạnh ACID.

## 11. Thu dọn và đặt lại dữ liệu

Sau các phép thử, đảm bảo mọi cửa sổ `psql` đã `COMMIT` hoặc `ROLLBACK` giao dịch còn mở. Để đưa ví dụ về trạng thái ban đầu, dùng một phiên:

```sql
BEGIN;

DELETE FROM transfer_log;

UPDATE accounts SET balance = 1000 WHERE account_id = 101;
UPDATE accounts SET balance = 500  WHERE account_id = 202;

COMMIT;

SELECT account_id, balance FROM accounts ORDER BY account_id;
```

Đừng chạy lệnh đặt lại khi phiên khác đang giữ khóa hàng nếu không muốn lệnh chờ. Đối với kết nối `psql`, `\q` dùng để thoát. Nếu đã tạo container riêng để học và không cần giữ dữ liệu, dừng và xóa container bằng:

```powershell
docker stop acid-transfer-lab
docker rm acid-transfer-lab
```

Việc xóa container thực hành có thể xóa luôn dữ liệu trong đó; không dùng trên container phục vụ công việc thật.

## 12. Cách ghi nhớ ACID bằng một câu chuyện chuyển tiền

Một yêu cầu chuyển `300` từ An sang Bình chỉ được xem là hoàn tất khi cả phần trừ, phần cộng và bản ghi lịch sử được chấp nhận như **một giao dịch** (**Atomicity**); số dư và quy tắc bảo toàn tiền vẫn đúng (**Consistency**); những yêu cầu đến cùng lúc không dựa sai vào trạng thái cũ hoặc tạo xung đột không được xử lý (**Isolation**); và khi `COMMIT` đã được xác nhận thì kết quả không biến mất chỉ vì kết nối hay máy chủ khởi động lại (**Durability**).

Vì vậy, khi phân tích một lỗi chuyển tiền, hãy xác định **ranh giới giao dịch**, **bất biến nghiệp vụ**, **các giao dịch chạy chồng lấn** và **điểm xác nhận commit**. Bốn câu hỏi ấy giúp phân biệt lỗi thuộc về logic nghiệp vụ, kiểm soát đồng thời, xử lý ngoại lệ hay độ bền lưu trữ, thay vì chỉ nhìn vào một câu lệnh SQL đơn lẻ.
