# ACID, tính toàn vẹn và trách nhiệm của ứng dụng trong PostgreSQL

Khi một ứng dụng ghi dữ liệu, mục tiêu không chỉ là “câu SQL chạy không lỗi”. Một thao tác nghiệp vụ có thể gồm nhiều câu lệnh, nhiều điều kiện và nhiều hệ thống. Ví dụ chuyển tiền giữa hai tài khoản cần trừ tiền bên gửi, cộng tiền bên nhận và lưu lịch sử. Nếu hệ thống dừng giữa chừng, hai tài khoản không được ở trạng thái “đã trừ nhưng chưa cộng”. Nếu hai người cùng chi tiêu từ một số dư, tổng tiền không được âm. Nếu client mất kết nối sau khi gửi yêu cầu, hệ thống cần biết lần chuyển tiền trước đã hoàn tất hay chưa trước khi thử lại.

PostgreSQL giúp giải quyết một phần lớn các vấn đề trên bằng **giao dịch (transaction)**, **cơ chế ACID**, **ràng buộc toàn vẹn (constraints)**, **kiểm soát truy cập đồng thời** và **nhật ký phục hồi WAL**. Tuy nhiên, cơ sở dữ liệu không thể tự suy ra mọi quy tắc nghiệp vụ. Ứng dụng vẫn phải quyết định điều gì hợp lệ, tổ chức ranh giới giao dịch, xử lý lỗi, chống xử lý lặp và phối hợp các hệ thống bên ngoài database.

Bài học giải thích rõ **PostgreSQL bảo đảm điều gì**, **điều kiện để bảo đảm có ý nghĩa**, và **trách nhiệm nào vẫn thuộc về ứng dụng**.

Sau khi học, bạn có thể:

- Diễn giải đúng bốn thuộc tính ACID: Atomicity, Consistency, Isolation, Durability.
- Phân biệt transaction, câu lệnh SQL đơn lẻ, constraint, MVCC và write-ahead log.
- Sử dụng `BEGIN`, `COMMIT`, `ROLLBACK` và `SAVEPOINT` trong PostgreSQL.
- Tạo ràng buộc `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL` và `CHECK` để bảo vệ dữ liệu.
- Hiểu ảnh hưởng của `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` khi nhiều transaction chạy đồng thời.
- Thiết kế thao tác chuyển tiền có điều kiện số dư và khóa chống gửi lại yêu cầu.
- Xử lý các tình huống thất bại, retry, deadlock, lỗi serialization và tác động ngoài database.

Các ví dụ sử dụng cú pháp PostgreSQL phổ biến. Chỉ chạy thao tác tạo hoặc xóa bảng trên **database thử nghiệm riêng**.

---

## 1. Vì sao một thao tác nghiệp vụ cần nhiều bảo đảm?

Xét thao tác chuyển 250.000 đồng từ tài khoản A sang B. Giả sử hệ thống lưu tiền theo **đơn vị đồng** dưới dạng số nguyên (không dùng số thực nhị phân để biểu diễn tiền).

Trước khi chuyển:

| Tài khoản | Số dư |
| --- | ---: |
| A | 1.000.000 |
| B | 300.000 |
| **Tổng** | **1.300.000** |

Sau khi chuyển hợp lệ:

| Tài khoản | Số dư |
| --- | ---: |
| A | 750.000 |
| B | 550.000 |
| **Tổng** | **1.300.000** |

Ở đây tồn tại ít nhất bốn yêu cầu khác nhau:

1. **Không được chuyển một nửa:** trừ A và cộng B phải cùng thành công hoặc cùng bị hủy.
2. **Số dư hợp lệ:** A phải có đủ tiền; số dư không được âm.
3. **Nhiều yêu cầu cùng lúc:** hai transaction đồng thời không được ghi đè hoặc cùng chi tiêu vượt số dư.
4. **Sự cố:** khi PostgreSQL thông báo commit thành công theo chính sách độ bền đã cấu hình, dữ liệu cần được phục hồi phù hợp sau crash.

Cần thêm các yêu cầu do **ứng dụng** định nghĩa, chẳng hạn tài khoản đã xác minh, hạn mức ngày, phòng chống gian lận, quyền sở hữu tài khoản, yêu cầu không trùng lặp và gửi thông báo thành công đúng một cách hợp lý.

Có thể hình dung trách nhiệm:

```text
Yêu cầu từ client
        |
        v
Ứng dụng: xác thực, phân quyền, kiểm tra nghiệp vụ
        |
        v
PostgreSQL transaction
  +--------------------------------------+
  | Kiểm tra điều kiện và ràng buộc       |
  | Ghi các hàng liên quan                |
  | Phối hợp truy cập đồng thời           |
  | Commit hoặc rollback                 |
  +--------------------------------------+
        |
        v
Ứng dụng: xác nhận kết quả, retry khi thích hợp,
          quản lý idempotency và tác động bên ngoài
```

Không nên gọi cả hệ thống “ACID tuyệt đối” chỉ vì các bảng dùng PostgreSQL. ACID chủ yếu mô tả **giao dịch được database thực thi**, không tự mở rộng tới email, HTTP API, hàng đợi hoặc thao tác trên hệ thống khác.

## 2. Transaction là đơn vị nền tảng

Một transaction gom nhiều thao tác database thành một đơn vị logic. Trong PostgreSQL, có thể mở transaction tường minh:

```sql
BEGIN;

UPDATE some_table
SET some_value = 'new value'
WHERE id = 1;

INSERT INTO audit_log(entity_id, action_name)
VALUES (1, 'updated');

COMMIT;
```

Đây là **mẫu cú pháp minh họa**, chưa có bảng `some_table` và `audit_log` trong phần lab.

Các lệnh cơ bản:

| Lệnh | Vai trò |
| --- | --- |
| `BEGIN` | Bắt đầu transaction tường minh |
| `COMMIT` | Yêu cầu xác nhận transaction thành công |
| `ROLLBACK` | Hủy các thay đổi thuộc transaction chưa commit |
| `SAVEPOINT name` | Đánh dấu vị trí trong transaction |
| `ROLLBACK TO SAVEPOINT name` | Quay lại vị trí đánh dấu, không hủy toàn bộ transaction |
| `RELEASE SAVEPOINT name` | Giải phóng savepoint và giữ thay đổi đang có trong transaction |

Nếu không mở transaction tường minh, PostgreSQL thường xử lý **mỗi câu lệnh SQL thành công như một transaction riêng** trong chế độ autocommit của client. Điều đó không phù hợp nếu hai câu lệnh phải cùng thành công như một thao tác nghiệp vụ.

Ví dụ dễ mắc lỗi:

```sql
-- Hai câu lệnh độc lập khi client đang autocommit:
UPDATE accounts SET balance_cents = balance_cents - 25000
WHERE account_id = 1;

UPDATE accounts SET balance_cents = balance_cents + 25000
WHERE account_id = 2;
```

Nếu câu lệnh thứ nhất đã commit, còn câu thứ hai thất bại, PostgreSQL **không tự quay ngược một transaction đã commit trước đó**. Muốn chuyển tiền như một đơn vị, phải đặt các bước trong cùng một transaction và xử lý đúng kết quả của từng bước.

### 2.1. Lỗi trong transaction PostgreSQL

Khi một câu SQL thất bại trong transaction, PostgreSQL thường đánh dấu transaction hiện tại là **aborted**. Các câu SQL tiếp theo sẽ bị từ chối cho tới khi `ROLLBACK` hoặc quay về một savepoint thích hợp.

Thông báo phổ biến:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
```

Điều này khác với ý tưởng “cứ tiếp tục chạy lệnh kế tiếp và bỏ qua lệnh lỗi”. Ứng dụng cần có khối xử lý exception, rollback và không giữ connection trong trạng thái giao dịch thất bại khi trả lại connection pool.

### 2.2. Không phải mọi tác dụng đều rollback được

PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL như `CREATE TABLE` và `ALTER TABLE`, nhưng **không phải mọi câu lệnh tiện ích đều có thể chạy trong transaction block**; chẳng hạn `CREATE DATABASE` và `VACUUM` có quy tắc riêng.

Ngoài ra:

- Giá trị lấy từ sequence bằng `nextval()` **không được hoàn nguyên** khi transaction rollback; ID có thể có khoảng trống.
- Một email đã gửi, file đã ghi hoặc yêu cầu HTTP đã gửi **không tự được PostgreSQL rollback**.
- Những tác động đã commit ở một database khác hoặc dịch vụ khác không tự tham gia transaction hiện tại.

Vì vậy “Atomicity” phải được hiểu đúng phạm vi.

---

## 3. A — Atomicity: hoặc tất cả, hoặc không có thay đổi nào được commit

**Atomicity (tính nguyên tử)** yêu cầu các thay đổi thuộc một transaction có kết quả commit hoặc abort như một đơn vị.

Ví dụ:

```text
BEGIN
  |
  +-- Trừ số dư tài khoản A
  |
  +-- Cộng số dư tài khoản B
  |
  +-- Ghi lịch sử giao dịch
  |
  +-- COMMIT thành công ----> các thay đổi cùng được xác nhận
  |
  +-- ROLLBACK / lỗi -------> các thay đổi của transaction bị hủy
```

Transaction giúp ngăn dữ liệu được commit ở trạng thái chỉ thực hiện một nửa các bước **khi mọi bước đều ở cùng transaction của PostgreSQL**.

Atomicity **không tự phát hiện lỗi nghiệp vụ**. Ví dụ `UPDATE ... WHERE account_id = 9999` ảnh hưởng 0 hàng nhưng không phải lỗi SQL. Nếu ứng dụng không kiểm tra số hàng cập nhật, nó có thể vẫn commit bước còn lại. Khi đó transaction vẫn atomic theo các thao tác thực sự xảy ra, nhưng nghiệp vụ sai.

Điểm quan trọng:

> **Ứng dụng phải biết thế nào là “thành công”.** Một câu SQL chạy không báo lỗi không đồng nghĩa giao dịch nghiệp vụ đã hợp lệ.

### 3.1. `SAVEPOINT` không phải commit một phần

Savepoint cho phép hoàn tác một phần công việc trong transaction:

```sql
BEGIN;

SAVEPOINT before_optional_action;

-- Minh họa câu lệnh có thể cần hủy:
-- INSERT INTO ...

ROLLBACK TO SAVEPOINT before_optional_action;

-- Các thay đổi trước savepoint vẫn nằm trong transaction.
COMMIT;
```

Rollback tới savepoint không tạo một transaction độc lập bền vững. Những thay đổi còn lại vẫn phụ thuộc `COMMIT` cuối cùng.

---

## 4. C — Consistency: trạng thái dữ liệu phải hợp lệ theo những quy tắc đã khai báo

**Consistency (tính nhất quán)** trong ACID là việc transaction đưa database từ một trạng thái thỏa các bất biến đã được thiết lập sang trạng thái tiếp tục thỏa các bất biến đó, với điều kiện quy tắc được mô hình hóa và giao dịch được viết đúng.

PostgreSQL có nhiều công cụ ràng buộc:

| Ràng buộc | Bảo vệ điều gì? | Ví dụ |
| --- | --- | --- |
| `PRIMARY KEY` | Mỗi hàng có khóa định danh duy nhất và không `NULL` | `account_id` |
| `UNIQUE` | Các giá trị hoặc tổ hợp giá trị không được trùng theo quy tắc unique | `request_key` của yêu cầu chuyển tiền |
| `NOT NULL` | Một cột luôn có giá trị không `NULL` | `balance_cents` |
| `CHECK` | Một biểu thức kiểm tra giá trị mỗi hàng | `balance_cents >= 0` |
| `FOREIGN KEY` | Giá trị tham chiếu phải tương thích với bảng được tham chiếu | `from_account_id` tham chiếu `accounts` |
| `EXCLUDE` | Ngăn các cặp hàng có quan hệ xung đột được biểu diễn bởi toán tử thích hợp | Ngăn trùng lịch/khung giờ đặt chỗ khi thiết kế đúng |

Một số quy tắc có thể bảo đảm bằng **constraint trong database**, số khác phải được ứng dụng hoặc logic transaction thực thi.

### 4.1. Một `CHECK` không tự hiểu toàn bộ nghiệp vụ

Ví dụ:

```sql
balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
```

Constraint bảo vệ số dư không âm của **từng hàng**. Nó không tự bảo đảm tổng tiền chuyển giữa hai tài khoản được giữ nguyên. Tổng bất biến đó cần thao tác trừ/cộng có kiểm tra trong một transaction.

Cũng cần nhớ `CHECK` trong PostgreSQL được coi là thỏa khi biểu thức là **TRUE hoặc NULL**. Nếu một cột có thể `NULL`, điều kiện như `CHECK (amount > 0)` không tự loại `NULL`; cần `NOT NULL` nếu nghiệp vụ yêu cầu phải có giá trị.

### 4.2. Không dùng chỉ kiểm tra ở ứng dụng thay cho constraint

Một ứng dụng có thể kiểm tra trước khi insert:

```text
SELECT có request_key = 'abc' chưa?
Nếu chưa: INSERT ...
```

Nhưng hai request đồng thời có thể cùng nhìn thấy “chưa tồn tại” rồi cùng cố insert. Nếu database có `UNIQUE(request_key)`, PostgreSQL sẽ kiểm soát cạnh tranh để không commit hai hàng trùng khóa.

Nguyên tắc:

- **Database constraint** là lớp phòng thủ cuối cho quy tắc dữ liệu có thể diễn đạt ở cấp database.
- **Ứng dụng** kiểm tra sớm để cung cấp thông báo dễ hiểu và xây dựng luồng nghiệp vụ.
- Hai lớp **bổ sung cho nhau**, không nên bỏ constraint chỉ vì API đã validate.

### 4.3. Không phải mọi consistency đều tự có

PostgreSQL không biết các quy định như “khách VIP được miễn phí”, “một người chỉ được hoàn tiền ba lần một ngày” hay “yêu cầu chuyển tiền phải được chủ tài khoản xác nhận” nếu bạn không mô hình hóa quy tắc.

Thực tế, tính đúng của hệ thống còn phụ thuộc vào:

- Schema và constraints đã khai báo.
- Transaction boundary.
- Cách mã hóa luật nghiệp vụ.
- Mức cô lập và chiến lược khóa.
- Cách ứng dụng phản ứng khi SQL trả về 0 hàng hoặc báo lỗi.
- Các hệ thống bên ngoài transaction.

Đây là lý do “PostgreSQL hỗ trợ ACID” **không đồng nghĩa “mọi nghiệp vụ viết trên PostgreSQL đều tự đúng”**.

---

## 5. I — Isolation: nhiều transaction không được tạo ra kết quả sai do tương tranh

**Isolation (tính cô lập)** đề cập tới cách transaction hoạt động khi nhiều kết nối thực thi đồng thời.

PostgreSQL sử dụng **Multi-Version Concurrency Control (MVCC)** để quản lý các phiên bản hàng và snapshot đọc dữ liệu. Nói đơn giản, truy vấn có thể nhìn một phiên bản dữ liệu phù hợp với snapshot của nó thay vì buộc mọi `SELECT` phải đợi `UPDATE` của transaction khác.

Tuy nhiên, **các mức cô lập có bảo đảm khác nhau**. Không nên hiểu isolation là “mọi transaction luôn chạy như từng cái một” ở mọi cấu hình.

### 5.1. Các mức cô lập PostgreSQL

| Isolation level | Ý nghĩa thực hành trong PostgreSQL |
| --- | --- |
| `READ UNCOMMITTED` | PostgreSQL xử lý thực tế như `READ COMMITTED`; không cho dirty read như tên gọi gợi ý |
| `READ COMMITTED` | Mặc định; mỗi câu lệnh có snapshot mới lúc bắt đầu, có thể thấy dữ liệu khác ở câu `SELECT` tiếp theo |
| `REPEATABLE READ` | Cùng snapshot cho các truy vấn thích hợp trong một transaction; ngăn nhiều bất thường đọc, nhưng vẫn có thể xuất hiện **serialization anomaly** |
| `SERIALIZABLE` | Cố gắng bảo đảm kết quả tương đương một thứ tự thực thi tuần tự; có thể hủy một transaction bằng lỗi serialization và yêu cầu retry |

Chỉ định mức cô lập khi bắt đầu:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
-- Thực hiện câu SQL...
COMMIT;

BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Thực hiện câu SQL...
COMMIT;

BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Thực hiện câu SQL...
COMMIT;
```

Đây là ba **transaction riêng để minh họa cú pháp**; không chạy lệnh đổi isolation giữa lúc transaction đã thực thi truy vấn khi không đáp ứng điều kiện của PostgreSQL.

### 5.2. `READ COMMITTED`: hai lần đọc có thể khác nhau

Giả sử số dư tài khoản 1 là 1.000.000. Hai kết nối chạy:

**Session A**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance_cents
FROM acid_lab.accounts
WHERE account_id = 1;

-- Chờ Session B commit...

SELECT balance_cents
FROM acid_lab.accounts
WHERE account_id = 1;

COMMIT;
```

**Session B**

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 10000
WHERE account_id = 1
  AND balance_cents >= 10000;
```

Nếu B commit giữa hai câu `SELECT` của A, A có thể đọc hai giá trị khác nhau. Đây là **non-repeatable read**, có thể xảy ra ở `READ COMMITTED`.

Không nên tự động coi đó là lỗi PostgreSQL: đó là hành vi cho phép của mức cô lập mặc định. Nếu nghiệp vụ cần snapshot ổn định qua nhiều truy vấn, cần chọn cơ chế phù hợp.

### 5.3. `REPEATABLE READ` và snapshot isolation

Ở `REPEATABLE READ`, PostgreSQL dùng snapshot ổn định theo transaction (được thiết lập ở truy vấn phù hợp đầu tiên). Các truy vấn đọc lại trong cùng transaction thấy phiên bản nhất quán theo snapshot đó, thay vì nhìn mỗi lần một snapshot mới.

Điều này giúp tránh nhiều loại bất thường đọc, nhưng không đảm bảo mọi invariant đa hàng khi hai transaction cùng đọc rồi sửa những hàng **khác nhau**.

Ví dụ có hai bác sĩ trực; quy định là **ít nhất một người phải trực**. Hai transaction cùng đọc “có 2 người trực”, rồi mỗi transaction bỏ lịch của một bác sĩ khác nhau. Nếu không cùng cập nhật một hàng và không có biện pháp bảo vệ bất biến, cả hai có thể commit dưới snapshot isolation, dẫn đến **không ai trực**. Trường hợp này được gọi là *write skew*.

Vì vậy `REPEATABLE READ` không nên được mô tả như “đã tương đương SERIALIZABLE cho mọi quy tắc nghiệp vụ”.

### 5.4. `SERIALIZABLE` không có nghĩa sẽ không bao giờ có lỗi

PostgreSQL triển khai serializable với cơ chế **Serializable Snapshot Isolation (SSI)**. Nó có thể phát hiện mô hình tương tranh nguy hiểm và từ chối một transaction để tránh kết quả không thể giải thích như một lịch tuần tự hợp lệ.

Ứng dụng có thể nhận SQLSTATE `40001` (`serialization_failure`).

Khi đó phải:

1. `ROLLBACK` transaction thất bại.
2. Thử lại **toàn bộ logic transaction**, bao gồm các truy vấn đã quyết định dữ liệu sẽ cập nhật.
3. Giới hạn số lần retry, dùng backoff/jitter phù hợp và ghi nhận lỗi nếu không thể hoàn tất.

Chỉ lặp lại **câu SQL cuối cùng** có thể không đủ, vì các quyết định trước đó đã dựa trên một snapshot bị hủy.

### 5.5. Row lock và atomic UPDATE

Khi nhiều transaction cập nhật cùng một hàng, PostgreSQL sử dụng cơ chế khóa hàng để phối hợp. Ở `READ COMMITTED`, một câu:

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 10000
WHERE account_id = 1
  AND balance_cents >= 10000
RETURNING account_id, balance_cents;
```

có thể an toàn hơn mẫu:

```text
SELECT balance_cents ở ứng dụng
Ứng dụng tính balance_moi = balance_cu - 10000
UPDATE accounts SET balance_cents = balance_moi
```

Với mẫu đọc–tính–ghi không có kiểm soát cạnh tranh, hai request có thể cùng đọc một số dư cũ rồi ghi đè giá trị dựa trên thông tin đã lỗi thời. Trong mẫu `UPDATE ... SET balance_cents = balance_cents - ... WHERE balance_cents >= ...`, việc kiểm tra điều kiện và giảm giá trị được PostgreSQL thực hiện như một thao tác cập nhật có điều kiện; câu lệnh có thể chờ update đồng thời và kiểm tra lại phiên bản hàng phù hợp theo quy tắc mức cô lập.

Dù vậy, ứng dụng **phải kiểm tra số hàng `RETURNING`**: nếu 0 hàng, tiền chưa được trừ vì không tồn tại tài khoản hoặc không đủ số dư. Điều đó không tự là lỗi SQL.

### 5.6. Deadlock và thứ tự khóa

Hai transaction có thể cập nhật hai tài khoản theo thứ tự ngược nhau:

```text
Transaction T1: khóa A, sau đó cần khóa B
Transaction T2: khóa B, sau đó cần khóa A
                        |
                        v
                 Chờ vòng (deadlock)
```

PostgreSQL phát hiện deadlock và hủy một transaction, thường có SQLSTATE `40P01`. Đây là cơ chế bảo vệ hệ thống, không phải lời hứa ứng dụng không cần xử lý lỗi.

Để giảm nguy cơ:

- Thực hiện cập nhật/khóa nhiều hàng theo **thứ tự khóa nhất quán** trên mọi code path.
- Giữ transaction ngắn, tránh đợi network hoặc người dùng trong lúc giữ khóa.
- Đảm bảo điều kiện tìm hàng có index phù hợp khi cần.
- Có cơ chế retry giới hạn cho lỗi deadlock khi thao tác nghiệp vụ cho phép.

---

## 6. D — Durability: thay đổi đã commit phải có khả năng phục hồi

**Durability (tính bền vững)** đề cập tới việc các thay đổi được xác nhận thành công vẫn có thể được phục hồi theo bảo đảm lưu trữ và cấu hình của PostgreSQL sau sự cố.

PostgreSQL sử dụng **Write-Ahead Log (WAL)**. Thay vì bắt buộc ghi ngay mọi trang dữ liệu đã sửa về tệp dữ liệu trước khi trả lời cho mỗi commit, hệ thống ghi đủ thông tin phục hồi vào WAL theo cơ chế write-ahead.

Một mô hình đơn giản:

```text
UPDATE / INSERT / DELETE
          |
          v
Dữ liệu thay đổi trong bộ nhớ và trang liên quan
          |
          v
Ghi thông tin phục hồi vào WAL
          |
          v
COMMIT và xử lý độ bền WAL theo cấu hình
          |
          v
Trang dữ liệu có thể được ghi về tệp dữ liệu sau đó
          |
          v
Nếu xảy ra crash: dùng WAL và dữ liệu bền vững để phục hồi
```

WAL không có nghĩa database tự sao lưu mọi lịch sử. Nó là thành phần của cơ chế recovery; **backup và lưu giữ WAL phục vụ khôi phục tới thời điểm** là một chiến lược vận hành khác cần thiết.

### 6.1. Các tham số có thể ảnh hưởng bảo đảm độ bền

Một số tham số PostgreSQL quan trọng:

- `fsync`: điều khiển những nỗ lực đồng bộ ghi dữ liệu ra storage. Tắt `fsync` trong môi trường production có thể làm mất bảo đảm phục hồi khi crash, không phải cách tăng tốc an toàn.
- `synchronous_commit`: điều khiển thời điểm transaction được coi là đã commit so với việc đẩy WAL/nhận xác nhận phù hợp. Khi tắt, một số commit gần thời điểm crash có thể bị mất dù client đã nhận báo hoàn tất.
- `full_page_writes`: liên quan tới việc bảo vệ recovery khỏi trang bị ghi dang dở.
- Các thiết lập replication và lưu WAL ảnh hưởng tới mức độ dữ liệu hiện diện trên các replica và khả năng failover.

Xem cấu hình hiện hành:

```sql
SHOW fsync;
SHOW synchronous_commit;
SHOW full_page_writes;
SHOW wal_level;
```

Các lệnh `SHOW` là **chỉ đọc**. Bài học không yêu cầu thay đổi thông số trên một server đang vận hành.

### 6.2. Commit thành công trên primary không nhất thiết đã tới mọi replica

Nếu hệ thống dùng **asynchronous replication**, transaction có thể commit trên primary trước khi replica nhận và áp dụng thay đổi. Việc chuyển ứng dụng sang một replica chưa bắt kịp có thể làm dữ liệu quan sát thiếu những commit rất mới.

Cấu hình synchronous replication có thể tăng bảo đảm theo chính sách nhất định nhưng có chi phí độ trễ và tính sẵn sàng; không thể xem mọi topology PostgreSQL là đồng bộ chỉ vì được gọi là replication.

Tách biệt:

| Khái niệm | Giúp giải quyết |
| --- | --- |
| WAL và recovery | Phục hồi các thay đổi đã được ghi nhận bền vững sau crash |
| Replication | Duy trì bản sao dữ liệu trên server khác theo chính sách topology |
| Backup | Khôi phục dữ liệu sau xóa nhầm, lỗi logic, hỏng hệ thống hoặc sự cố rộng hơn |
| Monitoring | Phát hiện độ trễ, lỗi ghi, replication lag và dấu hiệu sự cố |

Một replica không thay thế backup: thao tác `DELETE` sai trên primary có thể được sao chép sang replica.

---

## 7. Tạo mô hình dữ liệu chuyển tiền để thực hành ACID

Ví dụ sau dùng một database thử nghiệm mà tài khoản có quyền tạo schema. Nếu không có quyền tạo schema, hãy làm trên schema được cấp phép và thay tiền tố `acid_lab.` tương ứng.

> **Không chạy trên database có dữ liệu thật.** Các lệnh `DROP TABLE` dưới đây xóa bảng thực hành cùng tên và toàn bộ dữ liệu cũ của chúng. Chúng chỉ dành cho một database lab được phép đặt lại.

### 7.1. Tạo hai bảng và các constraints

```sql
CREATE SCHEMA IF NOT EXISTS acid_lab;

DROP TABLE IF EXISTS acid_lab.transfer_requests;
DROP TABLE IF EXISTS acid_lab.accounts;

CREATE TABLE acid_lab.accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance_cents BIGINT NOT NULL
        CHECK (balance_cents >= 0)
);

CREATE TABLE acid_lab.transfer_requests (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    from_account_id INTEGER NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES acid_lab.accounts(account_id),
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT different_accounts
        CHECK (from_account_id <> to_account_id)
);

INSERT INTO acid_lab.accounts
    (account_id, owner_name, balance_cents)
VALUES
    (1, 'An',   100000),
    (2, 'Binh',  30000),
    (3, 'Chi',      0);

SELECT *
FROM acid_lab.accounts
ORDER BY account_id;
```

Giải thích các lựa chọn:

- `BIGINT` biểu diễn số tiền bằng **đơn vị nhỏ nhất** (ví dụ đồng hoặc xu); tránh lỗi làm tròn của `real`/`double precision` khi cộng trừ số tiền.
- `accounts.account_id` định danh duy nhất tài khoản.
- `CHECK (balance_cents >= 0)` từ chối số dư âm ngay ở database.
- `transfer_requests.request_key UNIQUE` là lớp bảo vệ chống ghi cùng khóa yêu cầu hai lần.
- Hai foreign key bảo đảm tài khoản gửi/nhận đã tồn tại khi ghi lịch sử.
- `amount_cents > 0` và hai tài khoản khác nhau là các bất biến nội bộ của một hàng lịch sử.
- `created_at TIMESTAMPTZ` lưu thời điểm có múi giờ theo cơ chế PostgreSQL; cách hiển thị phụ thuộc timezone của session.

Kiểm tra tổng ban đầu:

```sql
SELECT SUM(balance_cents) AS total_cents
FROM acid_lab.accounts;
```

Kết quả ban đầu: `130000`.

### 7.2. Tập dữ liệu nhỏ giúp xem kết quả, không mô phỏng tải đồng thời

Ba hàng mẫu đủ để minh họa rollback, constraints và chuyển tiền. Để quan sát concurrency, bạn cần **hai kết nối PostgreSQL độc lập**; việc chạy các câu lệnh tuần tự trong một session không mô phỏng được tranh chấp thật.

Bài lab không thay thế hệ thống ngân hàng hoàn chỉnh: chưa có đa tiền tệ, phí giao dịch, hạn mức, phê duyệt, đối soát, nhật ký bất biến hay quyền truy cập của từng chủ tài khoản.

---

## 8. Thử Atomicity bằng `BEGIN` và `ROLLBACK`

Trước hết thực hiện chuyển thử 25000 đơn vị từ tài khoản 1 sang 2 nhưng chủ động rollback:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 25000
WHERE account_id = 1
  AND balance_cents >= 25000
RETURNING account_id, balance_cents;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 25000
WHERE account_id = 2
RETURNING account_id, balance_cents;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;
```

Trong transaction, các số dư tạm thời là `75000` và `55000`. Sau `ROLLBACK`, các số dư trở về `100000` và `30000`. Những thay đổi chưa commit của transaction khác thông thường không nhìn thấy hai giá trị tạm thời này.

Trong ví dụ, câu `UPDATE` trả về một hàng mỗi lần vì tài khoản có tồn tại và tiền đủ. **Nếu một câu `RETURNING` trả về 0 hàng, cần chủ động rollback thay vì tiếp tục**. Phần lab được chọn để có kết quả thành công; chương trình thật phải thực thi nhánh kiểm tra đó.

### 8.1. Chuyển tiền và `COMMIT`

Chạy giao dịch hợp lệ:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 25000
WHERE account_id = 1
  AND balance_cents >= 25000
RETURNING account_id, balance_cents;

-- Chỉ tiếp tục nếu câu trên trả đúng một hàng.
UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 25000
WHERE account_id = 2
RETURNING account_id, balance_cents;

-- Chỉ tiếp tục nếu câu trên trả đúng một hàng.
INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('demo-transfer-001', 1, 2, 25000)
RETURNING transfer_id, request_key;

COMMIT;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

SELECT transfer_id, request_key, amount_cents
FROM acid_lab.transfer_requests
ORDER BY transfer_id;
```

Kết quả số dư sau commit: tài khoản 1 còn `75000`, tài khoản 2 có `55000`; tổng vẫn là `130000`. Lịch sử có bản ghi `demo-transfer-001`.

**Quan trọng:** Trong một SQL client chạy script tự động, các câu bên trên **không tự dừng** nếu `UPDATE` đầu trả 0 hàng. Comment `-- Chỉ tiếp tục ...` là yêu cầu điều khiển luồng dành cho người học/ứng dụng. Production phải thực hiện kiểm tra số hàng và rollback bằng code hoặc hàm/procedure SQL có xử lý exception; không được coi khối SQL này là một API chuyển tiền an toàn có thể chạy mù.

### 8.2. Minh họa constraint bảo vệ dữ liệu

Thử:

```sql
-- Thực hiện ngoài transaction chuyển tiền trước đó.
UPDATE acid_lab.accounts
SET balance_cents = -1
WHERE account_id = 3;
```

PostgreSQL từ chối vì vi phạm `CHECK (balance_cents >= 0)`.

Tiếp theo:

```sql
INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('bad-missing-account', 999, 2, 1000);
```

Lệnh bị từ chối vì `from_account_id = 999` không có hàng tương ứng trong `accounts`.

Những ví dụ này minh họa ranh giới quan trọng: **constraint có thể chặn dữ liệu sai ngay cả khi ứng dụng quên validate**.

---

## 9. Bảo vệ số dư trước nhiều yêu cầu đồng thời

Giả sử hai client cùng muốn trừ 60000 từ tài khoản 1, vốn đang có `75000` sau phần 8.1.

Không nên làm theo thứ tự chỉ dựa trên giá trị đọc trước ở ứng dụng:

```text
Client A: SELECT balance -> 75000
Client B: SELECT balance -> 75000
Client A: ứng dụng tính 75000 - 60000 = 15000
Client B: ứng dụng cũng tính 75000 - 60000 = 15000
Client A: UPDATE balance = 15000
Client B: UPDATE balance = 15000
```

Nếu không có cơ chế concurrency control phù hợp, hai lần chi tiền có thể bị ghi nhận trong logic nghiệp vụ trong khi số dư chỉ giảm một lần. Đây là một dạng rủi ro **lost update/đọc dữ liệu cũ**.

Hãy để database thực thi cập nhật có điều kiện:

```sql
UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 60000
WHERE account_id = 1
  AND balance_cents >= 60000
RETURNING account_id, balance_cents;
```

Với hai yêu cầu đồng thời, PostgreSQL phối hợp cập nhật cùng hàng bằng cơ chế khóa và quy tắc `READ COMMITTED`. Sau khi một yêu cầu thành công làm số dư còn `15000`, yêu cầu còn lại không thể trừ thêm 60000 và vẫn thỏa điều kiện; nó có thể trả **0 hàng**. Ứng dụng phải hiểu 0 hàng là “không thể thực hiện yêu cầu trong trạng thái hiện tại”, không phải tự động retry vô hạn.

**Không nên chạy lệnh trừ 60000 này nếu muốn giữ nguyên dữ liệu cho các bài tập tiếp theo.** Nó dùng để mô tả hành vi; có thể tạo lại bảng mẫu trước khi thử trực tiếp.

### 9.1. Khi cần kiểm tra nhiều hàng rồi mới ghi

Nếu một nghiệp vụ cần đọc nhiều tài khoản và ra quyết định dựa trên tập hàng, có thể phải khóa các hàng liên quan:

```sql
BEGIN;

SELECT account_id, balance_cents
FROM acid_lab.accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng kiểm tra điều kiện, cập nhật và ghi lịch sử.
-- Sau khi tất cả bước hợp lệ:
COMMIT;
```

`FOR UPDATE` yêu cầu khóa hàng đã chọn trong transaction. Các transaction khác có thể phải chờ khi muốn cập nhật cùng hàng.

Cần thiết kế **thứ tự lấy khóa nhất quán** để giảm deadlock. Không giữ transaction mở trong lúc chờ người dùng hoặc gọi API chậm. Việc khóa nhiều hàng cũng không tự thay thế mọi kiểm tra invariant, đặc biệt khi các bản ghi liên quan có thể được thêm mới hoặc các transaction không cùng tuân theo một quy trình khóa.

---

## 10. Idempotency: không ghi chuyển tiền hai lần khi client retry

Một tình huống thực tế:

1. Client gửi lệnh chuyển tiền có khóa yêu cầu `request_key = 'order-pay-123'`.
2. PostgreSQL commit thành công.
3. Kết nối giữa server ứng dụng và client bị ngắt trước khi client nhận kết quả.
4. Client gửi lại cùng yêu cầu.

Nếu API chạy lại thao tác trừ/cộng tiền mà không kiểm tra, có thể **chuyển hai lần**.

### 10.1. `UNIQUE(request_key)` là lớp bảo vệ quan trọng

Bảng `transfer_requests` trong lab có:

```sql
request_key TEXT NOT NULL UNIQUE
```

PostgreSQL bảo đảm không có hai hàng committed trùng `request_key`. Nếu ứng dụng cố insert duplicate trong cùng transaction sau khi đã cập nhật số dư, lỗi unique khiến transaction không thể commit các cập nhật đó (trừ khi ứng dụng dùng savepoint/exception và cố ý xử lý khác).

Ví dụ sau dùng key đã tồn tại, **chỉ để quan sát lỗi**, không dùng làm cách gọi API production:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 1000
WHERE account_id = 1
  AND balance_cents >= 1000;

INSERT INTO acid_lab.transfer_requests (
    request_key, from_account_id, to_account_id, amount_cents
)
VALUES ('demo-transfer-001', 1, 2, 1000);

-- INSERT trùng UNIQUE sẽ báo lỗi và transaction bị abort.
ROLLBACK;
```

Không nên dùng `ON CONFLICT DO NOTHING` một cách vô điều kiện **sau khi đã trừ tiền**, rồi vẫn commit: nếu phần ghi lịch sử bị bỏ qua do trùng key nhưng cập nhật số dư vẫn xảy ra, nghiệp vụ có thể sai. Idempotency phải bảo vệ **toàn bộ thao tác**, không chỉ một hàng log.

### 10.2. Quy trình idempotency ở tầng ứng dụng

Một thiết kế thông dụng:

- Client tạo hoặc gửi một `request_key` duy nhất cho **một ý định nghiệp vụ**.
- Ứng dụng kiểm tra tính hợp lệ của payload và quyền của người yêu cầu.
- Trong transaction, ứng dụng **đăng ký hoặc khóa key** theo cơ chế chống trùng có ràng buộc database.
- Nếu key đã được xử lý, kiểm tra payload có trùng với yêu cầu trước và trả lại kết quả đã lưu (hoặc trạng thái phù hợp), **không lặp chuyển tiền**.
- Nếu key mới, thực hiện chuyển tiền, ghi kết quả vào database rồi commit.
- Nếu mất kết nối sau commit chưa biết kết quả, ứng dụng kiểm tra lại theo key trước khi chạy một thao tác khác.

**Chỉ có khóa duy nhất là chưa đủ** để cung cấp hoàn chỉnh kết quả API idempotent: cần lưu trạng thái yêu cầu, kết quả, dữ liệu đối chiếu và có quy trình xử lý tình huống cạnh tranh giữa hai request cùng key.

Một key tái sử dụng với payload khác phải bị từ chối hoặc xử lý rõ ràng; không tự hiểu là cùng một lệnh chỉ vì chuỗi key trùng.

### 10.3. `INSERT ... ON CONFLICT` hỗ trợ nhưng không thay thế thiết kế

PostgreSQL cung cấp:

```sql
INSERT INTO some_table (unique_key, value)
VALUES ('abc', 'payload')
ON CONFLICT (unique_key) DO NOTHING;
```

Đây là **mẫu cú pháp**, chưa có bảng `some_table` trong lab. `ON CONFLICT` hữu ích để xử lý cạnh tranh trên unique key, nhưng ứng dụng vẫn phải biết: conflict nghĩa là bản ghi có trước thuộc cùng yêu cầu hay một yêu cầu mâu thuẫn? Có kết quả nào cần trả? Các bước còn lại có được phép chạy hay không?

---

## 11. Ứng dụng phải quản lý vòng đời transaction

Một ứng dụng sử dụng PostgreSQL thường đi qua driver hoặc ORM; transaction nằm trên **một kết nối** hoặc ngữ cảnh transaction cụ thể.

Mô hình ứng dụng:

```text
request
  |
  v
Lấy connection từ pool
  |
  v
BEGIN
  |
  +-- Validate trạng thái liên quan
  +-- Đọc/khóa dữ liệu khi cần
  +-- UPDATE ... RETURNING
  +-- Kiểm tra số hàng trả về
  +-- INSERT lịch sử / outbox
  |
  +-- Thành công ---> COMMIT
  |
  +-- Bất kỳ lỗi ---> ROLLBACK
  |
  v
Trả connection về pool trong trạng thái sạch
```

Những trách nhiệm cốt lõi:

1. **Mở transaction** đúng chỗ, trước những thao tác phải cùng atomic.
2. **Dùng cùng một transaction/connection** cho các câu SQL cần thống nhất. Hai hàm repository vô tình lấy hai connection khác nhau có thể không cùng transaction.
3. **Kiểm tra số hàng ảnh hưởng** và các điều kiện nghiệp vụ, không chỉ exception từ database.
4. **Rollback trong đường lỗi**, kể cả timeout, serialization failure, deadlock và lỗi unique.
5. **Không kéo dài transaction không cần thiết**: không mở transaction rồi chờ người dùng nhập OTP hay chờ HTTP bên ngoài nhiều giây.
6. **Không để connection bị lỗi transaction** quay về pool mà chưa được rollback.
7. **Không retry vô hạn**: phân biệt lỗi tạm thời, lỗi nghiệp vụ và lỗi không rõ kết quả commit.
8. **Quan sát transaction** bằng log và metric để biết lệnh nào lỗi, retry bao nhiêu lần và độ trễ do database hay bên ngoài.

### 11.1. Pseudocode xử lý giao dịch chuyển tiền

Ví dụ độc lập với ngôn ngữ lập trình:

```text
function transfer(requestKey, fromId, toId, amount):
    validate amount > 0
    validate fromId != toId
    authorize caller to debit fromId

    for attempt in boundedRetries:
        begin database transaction
        try:
            acquire/register idempotency key safely
            if prior completed request with same payload:
                rollback/finish according to design
                return prior result

            optionally lock relevant account rows in stable order

            debit = UPDATE accounts
                    SET balance = balance - amount
                    WHERE id = fromId AND balance >= amount
                    RETURNING id

            if debit has not exactly one row:
                rollback
                return insufficient_funds_or_not_found

            credit = UPDATE accounts
                     SET balance = balance + amount
                     WHERE id = toId
                     RETURNING id

            if credit has not exactly one row:
                rollback
                return destination_not_found

            write transfer history and durable result
            write outbox event if needed
            commit
            return success

        catch retryable concurrency error:
            rollback
            backoff with jitter
            retry whole transaction

        catch any other error:
            rollback
            report or map error appropriately
            stop

    report bounded retry exhaustion
```

Pseudocode minh họa **trách nhiệm và ranh giới**, không phải mã triển khai đã xử lý toàn bộ cạnh tranh về idempotency, overflow số, timeout và lỗi commit không xác định. Trong production, cần áp dụng ràng buộc và cơ chế khởi tạo request-key cụ thể, lưu payload/result và xử lý lỗi driver đúng ngôn ngữ đang sử dụng.

**Đặc biệt:** nếu driver báo mất kết nối trong lúc `COMMIT`, không mặc định transaction thất bại. Có thể server đã commit nhưng client chưa nhận được phản hồi. Đó là lý do lưu key nghiệp vụ và có quy trình kiểm tra kết quả sau reconnect quan trọng hơn việc retry “mù”.

---

## 12. Phân loại lỗi PostgreSQL: không phải lỗi nào cũng retry

PostgreSQL thường trả **SQLSTATE** có cấu trúc. Một số mã quan trọng:

| SQLSTATE | Tên thường gặp | Hướng xử lý |
| --- | --- | --- |
| `23505` | `unique_violation` | Kiểm tra trùng khóa/idempotency; không tự retry vô điều kiện |
| `23503` | `foreign_key_violation` | Dữ liệu tham chiếu không hợp lệ hoặc thay đổi cạnh tranh; xử lý theo nghiệp vụ |
| `23514` | `check_violation` | Vi phạm điều kiện `CHECK`; sửa dữ liệu/luồng nghiệp vụ |
| `23502` | `not_null_violation` | Thiếu giá trị bắt buộc |
| `40001` | `serialization_failure` | Retry **toàn bộ transaction** khi nghiệp vụ cho phép |
| `40P01` | `deadlock_detected` | Rollback, retry giới hạn và xem lại thứ tự khóa |
| `55P03` | `lock_not_available` | Có thể xuất hiện với `NOWAIT` hoặc ngữ cảnh không lấy được khóa; xử lý chờ/retry tùy SLA |
| `57014` | `query_canceled` | Có thể do `statement_timeout` hoặc người dùng hủy; kiểm tra nguyên nhân trước khi retry |

Không nên xây logic chỉ dựa vào **chuỗi thông báo lỗi** vì ngôn ngữ và thông điệp có thể thay đổi. Ưu tiên trường SQLSTATE và dữ liệu có cấu trúc của driver.

### 12.1. Tại sao retry cả transaction?

Ví dụ một transaction đọc số đơn hàng còn trống, quyết định tạo đơn mới và cập nhật quota. Nếu lỗi `40001` chỉ được xử lý bằng việc chạy lại câu `INSERT` cuối, các quyết định quota được đưa ra trước đó có thể không còn hợp lệ. Chạy lại toàn bộ transaction đảm bảo các truy vấn quyết định nghiệp vụ được đánh giá trên trạng thái mới.

Cũng cần phân biệt **retry transaction bị database hủy** với **retry yêu cầu sau kết quả commit không xác định**. Loại thứ hai đòi hỏi idempotency và truy vấn xác minh kết quả.

---

## 13. Các quy tắc toàn vẹn nhiều bảng và giới hạn của constraints

Trong lab, `CHECK(balance_cents >= 0)` là bất biến **một hàng**. Một số quy tắc phức tạp hơn:

- Tổng tiền trong tất cả tài khoản phải được bảo toàn khi chuyển.
- Không được có hơn N lượt đặt chỗ tại cùng thời điểm.
- Một đơn hàng có ít nhất một dòng chi tiết trước khi chuyển sang trạng thái `PAID`.
- Không được vượt hạn mức giao dịch trong ngày của mỗi khách.

PostgreSQL không cho bạn viết `CHECK` tùy ý tham chiếu trực tiếp tới bảng khác như một truy vấn tổng hợp thông thường. Những invariant nhiều hàng/bảng thường cần lựa chọn mô hình:

1. **Thiết kế schema** để biến một số quy tắc thành constraint (khóa ngoại, unique, exclusion...).
2. **Transaction có kiểm soát cạnh tranh**, ví dụ khóa một hàng tổng/parent đại diện cho tài nguyên đang quản lý.
3. **Serializable isolation** cùng cơ chế retry.
4. **Trigger hoặc function** bên database khi có lý do rõ ràng và hiểu tác động tương tranh.
5. **Quy trình ứng dụng** kiểm tra điều kiện và phản hồi lỗi, kết hợp constraint để ngăn dữ liệu không hợp lệ.

### 13.1. Constraints có thể được trì hoãn trong một số trường hợp

PostgreSQL hỗ trợ `DEFERRABLE` cho những loại constraint thích hợp như foreign key, unique, primary key và exclusion, cho phép thời điểm kiểm tra theo thiết kế trong transaction.

Ví dụ ý tưởng: cần tạm thời có trạng thái trung gian khi hoán đổi các khóa unique, nhưng cuối transaction phải hợp lệ. Trong trường hợp phù hợp có thể thiết kế constraint `DEFERRABLE INITIALLY DEFERRED`.

Không phải mọi constraint đều trì hoãn được. `NOT NULL` và `CHECK` thông thường không hỗ trợ `DEFERRABLE` theo cùng cách. Việc hoãn kiểm tra chỉ phù hợp khi invariant cuối transaction vẫn được bảo đảm và luồng ghi dữ liệu đã được thiết kế tương ứng.

### 13.2. Thời gian kiểm tra và độ an toàn

Cơ sở dữ liệu có thể từ chối `COMMIT` khi constraint deferrable không thỏa ở cuối transaction. Vì thế ứng dụng phải xử lý lỗi **ở thời điểm commit**, không chỉ tại từng `INSERT` hoặc `UPDATE`.

Một quy tắc quan trọng là: kết quả của thao tác ghi tạm thời trong transaction **chưa phải kết quả cuối cùng** cho tới khi `COMMIT` thành công.

---

## 14. ACID và tác động bên ngoài PostgreSQL

Một giao dịch ứng dụng thực tế thường còn:

- Gửi email xác nhận.
- Phát sự kiện qua message broker.
- Gọi hệ thống thanh toán khác.
- Ghi file lên object storage.
- Gửi thông báo push hoặc gọi webhook.

Những thao tác này không mặc nhiên là một phần của transaction PostgreSQL.

### 14.1. Vấn đề “commit rồi mới gửi message”

Ví dụ:

```text
BEGIN
UPDATE orders SET status='PAID'
COMMIT

send message "OrderPaid"
```

Nếu ứng dụng crash **sau commit nhưng trước khi gửi message**, database có đơn đã thanh toán nhưng hệ thống khác không nhận thông báo.

Đảo ngược thứ tự cũng có rủi ro:

```text
send message "OrderPaid"

BEGIN
UPDATE orders SET status='PAID'
ROLLBACK
```

Người nhận có thể xử lý thông báo cho một thay đổi chưa từng được commit.

### 14.2. Transactional outbox

Một cách tiếp cận phổ biến là ghi **outbox event vào cùng PostgreSQL transaction** với thay đổi nghiệp vụ:

```text
BEGIN
  UPDATE business_data ...
  INSERT INTO outbox_events (...) VALUES (...)
COMMIT
        |
        v
Worker đọc sự kiện outbox đã commit
        |
        v
Gửi tới broker/API
        |
        v
Ghi nhận trạng thái phát và retry nếu cần
```

Việc cùng ghi business data và outbox trong một transaction giúp tránh trạng thái “đơn đã commit nhưng event không có bản ghi để phát”.

Tuy nhiên outbox **không tự tạo bảo đảm exactly-once cho mọi bên ngoài**. Worker có thể gửi message thành công rồi crash trước khi đánh dấu đã gửi, khiến message được gửi lại. Consumer nên thiết kế **idempotent** và lưu khóa sự kiện đã xử lý khi cần.

### 14.3. Giao dịch phân tán không tự xuất hiện vì có PostgreSQL

Nếu thao tác cần commit đồng thời giữa PostgreSQL và một dịch vụ bên ngoài, giao dịch local không thể tự bảo đảm atomicity trên cả hai. Những thiết kế như saga, outbox/inbox, idempotency hoặc cơ chế điều phối phân tán cần được chọn dựa trên yêu cầu nghiệp vụ.

Đừng giữ transaction database mở trong lúc chờ một dịch vụ bên ngoài quá lâu chỉ để mong đạt “atomicity” giữa hai hệ thống.

---

## 15. Kiểm soát quyền truy cập cũng là trách nhiệm của ứng dụng

ACID tập trung vào giao dịch và tính đúng của dữ liệu, **không thay thế xác thực và phân quyền**.

Ví dụ, nếu service account PostgreSQL có quyền `UPDATE acid_lab.accounts`, database biết connection đó có quyền cập nhật bảng; nhưng không tự biết người dùng HTTP đang gửi yêu cầu có phải chủ tài khoản nào hay không nếu kiến trúc không biểu diễn quyền đó.

Các lớp nên được tách:

| Lớp | Ví dụ trách nhiệm |
| --- | --- |
| Client/API | Kiểm tra dữ liệu đầu vào, định dạng, quyền truy cập chức năng |
| Application service | Xác thực người dùng, kiểm tra chủ tài khoản, hạn mức, idempotency, điều phối transaction |
| PostgreSQL role/GRANT | Giới hạn service có thể đọc/ghi schema, bảng, cột hoặc thực thi function nào |
| PostgreSQL constraints | Ngăn những trạng thái dữ liệu không hợp lệ đã được mô hình hóa |
| PostgreSQL transaction/isolation | Phối hợp nhiều câu lệnh và truy cập đồng thời |
| Logging/monitoring | Truy vết, phát hiện lỗi, đo độ trễ và vận hành |

PostgreSQL còn có **Row-Level Security (RLS)** để hỗ trợ chính sách truy cập theo hàng khi kiến trúc phù hợp. Tuy nhiên, bật RLS không tự giải quyết toàn bộ xác thực người dùng cuối; phải thiết kế cách truyền danh tính vào session an toàn và kiểm tra quyền của role, chủ bảng và các trường hợp bypass.

Không cấp quyền quản trị hoặc quyền `DROP` schema cho tài khoản ứng dụng chỉ vì muốn triển khai nhanh. Tách account migration khỏi account runtime giúp giảm tác động của lỗi ứng dụng.

---

## 16. Thời gian giao dịch và khả năng vận hành

Transaction dài gây nhiều vấn đề dù SQL đúng:

- Giữ row lock, khiến transaction khác phải chờ.
- Có thể khiến PostgreSQL giữ lại các phiên bản hàng cũ lâu hơn, ảnh hưởng công việc của VACUUM và dung lượng.
- Tăng khả năng deadlock khi thay đổi nhiều hàng.
- Tăng độ phức tạp khi connection hỏng hoặc timeout.
- Làm người vận hành khó phân biệt tác vụ đang làm việc với tác vụ “idle in transaction”.

Một số lệnh xem trạng thái để học cách quan sát:

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    wait_event_type,
    wait_event,
    LEFT(query, 150) AS query_text
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Kết quả hiển thị phụ thuộc quyền của tài khoản quan sát; thông tin SQL của những session khác có thể bị giới hạn. Một số trường chứa dữ liệu nhạy cảm, nên không công khai output trên môi trường sản xuất.

Nếu cần giới hạn thời gian, có thể cấu hình các timeout thích hợp ở connection/session hoặc vai trò, chẳng hạn `statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`. Chúng là **cơ chế bảo vệ vận hành**, không thay thế thiết kế transaction đúng.

Ví dụ chỉ dành cho session thử nghiệm:

```sql
SET statement_timeout = '5s';
SET lock_timeout = '2s';
```

Nếu một câu lệnh bị hủy do timeout trong transaction, ứng dụng phải xử lý trạng thái transaction tương ứng (thường là rollback). Không đơn giản chạy tiếp các SQL và mong transaction còn hợp lệ.

---

## 17. Những hiểu lầm phổ biến về ACID và PostgreSQL

| Hiểu lầm | Điều đúng hơn |
| --- | --- |
| “Đặt nhiều câu `UPDATE` nối nhau là atomic.” | Chỉ khi các câu được bao trong **cùng transaction** và các lỗi được xử lý đúng. |
| “Transaction thành công nếu không có exception.” | `UPDATE ... WHERE ...` có thể ảnh hưởng **0 hàng**; phải kiểm tra điều kiện nghiệp vụ. |
| “Atomicity có thể rollback email hoặc HTTP call.” | Rollback PostgreSQL không hoàn tác tác động của hệ thống khác. |
| “PostgreSQL tự hiểu mọi quy tắc consistency.” | Phải định nghĩa constraint và luồng nghiệp vụ đúng. |
| “`CHECK(amount > 0)` luôn cấm `NULL`.” | `CHECK` chấp nhận biểu thức `NULL`; dùng thêm `NOT NULL`. |
| “Ứng dụng đã kiểm tra trùng nên không cần `UNIQUE`.” | Hai request đồng thời có thể vượt qua kiểm tra trước; database unique giúp chặn cạnh tranh. |
| “`READ UNCOMMITTED` cho đọc dữ liệu chưa commit trong PostgreSQL.” | PostgreSQL xử lý nó như `READ COMMITTED`. |
| “`READ COMMITTED` luôn cho cùng snapshot trong transaction.” | Mỗi statement thường có snapshot mới. |
| “`REPEATABLE READ` bảo đảm mọi bất biến đa hàng.” | Snapshot isolation vẫn có thể có serialization anomaly/write skew. |
| “`SERIALIZABLE` nghĩa là không cần xử lý lỗi.” | Transaction có thể bị hủy với `40001` và cần retry toàn bộ. |
| “Khóa hàng làm mọi nghiệp vụ đúng mà không cần kiểm tra.” | Phải xác định tập hàng, thứ tự khóa, các hàng mới có thể phát sinh và invariants. |
| “`COMMIT` đồng nghĩa mọi replica đã bắt kịp.” | Phụ thuộc topology và cấu hình đồng bộ. |
| “WAL là backup hoàn chỉnh.” | Recovery/WAL và chiến lược backup có mục tiêu khác nhau. |
| “Sequence phải liên tục nếu transaction rollback.” | `nextval()` không rollback; khoảng trống ID là bình thường. |
| “Client mất kết nối sau `COMMIT` nghĩa là transaction thất bại.” | Kết quả có thể **không xác định ở client**; phải kiểm tra bằng idempotency key. |
| “Retry mọi lỗi PostgreSQL là an toàn.” | Chỉ retry lỗi tạm thời thích hợp; lỗi constraint/nghiệp vụ cần xử lý khác. |

---

## 18. Bài tập tự luyện

### Bài 1 — Xác định thuộc tính ACID

Với mỗi tình huống, chỉ ra thuộc tính liên quan và trách nhiệm của ứng dụng:

1. Có hai câu SQL trừ và cộng tiền; câu cộng báo lỗi.
2. Hai người cùng đặt món hàng cuối cùng còn trong kho.
3. Database restart sau khi commit nhưng trước khi trang dữ liệu được ghi hoàn toàn về tệp dữ liệu.
4. Ứng dụng thử insert hai bản ghi có cùng mã yêu cầu.
5. Client gửi lại yêu cầu sau khi bị ngắt mạng đúng thời điểm commit.

**Gợi ý:** Các tình huống có thể liên quan nhiều hơn một thuộc tính; ví dụ số 5 còn đòi hỏi idempotency, không thể chỉ trả lời “Durability”.

### Bài 2 — Thử `ROLLBACK`

Tạo lại dữ liệu ở mục 7, chạy:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 5000
WHERE account_id = 1 AND balance_cents >= 5000;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents + 5000
WHERE account_id = 2;

ROLLBACK;

SELECT account_id, balance_cents
FROM acid_lab.accounts
ORDER BY account_id;
```

Giải thích vì sao số dư không thay đổi sau rollback, và vì sao chạy hai câu `UPDATE` độc lập trong autocommit khác với cùng hai câu nằm trong transaction.

### Bài 3 — Lỗi không phải exception

Vẫn trong dữ liệu lab:

```sql
BEGIN;

UPDATE acid_lab.accounts
SET balance_cents = balance_cents - 5000000
WHERE account_id = 1
  AND balance_cents >= 5000000
RETURNING account_id;

-- Không thấy hàng được RETURNING.
ROLLBACK;
```

Câu `UPDATE` có thất bại vì lỗi SQL không? Tại sao ứng dụng vẫn phải rollback và trả thông báo nghiệp vụ, thay vì tiếp tục bước cộng tiền?

### Bài 4 — Constraint và `NULL`

Giải thích sự khác nhau giữa:

```sql
amount BIGINT CHECK (amount > 0)
```

và:

```sql
amount BIGINT NOT NULL CHECK (amount > 0)
```

Dạng nào loại `NULL`? Nếu muốn không cho chuyển số tiền 0, bạn sẽ chọn dạng nào?

### Bài 5 — Giao dịch hai session

Dùng hai connection PostgreSQL riêng và bảng `acid_lab.accounts`. Ở session A, mở transaction và `UPDATE` một tài khoản nhưng chưa commit; ở session B, thử `UPDATE` chính tài khoản ấy. Quan sát trạng thái chờ, sau đó rollback session A để giải phóng khóa.

Dùng cơ chế timeout trên **session lab** để tránh đợi kéo dài. Trả lời tại sao transaction giữ khóa càng lâu càng có thể làm tăng độ trễ của request khác.

### Bài 6 — Phân biệt `READ COMMITTED` với `REPEATABLE READ`

Thiết kế một thử nghiệm có transaction A đọc cùng số dư hai lần, transaction B thay đổi và commit giữa hai lần đọc. So sánh kết quả kỳ vọng giữa:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
```

và:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
```

Giải thích “cùng snapshot” khác với “không có ai khác được cập nhật dữ liệu”.

### Bài 7 — Xử lý lỗi có phân loại

Ứng dụng nhận các mã `23505`, `23514`, `40001`, `40P01`. Hãy phân loại lỗi nào thường là vi phạm dữ liệu/nghiệp vụ, lỗi nào có thể retry toàn transaction, và cần giới hạn số lần retry thế nào.

### Bài 8 — Tác động bên ngoài transaction

Một hệ thống cần cập nhật đơn hàng và gửi event tới message broker. Hãy mô tả rủi ro của hai thứ tự:

1. Commit database trước, gửi event sau.
2. Gửi event trước, commit database sau.

Sau đó phác thảo cách dùng transactional outbox và giải thích vì sao consumer vẫn cần idempotency.

---

## 19. Checklist thiết kế một thao tác ghi đáng tin cậy

Trước khi triển khai nghiệp vụ quan trọng lên PostgreSQL, hãy tự trả lời:

| Câu hỏi | Điều cần xác định |
| --- | --- |
| Ranh giới transaction ở đâu? | Những câu lệnh database nào phải cùng commit/rollback? |
| Dữ liệu nào luôn phải hợp lệ? | Constraint nào khai báo được ngay trong PostgreSQL? |
| Điều kiện nghiệp vụ nào phải kiểm tra? | Quyền sở hữu, trạng thái, số dư, hạn mức, quy trình phê duyệt |
| Mức cô lập có đủ không? | `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` hay khóa hàng phù hợp |
| Có đọc–tính–ghi không? | Điều kiện có thể đã đổi giữa các câu SQL; cần `UPDATE` có điều kiện hoặc khóa |
| `UPDATE`/`DELETE` ảnh hưởng 0 hàng thì sao? | Nhánh nghiệp vụ và rollback rõ ràng |
| Có cạnh tranh theo khóa duy nhất không? | `UNIQUE` và xử lý conflict/idempotency |
| Lỗi nào retry được? | SQLSTATE, retry toàn transaction, giới hạn và backoff |
| Commit thất bại hoặc không rõ kết quả? | Có khóa yêu cầu và cách truy vấn xác nhận không? |
| Có gửi email/event/API ngoài database? | Outbox hoặc chiến lược nhất quán giữa các hệ thống |
| Tài khoản kết nối có đúng quyền? | Quyền tối thiểu cho ứng dụng, tách migration/admin |
| Có quan sát/khôi phục được không? | Log, metric, backup, kiểm thử restore, theo dõi replication lag |

**Không phải thao tác ghi nào cũng cần `SERIALIZABLE` hoặc `SELECT FOR UPDATE`.** Chọn cơ chế theo invariant và mức cạnh tranh, rồi kiểm tra với thử nghiệm đồng thời thực tế. Cơ chế mạnh hơn có thể tăng khả năng transaction bị rollback/retry, tranh chấp hoặc giảm thông lượng.

---

## Kết luận

ACID là nền tảng quan trọng của PostgreSQL:

- **Atomicity:** các thay đổi trong một transaction được commit hoặc hủy như một đơn vị.
- **Consistency:** database thực thi những ràng buộc toàn vẹn đã khai báo; ứng dụng vẫn phải mô hình hóa và bảo vệ những quy tắc nghiệp vụ phức tạp.
- **Isolation:** PostgreSQL điều phối transaction đồng thời bằng MVCC, locking và các mức cô lập; mức cô lập càng mạnh có thể đòi hỏi xử lý retry.
- **Durability:** WAL và cơ chế lưu trữ hỗ trợ phục hồi các commit theo cấu hình độ bền, nhưng không thay thế backup hoặc đảm bảo mọi replica đã đồng bộ.

Điều quyết định chất lượng ứng dụng không phải chỉ là “đã dùng PostgreSQL”, mà là **đặt đúng ranh giới transaction, định nghĩa đúng constraints, cập nhật có điều kiện, xử lý lỗi/retry và phối hợp các tác động ngoài database**. Khi mỗi lớp làm đúng trách nhiệm của mình, hệ thống có thể vừa giữ dữ liệu nhất quán vừa ứng phó được với cạnh tranh và sự cố thực tế.
