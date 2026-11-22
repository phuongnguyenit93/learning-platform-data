# Autocommit và quyền sở hữu giao dịch của công cụ hoặc ứng dụng

Bạn chạy một câu `UPDATE`, thấy công cụ báo “1 row affected”, rồi nhấn `ROLLBACK` để hủy — nhưng dữ liệu không trở lại như cũ. Ở tình huống khác, ứng dụng Java đã gọi `executeUpdate()` thành công, song một lỗi xảy ra ở bước sau khiến mọi thay đổi biến mất. Lại có trường hợp câu SQL trong cùng một hàm service chạy ở **hai kết nối khác nhau**, nên lệnh rollback của service không hủy được bước ghi trước.

Những tình huống trên thường không xuất phát từ việc `UPDATE` hay `ROLLBACK` sai cú pháp. Vấn đề là **ai đang sở hữu và quản lý transaction**, **kết nối nào tham gia**, và **autocommit đang được cấu hình ra sao**.

Bài học thuộc chương **Giao dịch SQL** của module **Database SQL**. Trọng tâm là:

- Hiểu **autocommit**, giao dịch ngầm và giao dịch tường minh.
- Phân biệt **nguyên tử của một câu SQL** với **nguyên tử của toàn quy trình nghiệp vụ**.
- Xác định **ai có quyền quyết định `COMMIT`/`ROLLBACK`**: SQL client, mã JDBC, connection pool hay transaction manager của framework.
- Nhận diện những lỗi phổ biến khi nhiều câu SQL, nhiều kết nối hoặc nhiều lớp ứng dụng cùng muốn điều khiển transaction.
- Tự kiểm chứng hành vi trên PostgreSQL với ví dụ thử nghiệm, trước khi áp dụng vào hệ thống thật.

Ví dụ SQL chính dùng **PostgreSQL**, ví dụ ứng dụng dùng **JDBC** và **Spring** để minh họa các mô hình phổ biến. Những khác biệt giữa DBMS và công cụ được nêu rõ thay vì giả định chúng đều hoạt động giống nhau.

> **Ý chính:** Transaction không thuộc về một file `.sql`, một màn hình, một hàm Java hay một yêu cầu HTTP theo cách tự động. Nó được thực thi trong **ngữ cảnh kết nối/phiên database**, và một thành phần điều phối phải có **trách nhiệm rõ ràng** đối với việc bắt đầu, kết thúc và xử lý lỗi.

## 1. Transaction là gì và tại sao cần nó?

Một **transaction** là đơn vị công việc mà database xử lý theo các bảo đảm giao dịch của hệ quản trị. Trong mô hình quan hệ giao dịch, các thuộc tính thường được tóm bằng **ACID**:

| Thuộc tính | Ý nghĩa trực quan |
|---|---|
| **Atomicity** — nguyên tử | Các thay đổi dữ liệu giao dịch của một đơn vị công việc được chấp nhận cùng nhau hoặc hoàn tác khi đơn vị đó thất bại |
| **Consistency** — nhất quán | Ràng buộc và bất biến dữ liệu được duy trì theo luật đã thiết kế; database không tự biết mọi quy tắc nghiệp vụ |
| **Isolation** — cô lập | Hạn chế cách các giao dịch đồng thời quan sát/ảnh hưởng lẫn nhau, tùy mức cô lập |
| **Durability** — bền vững | Sau khi commit thành công, thay đổi được ghi nhận theo cam kết bền vững của database |

Giả sử chuyển **100 đơn vị tiền** từ tài khoản A sang B. Quy trình có hai bước:

```text
Tài khoản A: 1000 ── trừ 100 ──> 900
Tài khoản B:  500 ── cộng 100 ──> 600

Tổng trước = 1500
Tổng sau   = 1500
```

Nếu bước trừ tiền thành công nhưng bước cộng tiền thất bại, tổng còn 1400 — vi phạm mục tiêu nghiệp vụ. Cả hai bước phải thuộc **cùng một transaction**, và ứng dụng phải **rollback toàn transaction** nếu bất kỳ bước bắt buộc nào không đạt.

### 1.1. Nguyên tử của câu lệnh khác nguyên tử của quy trình

Một câu `UPDATE accounts SET ... WHERE ...` trong PostgreSQL có tính nguyên tử đối với các thay đổi dữ liệu giao dịch của **câu lệnh đó**. Nhưng một quy trình gồm:

```sql
UPDATE accounts SET balance = balance - 100 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 100 WHERE account_id = 2;
```

là **hai câu SQL riêng**. Nếu mỗi câu được commit độc lập, database không tự biết chúng phải cùng thành công hoặc cùng thất bại vì đó là quy tắc chuyển tiền của ứng dụng.

### 1.2. `COMMIT` và `ROLLBACK`

- `COMMIT`: kết thúc transaction bằng việc chấp nhận các thay đổi của nó theo quy tắc database.
- `ROLLBACK`: kết thúc transaction bằng việc hoàn tác các thay đổi dữ liệu giao dịch chưa commit.
- `SAVEPOINT`: tạo một mốc để có thể quay lui **một phần** trong transaction hiện tại, nếu DBMS hỗ trợ.

Một transaction **không thể bị rollback sau khi nó đã được commit thành công**. Việc sửa sai sau commit cần giao dịch bù trừ, phục hồi từ dữ liệu lịch sử/backup hoặc quy trình nghiệp vụ riêng.

## 2. Autocommit: định nghĩa chính xác

**Autocommit** là chế độ mà ở đó mỗi câu lệnh SQL được thực hiện như một đơn vị giao dịch độc lập và **được commit tự động khi thành công**, nếu không đang có một giao dịch tường minh chi phối nó.

Hình dung khi autocommit đang bật cho các câu DML thông thường:

```text
Ứng dụng / SQL client gửi:

UPDATE A ...
       │
       ▼
  Transaction #1
       │
       ├─ Thành công → COMMIT tự động
       └─ Thất bại   → hủy câu lệnh

UPDATE B ...
       │
       ▼
  Transaction #2
       │
       ├─ Thành công → COMMIT tự động
       └─ Thất bại   → hủy câu lệnh
```

Điểm nguy hiểm là **transaction #2 thất bại không tự hủy transaction #1 đã commit**.

### 2.1. Autocommit không có nghĩa là không có transaction

Khi autocommit bật, database vẫn thực thi câu lệnh theo bảo đảm giao dịch phù hợp. Điều khác là **ranh giới commit được đặt quanh từng câu lệnh** thay vì quanh cả nhóm câu lệnh do bạn chọn.

Đừng hiểu:

```text
Autocommit ON = SQL bỏ qua ACID
```

Mà hãy hiểu:

```text
Autocommit ON = mỗi câu lệnh thành công thường có ranh giới commit riêng
```

### 2.2. Khi nào autocommit hữu ích?

Autocommit phù hợp với nhiều thao tác độc lập:

- Một câu `INSERT` tự chứa, không có bước nghiệp vụ bắt buộc tiếp theo.
- Một `UPDATE` đã có đủ điều kiện và không cần kiểm chứng trước khi commit.
- Nhiều truy vấn `SELECT` đơn giản, không cần snapshot chung kéo dài qua nhiều câu.
- Công cụ truy vấn tương tác mà người dùng muốn câu lệnh hợp lệ được lưu ngay.

Nó **không đủ** nếu cần “thực hiện ba câu DML, kiểm chứng xong mới quyết định lưu”.

### 2.3. Bật/tắt autocommit ở đâu?

Đây là một điểm phụ thuộc **driver và công cụ**:

- Trong **JDBC**, `Connection.setAutoCommit(boolean)` điều khiển chế độ autocommit của đối tượng `Connection` JDBC; một kết nối JDBC mới theo mặc định của JDBC có autocommit **`true`**, trừ khi DataSource/driver/pool hoặc framework cấu hình và quản lý khác.
- Trong **SQL editor**, có thể có nút “Auto-commit” hoặc “Manual commit”; nó áp dụng theo cách công cụ quản lý **kết nối/phiên**. Không giả định hai tab editor có cùng kết nối.
- Trong **`psql`**, mặc định client hoạt động với autocommit bật; có thể dùng các lệnh client như `\set AUTOCOMMIT off`, nhưng đây là cơ chế của **psql**, không phải câu SQL chuẩn gửi tới mọi database.
- Trong **framework có transaction manager**, framework có thể điều khiển autocommit của kết nối hoặc sử dụng cơ chế khác để gắn kết nối vào transaction hiện có.

Không có một câu `SET AUTOCOMMIT` di động giống nhau trên tất cả PostgreSQL, SQL Server, MySQL, Oracle và mọi công cụ.

## 3. “Ai sở hữu transaction?” là câu hỏi về trách nhiệm

Từ **sở hữu** trong bài này là cách nói về **thành phần có trách nhiệm tạo ranh giới transaction và quyết định commit/rollback**. Nó không có nghĩa một transaction là một đối tượng độc lập có thể được chuyển tùy ý từ kết nối này sang kết nối khác.

### 3.1. Bảng các mô hình sở hữu phổ biến

| Môi trường | Bên thường điều phối transaction | Điều phải kiểm tra |
|---|---|---|
| SQL editor bật autocommit | Công cụ/driver tự commit từng câu | Có thực sự bật? Chạy một câu hay cả script? |
| SQL editor ở chế độ manual | Người dùng qua nút Commit/Rollback, công cụ giữ kết nối | Có transaction đang mở? Tab có dùng đúng connection? |
| `psql` với `BEGIN` tường minh | Người chạy script/phiên `psql` | Đã `COMMIT` hay `ROLLBACK` chưa? |
| JDBC `autoCommit=true` | Driver/database cho từng câu lệnh | Một nhóm câu có bị tách thành nhiều commit không? |
| JDBC tự gọi `setAutoCommit(false)` | Đoạn mã nhận trách nhiệm `commit`/`rollback` | Các câu có chạy trên **cùng Connection** không? |
| Spring `@Transactional` | Transaction manager được cấu hình | Lời gọi có đi qua cơ chế quản lý transaction không? |
| ORM như JPA/Hibernate | Transaction manager/EntityManager và kết nối liên quan | `flush()` có bị nhầm với `commit()` không? |
| Job ETL có nhiều bước | Job/framework hoặc mã tự quản lý | Mỗi batch, từng statement hay toàn job là một transaction? |

### 3.2. Một transaction không tự đi theo “hàm Java”

Giả sử:

```text
transferMoney()
    ├── connectionA: trừ tiền
    └── connectionB: cộng tiền
```

Nếu hai kết nối hoạt động với autocommit, mỗi bước có thể commit riêng dù cùng nằm trong một hàm `transferMoney()`. Nếu muốn giao dịch local database chung, hai bước cần cùng **ngữ cảnh transaction** được quản lý đúng cách; trong JDBC thuần thường là **cùng một Connection**.

### 3.3. Quy tắc một người điều phối

Đối với một đơn vị công việc, cần quy định ai **được phép**:

- Bắt đầu transaction.
- Đặt isolation/read-only/timeout khi thích hợp.
- Chọn `COMMIT`.
- Chọn `ROLLBACK`.
- Đóng/trả kết nối về pool.

Khi framework đã sở hữu transaction, một repository tự gọi `commit()` trên kết nối đó có thể phá ranh giới nghiệp vụ. Ngược lại, khi tự quản lý JDBC mà không ai gọi `commit()` sau `setAutoCommit(false)`, thay đổi có thể bị rollback khi kết nối đóng/trả về pool hoặc bị giữ trong transaction đang mở.

## 4. Tạo dữ liệu thực hành PostgreSQL

Ta sẽ dùng **bảng tạm**, bảo đảm các ví dụ cập nhật tài khoản không đụng dữ liệu ứng dụng thật. Tên bảng bắt đầu bằng `txn_lab_`.

```sql
CREATE TEMP TABLE txn_lab_accounts (
    account_id INTEGER PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance NUMERIC(14, 2) NOT NULL
        CHECK (balance >= 0),
    version_no INTEGER NOT NULL DEFAULT 1
        CHECK (version_no >= 1)
);

CREATE TEMP TABLE txn_lab_transfer_log (
    transfer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    from_account_id INTEGER NOT NULL
        REFERENCES txn_lab_accounts(account_id),
    to_account_id INTEGER NOT NULL
        REFERENCES txn_lab_accounts(account_id),
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO txn_lab_accounts (account_id, owner_name, balance)
VALUES
    (1, 'An', 1000.00),
    (2, 'Binh', 500.00);

SELECT account_id, owner_name, balance, version_no
FROM txn_lab_accounts
ORDER BY account_id;
```

Trạng thái ban đầu:

| account_id | owner_name | balance | version_no |
|---:|---|---:|---:|
| 1 | An | 1000.00 | 1 |
| 2 | Binh | 500.00 | 1 |

Tổng là `1500.00`.

### 4.1. Những lưu ý để thực hành

1. Mở một **phiên PostgreSQL dành riêng cho bài học** và chạy script tạo bảng.
2. Nếu tạo lại bảng trong cùng phiên mà không dọn dữ liệu, PostgreSQL có thể báo bảng đã tồn tại; nên dùng phiên mới cho các kịch bản độc lập.
3. Câu có ghi **NGUY HIỂM** chỉ để phân tích, không chạy trên dữ liệu sản xuất.
4. Bảng `TEMP` chỉ tồn tại trong **phiên kết nối tạo ra nó**. Một kết nối khác **không nhìn thấy chính bảng tạm đó**. Vì vậy, phần quan sát hai phiên bên dưới là **mô hình lý thuyết hoặc cần bảng dùng chung được tạo riêng trong môi trường thử**, không thể chỉ mở hai tab/kết nối rồi mong chúng thấy cùng bảng `TEMP`.
5. Khi thay đổi đã được commit trong phiên thử, dùng **phiên mới** hoặc chủ động khôi phục dữ liệu gốc nếu muốn lặp lại bài từ đầu. `ROLLBACK` sau `COMMIT` **không khôi phục** commit trước.

### 4.2. Một câu `UPDATE` và kết quả trả về

```sql
UPDATE txn_lab_accounts
SET balance = balance - 100,
    version_no = version_no + 1
WHERE account_id = 1
  AND balance >= 100
RETURNING account_id, balance, version_no;
```

Nếu chạy trên dữ liệu gốc, câu lệnh trả một dòng có `balance = 900.00`, `version_no = 2`. Trong autocommit, thay đổi của câu lệnh có thể đã commit ngay khi thành công. Khi đó việc phát hiện bước tiếp theo sai **không tự đảo ngược** 100 đã trừ.

Trong các mục tiếp theo, ta sẽ đặt những câu tương tự trong **`BEGIN ... ROLLBACK`** để có thể hủy thử nghiệm một cách có kiểm soát.

## 5. Thí nghiệm 1: hai câu lệnh với autocommit

Giả sử PostgreSQL client của bạn đang ở chế độ **autocommit mặc định**, không mở `BEGIN`.

```sql
-- Câu 1: trừ 100 từ tài khoản 1.
UPDATE txn_lab_accounts
SET balance = balance - 100
WHERE account_id = 1 AND balance >= 100
RETURNING account_id, balance;
-- 1 dòng, balance=900; trong autocommit, câu này đã được commit.

-- Câu 2: ứng dụng định cộng 100 vào tài khoản 2,
-- nhưng lại truyền nhầm ID 999 không tồn tại.
UPDATE txn_lab_accounts
SET balance = balance + 100
WHERE account_id = 999
RETURNING account_id, balance;
-- 0 dòng; câu SQL không nhất thiết phát sinh lỗi!
```

Trạng thái sau hai câu (nếu bắt đầu từ dữ liệu gốc):

```text
A = 900
B = 500
Tổng = 1400
```

Không những bước 1 đã commit, bước 2 còn **không báo lỗi SQL** vì `UPDATE ... WHERE` khớp 0 dòng là một kết quả hợp lệ về cú pháp và thực thi.

### 5.1. “0 rows affected” cũng là tín hiệu nghiệp vụ

Nếu quy trình chuyển tiền yêu cầu cập nhật chính xác một tài khoản nguồn và một tài khoản đích, nó phải kiểm tra:

```text
debit_row_count  == 1
credit_row_count == 1
```

Chỉ xem “hai câu SQL đều không throw exception” là chưa đủ. Ở ví dụ, bước cộng ảnh hưởng **0 dòng** nên ứng dụng phải coi là **không đạt yêu cầu**, nhưng thời điểm đó đã quá muộn để rollback bước trừ riêng đã commit.

### 5.2. Phát hiện lỗi trong câu thứ hai cũng không cứu câu đầu

Thay bước 2 bằng một câu cố ý vi phạm `CHECK(balance >= 0)`:

```sql
-- Chỉ thử trên bảng TEMP trong phiên thực hành.
UPDATE txn_lab_accounts
SET balance = -1
WHERE account_id = 2;
-- SQLSTATE 23514: CHECK violation.
```

Khi autocommit, câu này thất bại; thay đổi của **chính câu 2** không được lưu. Nhưng câu 1 đã commit vẫn giữ `balance=900` cho tài khoản 1.

### 5.3. Sau autocommit, `ROLLBACK` không quay về trước câu 1

Nếu không có transaction đang mở, lệnh `ROLLBACK` không thể đảo ngược transaction đã commit tự động. Trong PostgreSQL, `ROLLBACK` ngoài transaction có thể chỉ phát cảnh báo không có transaction đang diễn ra.

**Không làm việc này trên hệ thống thật với hy vọng “lỡ sửa rồi thì rollback được”.**

## 6. Thí nghiệm 2: một transaction tường minh

Muốn hai bước chuyển tiền là **một đơn vị**, cần transaction chứa cả hai câu:

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 100,
    version_no = version_no + 1
WHERE account_id = 1
  AND balance >= 100
RETURNING account_id, balance, version_no;
-- Phải có đúng 1 dòng.

UPDATE txn_lab_accounts
SET balance = balance + 100,
    version_no = version_no + 1
WHERE account_id = 2
RETURNING account_id, balance, version_no;
-- Phải có đúng 1 dòng.

SELECT account_id, balance, version_no
FROM txn_lab_accounts
ORDER BY account_id;
-- Trong transaction, A=900; B=600.

SELECT SUM(balance) AS total_balance
FROM txn_lab_accounts;
-- 1500.

ROLLBACK;
```

Vì kết thúc bằng `ROLLBACK`, cả hai giá trị trở lại `1000` và `500` (nếu bộ dữ liệu gốc chưa bị sửa/commit trước đó).

### 6.1. Khi nào thay `ROLLBACK` bằng `COMMIT`?

Trong chương trình thật, sau khi:

- Câu trừ trả đúng một dòng.
- Câu cộng trả đúng một dòng.
- Số tiền dương và đủ số dư.
- Không vi phạm bất biến nghiệp vụ.
- Bản ghi log yêu cầu cũng được ghi thành công.

ứng dụng có thể gọi `COMMIT`. Trong bài thực hành, dùng `ROLLBACK` để minh họa mà không giữ thay đổi.

### 6.2. Khi một bước không đạt, ai quyết định rollback?

Nếu bước cộng trả **0 dòng**, PostgreSQL có thể vẫn cho phép transaction tiếp tục vì đó **không phải lỗi SQL**. Chính **ứng dụng/công cụ** phải phát hiện row count không đạt và **chọn rollback**.

```text
BEGIN
    │
    ├── debit  → 1 row
    │
    ├── credit → 0 rows
    │                 │
    │                 ▼
    │          Ứng dụng phát hiện
    │          thiếu bản ghi đích
    │                 │
    └─────────────────┴── ROLLBACK
```

Transaction đảm bảo **có khả năng rollback nhiều bước cùng nhau**, không tự quyết định rằng hai bước phải ảnh hưởng đúng một dòng.

### 6.3. Transaction không tự làm nghiệp vụ đúng

Nếu lập trình viên chuyển tiền từ A sang tài khoản **khác B nhưng có tồn tại**, cả hai `UPDATE` có thể trả một dòng và transaction có thể commit. Database bảo đảm nguyên tử của thao tác đã viết, chứ không tự đoán người nhận đúng theo yêu cầu khách hàng.

Vì vậy vẫn cần kiểm tra **định danh, quyền truy cập, trạng thái, row count và điều kiện nghiệp vụ**.

## 7. Kết nối là ranh giới cốt lõi

Với transaction SQL local thông thường, trạng thái transaction được duy trì trong **kết nối/phiên database**. Hai kết nối độc lập không mặc nhiên có một transaction chung.

```text
Ứng dụng
 ├── Connection #A
 │       ├── BEGIN
 │       ├── UPDATE tài khoản nguồn
 │       └── ROLLBACK
 │
 └── Connection #B
         └── UPDATE tài khoản đích  (autocommit)

Kết quả: ROLLBACK trên A không hủy thay đổi đã commit trên B.
```

### 7.1. Cùng đối tượng `Connection` là quan trọng với JDBC thuần

Đoạn mã giả nguy hiểm:

```java
Connection a = dataSource.getConnection();
Connection b = dataSource.getConnection();

a.setAutoCommit(false);
// debitAccount dùng a
// creditAccount dùng b, vẫn có thể autoCommit=true
a.rollback();
```

Hàm có tên `creditAccount` không tự tham gia transaction của `a` nếu dùng `b`. Dù hai kết nối trỏ cùng một database, transaction local của `a` không bao trùm mọi thao tác trên `b`.

### 7.2. Cùng thread chưa chắc cùng transaction

Trong ứng dụng dùng connection pool, hai lần gọi `dataSource.getConnection()` có thể trả hai kết nối khác nhau. Một framework transaction manager có thể ràng buộc kết nối vào một ngữ cảnh transaction để những thao tác đúng API dùng chung kết nối, nhưng đó là **cơ chế của framework**, không phải thuộc tính tự nhiên của cùng thread hoặc cùng hàm.

Không nên:

```text
“Mọi câu SQL chạy trong HTTP request này chắc đều cùng transaction.”
```

Hãy xác nhận cách service, repository, driver và transaction manager thực sự lấy connection.

### 7.3. Bảng tạm không dùng để kiểm thử liên kết nhiều kết nối

Vì `txn_lab_accounts` là bảng PostgreSQL `TEMP`, kết nối khác không thấy cùng bảng. Nếu muốn thử A đọc dữ liệu chưa commit từ B, phải dùng **bảng dùng chung trong một schema thử nghiệm**, cấp quyền phù hợp và tạo dữ liệu thử riêng. Không tạo bảng chung trong môi trường sản xuất chỉ để học.

Đây là giới hạn quan trọng khi phân biệt “cùng transaction” và “cùng bảng”: hai kết nối muốn quan sát cùng dữ liệu phải có **quan hệ dùng chung**.

## 8. SQL editor: ai bấm nút `Commit`?

Một SQL editor có thể hoạt động ở hai chế độ:

### 8.1. Auto-commit bật

Ví dụ giao diện:

```text
[ Auto-commit: ON ]

Run: UPDATE accounts ...;
Tool báo: 1 row affected.
→ Lệnh thành công thường được commit tự động.
```

Nút `Rollback` bấm sau đó không thể hủy một lệnh đã được commit.

### 8.2. Manual commit

```text
[ Auto-commit: OFF ]

Run: UPDATE accounts ...;
Tool báo: 1 row affected.
→ Thay đổi đang chờ quyết định trong transaction hiện tại.

Run: SELECT ...;   → có thể thấy giá trị mới trên cùng kết nối.
Click Commit       → lưu.
hoặc Click Rollback → hủy.
```

Chế độ manual còn tùy thuộc cách SQL editor khởi động transaction, xử lý lỗi và chọn kết nối. Có công cụ giữ transaction qua nhiều lệnh, có công cụ chạy mỗi script trong một transaction riêng, và có công cụ tự commit khi tắt manual mode hoặc đóng/switch connection theo chính sách cấu hình.

### 8.3. Các câu hỏi bắt buộc khi dùng SQL client

Trước khi sửa/xóa dữ liệu quan trọng, cần xác nhận:

1. Auto-commit hiện **bật hay tắt**?
2. Tab này đang dùng **connection nào**?
3. Nút “Run statement” chỉ chạy câu đang chọn hay “Run script” chạy nhiều câu?
4. Khi một câu trong script lỗi, công cụ **dừng**, **tiếp tục**, hay **rollback** phần đã chạy?
5. Nếu nhiều câu được thực thi, chúng có được bọc trong **một transaction** không?
6. Đóng tab hoặc đóng kết nối khi còn transaction chưa kết thúc có hiện hộp xác nhận/rollback không?
7. Công cụ có hỗ trợ kiểm tra **row count, kết quả `RETURNING` và cảnh báo câu thiếu `WHERE`** không?

**Không giả định hành vi của công cụ chỉ từ biểu tượng “tia chớp” hoặc nút Run.** Các chế độ chạy một statement và chạy toàn script có thể khác.

### 8.4. Tránh trộn hai cách điều khiển một cách thiếu hiểu biết

Khi SQL editor đã ở manual mode và đang có transaction, người dùng vẫn có thể gõ:

```sql
BEGIN;
UPDATE ...;
COMMIT;
```

Nhưng nếu công cụ cũng tự mở/giữ transaction, `BEGIN` bổ sung có thể tạo thông báo hoặc hành vi khó hiểu, còn `COMMIT` tường minh có thể kết thúc transaction **trước khi người dùng bấm nút Commit của giao diện**.

Lời khuyên thực hành: chọn **một cơ chế quản lý transaction rõ ràng** cho buổi thao tác, hiểu chính sách cụ thể của SQL editor và quan sát trạng thái thật.

## 9. `psql`: autocommit của client và `BEGIN` của SQL

Với PostgreSQL, `psql` là công cụ dòng lệnh. Mặc định khi người dùng gửi từng câu SQL không nằm trong `BEGIN` tường minh, mỗi câu thực thi theo cơ chế autocommit của client.

### 9.1. `BEGIN` hoạt động dù client mặc định autocommit

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 50
WHERE account_id = 1;

SELECT balance
FROM txn_lab_accounts
WHERE account_id = 1;

ROLLBACK;
```

`BEGIN` tạo transaction tường minh trên **phiên PostgreSQL đang chạy**. Câu `UPDATE` không bị commit tự động riêng trong phạm vi transaction đó; `ROLLBACK` hủy thay đổi.

### 9.2. `\set AUTOCOMMIT off` là lệnh của `psql`

Trong chính `psql`, có thể dùng:

```text
\echo :AUTOCOMMIT
\set AUTOCOMMIT off
```

`\set` là **lệnh meta của psql**, không phải câu SQL di động gửi nguyên văn qua JDBC.

Khi tắt autocommit theo cơ chế của psql, công cụ có thể tự mở transaction trước các câu lệnh thích hợp, và người dùng cần `COMMIT` hoặc `ROLLBACK` để kết thúc. Một số lệnh PostgreSQL yêu cầu chạy **ngoài transaction block**, vì vậy manual autocommit có thể gây vướng mắc khi dùng chúng.

### 9.3. Chạy file script: lỗi ở giữa không đồng nghĩa rollback toàn file

Hãy tưởng tượng `batch.sql` chứa:

```sql
UPDATE txn_lab_accounts SET balance = balance - 10
WHERE account_id = 1;

UPDATE txn_lab_accounts SET balance = -1
WHERE account_id = 2;  -- CHECK failure.

UPDATE txn_lab_accounts SET version_no = version_no + 1
WHERE account_id = 1;
```

Nếu chạy một file theo chế độ autocommit mà **không có transaction bao trùm**, câu đầu có thể được commit dù câu thứ hai lỗi. Công cụ có thể tiếp tục câu thứ ba tùy tùy chọn thực thi. **Một file `.sql` không tự là một transaction.**

Với `psql`, những tùy chọn hay dùng cho migration/script có kiểm soát gồm:

```text
psql -X -v ON_ERROR_STOP=1 -1 -f batch.sql
```

Ý nghĩa:

- `-X`: không đọc file khởi tạo cá nhân psql khi khởi chạy.
- `-v ON_ERROR_STOP=1`: dừng khi xảy ra lỗi script thay vì tiếp tục vô ý.
- `-1` / `--single-transaction`: bao script trong một transaction thích hợp.
- `-f batch.sql`: thực thi file script được chỉ định.

**Giới hạn:** không phải mọi statement đều được PostgreSQL cho phép thực hiện trong một transaction block (ví dụ `CREATE INDEX CONCURRENTLY` hoặc `VACUUM` theo điều kiện thông thường); các file chứa lệnh tự kiểm soát transaction cũng cần được thiết kế để tránh xung đột với cơ chế `-1`. Không áp dụng `-1` mù quáng cho mọi script.

### 9.4. `ON_ERROR_ROLLBACK` không phải `ON_ERROR_STOP`

`psql` có biến `ON_ERROR_ROLLBACK` dùng cơ chế savepoint để tiếp tục xử lý trong transaction ở những trường hợp phù hợp. Nó phục vụ mục đích **tiếp tục sau lỗi**, khác với `ON_ERROR_STOP` để **dừng script**.

Không nên dùng chế độ “tiếp tục” cho batch bắt buộc all-or-nothing chỉ vì nó giúp tránh trạng thái transaction bị lỗi. Đặc tả nghiệp vụ phải quyết định có được bỏ qua một số bước hay không.

## 10. JDBC: autocommit là thuộc tính của `Connection`

Trong Java JDBC, API quan trọng:

```java
Connection connection = dataSource.getConnection();
boolean enabled = connection.getAutoCommit();
connection.setAutoCommit(false);
connection.commit();
connection.rollback();
```

Theo JDBC, một `Connection` mới thường mặc định autocommit bật. Nhưng giá trị nhận thực tế từ một **pool/framework** có thể chịu cấu hình của pool hoặc transaction manager. Hãy kiểm tra `getAutoCommit()` ở đúng ngữ cảnh, không chỉ nhớ mặc định của đặc tả.

### 10.1. Khi autocommit bật

```java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());

    try (PreparedStatement ps = connection.prepareStatement(
            "UPDATE accounts SET status = ? WHERE account_id = ?")) {
        ps.setString(1, "SUSPENDED");
        ps.setLong(2, 103L);
        int rows = ps.executeUpdate();
        System.out.println("Affected: " + rows);
    }
}
```

Nếu connection đang autocommit, câu `UPDATE` được commit tự động khi hoàn tất thành công theo quy tắc JDBC/driver. Thoát `try-with-resources` và đóng `Connection` sau đó không biến câu đã commit thành chưa commit.

### 10.2. Khi autocommit tắt, mã gọi phải quyết định kết thúc

```java
connection.setAutoCommit(false);
// ... các statement ...
connection.commit();   // Chỉ nếu tất cả điều kiện nghiệp vụ đạt.
// hoặc:
connection.rollback(); // Nếu có bước không đạt.
```

**Quan trọng:** `commit()`/`rollback()` là thao tác trên **Connection cụ thể**. Nó không tự tác động tới một Connection khác đang được repository hoặc service khác sử dụng.

### 10.3. Một số hành vi JDBC dễ bỏ sót

- Khi **autocommit đã bật**, gọi `commit()` hoặc `rollback()` trực tiếp trên JDBC connection không phải cách hợp lệ để đảo ngược câu đã commit và thường gây `SQLException` theo hợp đồng API.
- Gọi `setAutoCommit(true)` khi connection đang ở chế độ `false` **có thể commit transaction hiện tại** theo hợp đồng JDBC; đừng dùng thao tác đổi chế độ làm cách “dọn dẹp” thay cho `rollback()`.
- Khi đóng/trả connection mà còn transaction chưa kết thúc, hành vi cụ thể còn liên quan driver/pool; không dùng `close()` như kế hoạch rollback một cách ngầm định.
- Việc hoàn tất một câu JDBC trong autocommit có chi tiết khác nhau với API trả nhiều result set/cursor. Với các câu DML đơn giản, nó thường được commit khi câu lệnh hoàn tất; không suy rộng rằng mọi truy vấn đang stream đều có cùng thời điểm kết thúc.

**Kết luận vận hành:** mã tự quản lý transaction phải **commit khi thành công**, **rollback khi thất bại**, rồi **trả connection đúng cách**.

## 11. Ví dụ JDBC đầy đủ: chuyển tiền trong một transaction

Sau đây là mã Java minh họa cách một thành phần **thực sự sở hữu một transaction JDBC local**. Giả sử ứng dụng có bảng dùng chung `bank_accounts(account_id BIGINT PRIMARY KEY, balance NUMERIC(14,2) NOT NULL)` và DataSource quản lý kết nối. Đây là **schema minh họa cho ứng dụng**, không phải bảng TEMP `txn_lab_accounts` của phiên SQL trước.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferRepository {
    private final DataSource dataSource;

    public TransferRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        // Ví dụ này tự sở hữu transaction trên connection lấy về.
        // Không dùng nguyên mẫu này bên trong transaction do Spring quản lý.
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int debited;
                try (PreparedStatement debit = connection.prepareStatement(
                        "UPDATE bank_accounts " +
                        "SET balance = balance - ? " +
                        "WHERE account_id = ? AND balance >= ?")) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    debited = debit.executeUpdate();
                }

                if (debited != 1) {
                    throw new IllegalStateException(
                            "Source missing or insufficient funds");
                }

                int credited;
                try (PreparedStatement credit = connection.prepareStatement(
                        "UPDATE bank_accounts " +
                        "SET balance = balance + ? " +
                        "WHERE account_id = ?")) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    credited = credit.executeUpdate();
                }

                if (credited != 1) {
                    throw new IllegalStateException("Destination missing");
                }

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
```

### 11.1. Vì sao hai `PreparedStatement` phải dùng cùng `Connection`?

Chúng được tạo bởi **cùng `connection` đã gọi `setAutoCommit(false)`**. Nhờ đó, hai `UPDATE` tham gia **một transaction local**. Nếu bước cộng thất bại hoặc trả 0 dòng, `rollback()` trên chính connection này hủy cả bước trừ chưa commit.

### 11.2. Vì sao kiểm tra `executeUpdate()`?

Một `UPDATE` có điều kiện `WHERE account_id=?` không khớp vẫn có thể thực hiện thành công với số dòng tác động `0`. Ứng dụng phải quyết định rằng `0` là thất bại nghiệp vụ trước khi commit.

### 11.3. Vì sao catch cả lỗi runtime?

Kiểm tra nghiệp vụ có thể ném `IllegalStateException`, không chỉ `SQLException`. Nếu bỏ qua `RuntimeException`, một lỗi tại bước đối chiếu có thể làm transaction không được rollback chủ động như mong muốn.

Mã còn dùng `addSuppressed()` để giữ thông tin lỗi rollback nếu lỗi xảy ra trong lúc xử lý ngoại lệ gốc.

### 11.4. Giới hạn của ví dụ

- Đây là **mô hình connection tự quản lý**, giả định thành phần này có quyền quyết định commit và dùng một nguồn kết nối local phù hợp.
- Với connection pool, cơ chế trả connection, khôi phục trạng thái và kiểm tra kết nối hỏng phải được cấu hình đáng tin cậy. Không mượn một connection đang thuộc transaction của framework rồi tự `setAutoCommit(false)`.
- Mã minh họa **không bao gồm** sổ cái tài chính, idempotency key, audit, outbox, isolation/lock ordering và xử lý giao dịch phân tán — những thành phần có thể cần cho hệ thống chuyển tiền thật.
- Nếu xảy ra lỗi kết nối **đúng thời điểm commit**, kết quả commit có thể không chắc chắn từ góc nhìn ứng dụng. Việc retry cần khóa idempotency và quy trình đối soát, không chạy lại tùy tiện.
- Trong code thật, các lỗi khi lấy/trả connection, transaction timeout và khả năng commit/rollback có thể cần được quản lý theo chính sách của pool/framework.

Điểm chính của bài là **các bước bắt buộc dùng cùng transaction, và trách nhiệm commit/rollback thuộc một nơi rõ ràng**.

## 12. Đừng tự `commit()` khi framework đã quản lý transaction

Trong ứng dụng Spring, một service có thể được đánh dấu:

```java
@Transactional
public void transfer(...) {
    // Các thao tác repository.
}
```

Với cấu hình transaction manager và lời gọi qua cơ chế proxy/interceptor phù hợp, **framework** sẽ:

1. Mở hoặc tham gia transaction theo quy tắc propagation.
2. Cho các thao tác data access đúng ngữ cảnh dùng kết nối gắn với transaction.
3. Commit nếu phương thức kết thúc theo chính sách thành công.
4. Rollback khi gặp lỗi thuộc quy tắc rollback đã cấu hình.

### 12.1. Ví dụ Spring với `JdbcTemplate`

Đây là ví dụ triển khai trong dự án Spring đã có DataSource, `JdbcTemplate` và transaction manager phù hợp:

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE bank_accounts " +
            "SET balance = balance - ? " +
            "WHERE account_id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source missing or insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE bank_accounts " +
            "SET balance = balance + ? " +
            "WHERE account_id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Destination missing");
        }
    }
}
```

Ở đây **không gọi** `connection.commit()` hoặc `connection.rollback()` trong service. Transaction manager chịu trách nhiệm. `IllegalStateException` là lỗi runtime nên theo chính sách mặc định quen thuộc của Spring declarative transactions, nó khiến transaction rollback nếu lời gọi thực sự được framework quản lý.

### 12.2. Annotation không thay thế cấu hình và đường gọi

`@Transactional` **không phải phép màu chỉ cần ghi vào source**. Nó phải được hệ thống thực sự áp dụng, ví dụ:

- Bean được Spring quản lý.
- Transaction management được bật/cấu hình đúng.
- Lời gọi đi qua cơ chế proxy/interceptor tương ứng.
- Data access dùng DataSource/EntityManager được liên kết với transaction manager đó.

Một đối tượng tạo trực tiếp bằng `new TransferService(...)` ngoài cơ chế framework, hoặc một phương thức không được interceptor áp dụng, không đương nhiên có transaction chỉ vì có annotation trong mã nguồn.

### 12.3. Tại sao repository không nên tự quyết định commit?

Nếu một service cần:

```text
Tạo đơn
  → Ghi chi tiết đơn
  → Giảm tồn kho
  → Ghi sự kiện outbox
```

thì **service/transaction manager** là nơi phù hợp để xác định **một đơn vị nghiệp vụ chung**. Nếu repository tạo đơn tự commit, nhưng bước giảm tồn kho thất bại, service không thể rollback bước tạo đơn đã commit.

Một nguyên tắc thiết kế:

> **Lớp điều phối nghiệp vụ định nghĩa ranh giới transaction; lớp truy cập dữ liệu thực thi câu SQL bên trong ranh giới đó.**

Đây không phải quy tắc tuyệt đối cho mọi kiến trúc, nhưng là mặc định tốt để tránh nhiều lớp cùng sở hữu commit.

## 13. Các bẫy phổ biến của `@Transactional`

### 13.1. Tự gọi phương thức trên cùng đối tượng

Trong mô hình proxy Spring thông dụng:

```java
@Service
class PaymentService {
    public void handle() {
        this.saveWithTransaction();
    }

    @Transactional
    public void saveWithTransaction() {
        // database operations
    }
}
```

Lời gọi `this.saveWithTransaction()` **không đi qua proxy** trong cách quản lý transaction dựa trên proxy thường gặp. Vì vậy annotation ở `saveWithTransaction` có thể **không khởi động transaction như lập trình viên mong đợi**.

Cách xử lý là đặt ranh giới transaction tại phương thức service được gọi **qua Spring proxy**, hoặc dùng `TransactionTemplate`/cơ chế quản lý phù hợp khi cần gọi nội bộ. Không “sửa” bằng cách tự `commit()` trong repository.

### 13.2. Checked exception và quy tắc rollback

Theo chính sách mặc định phổ biến của Spring, transaction declarative rollback với `RuntimeException` và `Error`, còn **checked exception** không tự làm rollback trừ khi cấu hình thêm.

```java
@Transactional(rollbackFor = Exception.class)
public void processFile() throws Exception {
    // ...
}
```

Chỉ đặt `rollbackFor` theo **quy tắc nghiệp vụ thực sự**, không sao chép như mẹo chung. Nếu ứng dụng bắt lỗi và nuốt ngoại lệ bên trong phương thức, transaction manager có thể thấy phương thức kết thúc bình thường và **commit**, dù thao tác thiếu bước.

### 13.3. Nuốt ngoại lệ có thể làm commit một phần nghiệp vụ

Ví dụ logic:

```java
@Transactional
public void placeOrder() {
    createOrder();
    try {
        decreaseInventory();
    } catch (InventoryException error) {
        log.warn("Inventory unavailable", error);
        // Không ném lại và không đánh dấu rollback-only.
    }
}
```

Nếu `decreaseInventory()` thất bại nghiệp vụ nhưng mã chỉ ghi log rồi kết thúc bình thường, framework có thể **commit các bước trước**, tùy trạng thái transaction và ngoại lệ đã xảy ra ở tầng nào.

Khi thao tác phải all-or-nothing, hãy **truyền lỗi tới ranh giới transaction** hoặc đánh dấu transaction cần rollback bằng cơ chế được framework hỗ trợ. Không tự giả định “đã catch lỗi thì transaction tự hủy”.

### 13.4. `@Transactional(readOnly = true)` không luôn là khóa an toàn

`readOnly=true` thường là hint hoặc cấu hình cho transaction manager/driver/ORM. Mức độ cưỡng chế “không được ghi” tùy database và integration. Nó **không thay thế phân quyền database** và không nên được dùng làm tấm khiên duy nhất chống `UPDATE` nhầm.

### 13.5. Chạy tác vụ sang thread khác

Với Spring transaction manager dựa trên ngữ cảnh thread thông dụng, tạo một thread mới hoặc gửi việc sang executor có thể làm tác vụ đó **không tự tham gia** transaction đang hoạt động ở thread gọi.

```text
Thread A: @Transactional service
    ├── UPDATE 1
    └── submit task → Thread B
                         └── UPDATE 2 trên connection khác
```

Nếu task ở Thread B tự commit, rollback ở Thread A không hủy được phần đó. Các luồng bất đồng bộ phải có thiết kế ranh giới transaction, idempotency và phối hợp dữ liệu rõ ràng.

## 14. Connection pool: ai sở hữu connection và trạng thái của nó?

Các ứng dụng thường dùng pool như HikariCP thay vì tự mở một kết nối vật lý cho mỗi request. Khi gọi:

```java
Connection connection = dataSource.getConnection();
```

đối tượng nhận được có thể là một **wrapper** cho một kết nối vật lý được pool quản lý. Khi gọi `close()`, tùy pool, kết nối thường được **trả về pool**, không nhất thiết đóng TCP connection vật lý ngay.

### 14.1. Vì sao trạng thái cần được khôi phục?

Trong một connection có các thuộc tính và ngữ cảnh như:

- Autocommit.
- Isolation level.
- Read-only flag.
- Session-level settings.
- Transaction đang mở, lock đang giữ, temporary objects.

Nếu một đoạn mã dùng connection rồi trả về pool khi còn transaction chưa kết thúc, hoặc chỉnh cấu hình session mà không phục hồi, request sau có thể gặp kết nối ở trạng thái không như dự đoán. Các pool phổ biến có cơ chế kiểm soát và reset nhất định, nhưng **không được phụ thuộc mù quáng vào nó**; hãy hiểu hợp đồng của pool đang dùng.

### 14.2. Không đổi autocommit thủ công trên connection thuộc Spring

Một cách làm nguy hiểm:

```java
@Transactional
public void doWork() {
    Connection c = dataSource.getConnection();
    c.setAutoCommit(true);
    // ...
}
```

Tùy cách lấy connection và framework, đoạn này có thể:

- Lấy **connection khác**, tạo một bước ghi ngoài transaction mong muốn.
- Đổi trạng thái của **connection đang được transaction manager sử dụng**, phá giả định điều phối.
- Gây lỗi hoặc khiến dữ liệu commit vào thời điểm không dự kiến.

Hãy sử dụng `JdbcTemplate`, repository/EntityManager được cấu hình đúng với transaction manager. Khi thật sự cần JDBC thấp tầng trong Spring, lấy connection theo API của framework có liên kết transaction, và **không tự điều khiển commit** nếu transaction manager đang sở hữu nó.

### 14.3. Mẫu anti-pattern: repository mở và đóng connection riêng

```text
Service @Transactional
    |
    +-- Repository A → new connection → tự commit
    |
    +-- Repository B → transaction-managed connection → rollback
```

Hai repository nằm trong cùng một service không đảm bảo cùng transaction nếu repository A đi vòng qua DataSource/transaction manager. Cần kiểm chứng cấu hình kết nối thực tế, không chỉ nhìn annotation.

### 14.4. Một transaction dài ảnh hưởng pool

Transaction để mở trong lúc:

- Người dùng nhập form.
- Ứng dụng chờ API ngoài.
- Chương trình đọc tệp lớn rồi mới tiếp tục.
- SQL editor để màn hình nghỉ giữa `BEGIN` và `COMMIT`.

có thể giữ kết nối và lock, làm các request khác phải chờ. Pool hữu hạn có thể cạn kết nối, xuất hiện timeout dù SQL đơn lẻ không chậm.

**Giữ transaction ngắn, làm những công việc không thuộc database ngoài ranh giới transaction khi có thể**, và dùng timeout phù hợp.

## 15. Commit trong ORM: `flush()` không phải `commit()`

Với JPA/Hibernate, lập trình viên có thể gọi:

```java
entityManager.persist(entity);
entityManager.flush();
```

`flush()` thường yêu cầu ORM đồng bộ những thay đổi đang chờ thành SQL gửi xuống database trong transaction hiện tại. Nó có thể làm lỗi ràng buộc xuất hiện sớm hơn, nhưng **không đồng nghĩa transaction đã commit**.

```text
persist() → lên lịch thay đổi trong persistence context
flush()   → gửi SQL cần thiết tới database
commit()  → kết thúc transaction thành công
```

Trình tự cụ thể phụ thuộc chiến lược tạo ID, flush mode, truy vấn và framework. Không phải mọi lệnh `persist()` đều chỉ nằm trong bộ nhớ cho tới lúc `flush`, nhưng **được gửi xuống database** vẫn không phải **đã commit bền vững**.

### 15.1. Một lỗi có thể xuất hiện vào lúc flush hoặc commit

Ví dụ:

- `UNIQUE` vi phạm có thể được phát hiện khi ORM thực thi `INSERT`.
- Ràng buộc deferred có thể được kiểm tra đến `COMMIT`.
- Vấn đề đồng thời/isolation có thể khiến commit thất bại.

Ứng dụng không nên trả HTTP “tạo thành công” chỉ dựa trên việc `persist()` không throw exception nếu transaction chưa kết thúc theo chính sách thành công.

### 15.2. Không dùng `entityManager.getTransaction()` ở mọi môi trường

Trong JPA resource-local transaction tự quản lý, `EntityTransaction.begin()/commit()` là một mô hình hợp lệ. Nhưng trong môi trường transaction do Spring/JTA quản lý, quyền quyết định commit thuộc transaction manager tương ứng; ứng dụng không nên dùng `getTransaction().commit()` một cách tùy tiện trên EntityManager được container quản lý.

## 16. Propagation: một lời gọi có thể tham gia hay tạo transaction mới

Trong Spring, `@Transactional` có thuộc tính **propagation** để quyết định phương thức nên **tham gia transaction hiện có** hay **tạo transaction mới** theo quy tắc cấu hình.

### 16.1. `REQUIRED` — dùng cái đang có, hoặc mở mới

Đây là propagation mặc định quen thuộc:

```text
Service A (@Transactional REQUIRED)
   ├── Repository A
   └── Service B (@Transactional REQUIRED)

→ Thường tham gia cùng transaction trong cùng ngữ cảnh quản lý.
```

Nếu một thao tác bắt buộc thất bại và transaction bị đánh dấu rollback-only, toàn đơn vị có thể không commit, kể cả khi lớp ngoài tưởng đã xử lý lỗi.

### 16.2. `REQUIRES_NEW` — transaction độc lập

```text
Outer transaction
   ├── UPDATE order
   ├── Inner service (@Transactional REQUIRES_NEW)
   │       └── INSERT audit → COMMIT riêng
   └── Outer transaction → ROLLBACK
```

Trong mô hình phù hợp, transaction bên trong có thể **commit dù transaction bên ngoài rollback**. Đây đôi khi là thiết kế được chọn cho một loại log độc lập, nhưng sẽ là lỗi nếu nghiệp vụ yêu cầu audit và order **cùng tồn tại hoặc cùng mất**.

`REQUIRES_NEW` có thể cần thêm connection và làm tăng áp lực lên pool. Không dùng nó chỉ để “chặn lỗi rollback” mà chưa hiểu tính độc lập dữ liệu.

### 16.3. `NESTED` — sử dụng savepoint khi được hỗ trợ

Trong một số transaction manager/driver phù hợp, `NESTED` có thể dùng **savepoint** bên trong transaction ngoài. Rollback phần nested sẽ phục hồi về savepoint; commit thật vẫn do transaction ngoài quyết định.

Không coi `NESTED` và `REQUIRES_NEW` là đồng nghĩa:

| Đặc tính | `REQUIRES_NEW` | `NESTED` khi dùng savepoint |
|---|---|---|
| Ranh giới commit | Transaction riêng | Commit cuối vẫn theo transaction cha |
| Rollback cha sau khi bước con “xong” | Không tự rollback transaction con đã commit | Có thể rollback cả các bước con còn trong cha |
| Yêu cầu hạ tầng | Hỗ trợ transaction mới và tài nguyên phù hợp | Savepoint và transaction manager hỗ trợ |

Đừng suy đoán chính xác propagation nếu không xem cấu hình transaction manager thực tế.

## 17. Lỗi PostgreSQL trong transaction: trạng thái aborted

Một đặc điểm quan trọng của PostgreSQL là: nếu một statement phát sinh lỗi trong transaction tường minh, transaction thường chuyển sang **trạng thái failed/aborted**. Những lệnh SQL thông thường tiếp theo sẽ bị từ chối cho tới khi transaction được phục hồi hoặc hủy.

### 17.1. Ví dụ `CHECK` thất bại

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 50
WHERE account_id = 1;
-- Thành công nhưng chưa commit.

UPDATE txn_lab_accounts
SET balance = -1
WHERE account_id = 2;
-- SQLSTATE 23514: vi phạm CHECK(balance >= 0).

SELECT balance FROM txn_lab_accounts;
-- SQLSTATE 25P02: current transaction is aborted ...

ROLLBACK;
-- Thay đổi trừ 50 cũng bị hủy.
```

Điều đáng chú ý: lỗi ở câu 2 không tự chọn “bỏ qua câu 2 rồi tiếp tục câu 3” trong cùng transaction PostgreSQL. Transaction cần rollback hoặc quay lại một savepoint phù hợp.

### 17.2. Vì sao `25P02` không phải lỗi gốc?

`25P02` nói rằng **transaction đã ở trạng thái lỗi**, không chỉ ra nguyên nhân ban đầu. Lỗi gốc trong ví dụ là `23514`.

Khi debug, hãy tìm **statement đầu tiên báo lỗi** và SQLSTATE ban đầu. Sửa câu `SELECT` sau đó không giải quyết lỗi `25P02`.

### 17.3. Trạng thái sau lỗi trong autocommit khác thế nào?

Nếu không ở transaction tường minh, một câu DML đơn lẻ lỗi thường khiến **câu đó thất bại** và phiên có thể tiếp tục thực thi câu mới ở giao dịch kế tiếp. Trong transaction tường minh, lỗi ảnh hưởng **trạng thái transaction hiện tại** cho tới rollback hoặc savepoint.

Đây là khác biệt quan trọng giữa “câu lệnh lỗi” và “transaction nhiều câu đang lỗi”.

## 18. `SAVEPOINT`: ai được phép xử lý lỗi cục bộ?

`SAVEPOINT` cho phép đánh dấu một vị trí trong transaction và hoàn tác những thay đổi sau mốc đó, thay vì luôn hủy toàn transaction.

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 20
WHERE account_id = 1;

SAVEPOINT before_optional_step;

UPDATE txn_lab_accounts
SET balance = -1
WHERE account_id = 2;
-- Lỗi CHECK.

ROLLBACK TO SAVEPOINT before_optional_step;

-- Có thể tiếp tục transaction sau khi phục hồi thành công.
SELECT account_id, balance
FROM txn_lab_accounts
ORDER BY account_id;

ROLLBACK;
```

Sau `ROLLBACK TO SAVEPOINT`, thay đổi **trước savepoint** vẫn đang trong transaction (A còn 980 trong ví dụ), nhưng thay đổi gây lỗi ở bước sau không được giữ. Cuối cùng `ROLLBACK` toàn bộ đưa A về 1000.

### 18.1. Savepoint không biến statement nhiều dòng thành chèn từng dòng

Một `INSERT` nhiều dòng lỗi ràng buộc vẫn thất bại **như một statement**. `SAVEPOINT` cho phép phục hồi transaction về trước câu lỗi, chứ không tự cho phép giữ các dòng hợp lệ trong statement thất bại.

### 18.2. Savepoint vẫn cần quyết định của chủ sở hữu transaction

Nếu framework đang quản lý transaction, dùng savepoint qua API phù hợp của transaction manager/JDBC được phép trong ngữ cảnh đó. Không tự thêm các `COMMIT` thủ công vào giữa transaction framework để “đóng savepoint”.

### 18.3. Không nên che lỗi nghiệp vụ bắt buộc

Nếu quy trình chuyển tiền có hai bước **bắt buộc**, việc rollback đến savepoint trước bước cộng rồi **commit bước trừ** là sai nghiệp vụ. Savepoint phù hợp cho **bước tùy chọn** hoặc chính sách chấp nhận một phần, không phải cách làm mọi transaction đều “thành công” dù còn thiếu bước.

## 19. Nhiều cửa sổ SQL và dữ liệu chưa commit

Giả sử hai session độc lập kết nối tới **cùng bảng dùng chung**:

```text
Session A:
BEGIN;
UPDATE bank_accounts SET balance = 900 WHERE account_id=1;
-- Chưa commit.

Session B:
SELECT balance FROM bank_accounts WHERE account_id=1;
```

Trong PostgreSQL mức cô lập `READ COMMITTED` thông thường, session B **không đọc giá trị chưa commit của session A**; nó thường thấy phiên bản đã commit trước đó, ví dụ `1000` (giả sử không có cập nhật đã commit khác).

Sau khi A `COMMIT`, một câu `SELECT` **mới** của B trong `READ COMMITTED` thường có thể thấy phiên bản mới. Nếu B dùng `REPEATABLE READ` với snapshot đã được thiết lập, kết quả có thể khác tới khi transaction của B kết thúc.

### 19.1. Thấy thay đổi trong chính session không có nghĩa đã commit

Session A thường **đọc thấy thay đổi chưa commit của chính transaction A**:

```text
A UPDATE balance=900
A SELECT balance → 900
```

Nhưng B vẫn có thể thấy 1000 trong thời gian A chưa commit. Vì vậy, chạy `SELECT` lại trên **cùng connection** chỉ chứng minh trạng thái **bên trong transaction**, không chứng minh đã commit.

### 19.2. Hai tab có thể dùng cùng hoặc khác connection

Một IDE có thể:

- Dùng một connection chung cho nhiều tab.
- Cấp connection riêng cho từng tab.
- Cấp connection riêng cho việc chạy script.

Không suy luận tình trạng commit chỉ từ việc hai cửa sổ hiển thị khác nhau. Nếu cần xem kết nối PostgreSQL của editor:

```sql
SELECT pg_backend_pid() AS backend_pid;
```

Giá trị PID có thể giúp nhận ra liệu hai câu đang được thực thi trên cùng **backend session tại thời điểm quan sát**. Nó không thay thế kiểm tra transaction/autocommit và có thể thay đổi khi công cụ reconnect.

## 20. Transaction isolation không phải autocommit

Hai khái niệm giải quyết hai vấn đề khác nhau:

- **Autocommit**: một câu lệnh hay một nhóm câu lệnh được commit ở ranh giới nào?
- **Isolation level**: các giao dịch đồng thời được phép quan sát và tương tác như thế nào?

Ví dụ PostgreSQL:

```sql
SHOW transaction_isolation;
SHOW default_transaction_isolation;
```

Có thể đặt mức cô lập cho một transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- Các câu SELECT/UPDATE phù hợp.
ROLLBACK;
```

Các mức như `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` có quy tắc snapshot, tranh chấp và retry khác nhau. Nhưng **đổi isolation không tự biến hai connection độc lập thành một transaction**.

### 20.1. Snapshot chung khi đọc nhiều bước

Với báo cáo cần đọc nhiều bảng tại một thời điểm logic nhất quán, transaction ở isolation phù hợp có thể giúp tránh những thay đổi nhìn thấy giữa các câu SELECT.

Nhưng nếu autocommit bật và mỗi `SELECT` chạy trong một transaction riêng, hai câu có thể quan sát hai snapshot khác nhau ngay cả khi được gọi liên tiếp. Nếu nghiệp vụ yêu cầu snapshot chung, phải chọn ranh giới transaction và isolation phù hợp.

### 20.2. Isolation cao có thể yêu cầu retry

Ở `SERIALIZABLE`, database có thể hủy một transaction do xung đột đồng thời với mã như PostgreSQL `40001`. Ứng dụng thường phải **retry toàn bộ đơn vị công việc** từ đầu theo chính sách phù hợp, không chỉ chạy lại câu SQL cuối.

Retry cần giới hạn và idempotency khi có tác động ngoài DB; đừng retry vô hạn hoặc gửi email nhiều lần.

## 21. Transaction dài và trạng thái `idle in transaction`

Trong SQL editor, một người có thể chạy:

```sql
BEGIN;
SELECT * FROM some_table FOR UPDATE;
-- Rời máy mà chưa COMMIT/ROLLBACK.
```

Đây là một tình huống vận hành nguy hiểm. Connection vẫn có thể giữ transaction và lock trong lúc người dùng không làm gì.

### 21.1. Hậu quả có thể xảy ra

- Giao dịch khác phải **đợi lock**.
- Pool bị chiếm connection.
- Snapshot cũ giữ lại khiến PostgreSQL khó dọn phiên bản bản ghi đã hết dùng trong MVCC.
- Phiên bị bỏ quên lâu tạo rủi ro timeout, gián đoạn tác vụ và khó điều tra.

### 21.2. Kiểm tra từ PostgreSQL

Người có quyền quan sát phù hợp có thể dùng:

```sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

`state='idle in transaction'` có thể cho biết session đang rảnh nhưng chưa kết thúc transaction. Khả năng xem thông tin của phiên khác bị giới hạn bởi quyền quan sát của PostgreSQL.

### 21.3. Dùng timeout có chủ đích

Trong PostgreSQL:

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '15s';
-- Thực hiện câu SQL cần thiết.
ROLLBACK;
```

`SET LOCAL` áp dụng cho transaction hiện tại. Timeout có thể bảo vệ khỏi một số thao tác treo/đợi quá lâu, nhưng **không chứng minh SQL an toàn về nghiệp vụ**.

PostgreSQL còn có `idle_in_transaction_session_timeout` để xử lý session mở transaction rồi không hoạt động quá lâu. Cấu hình và giới hạn cần được chọn cùng đội vận hành, vì timeout quá ngắn có thể làm gián đoạn công việc hợp lệ.

### 21.4. Timeout không phải “commit tự động”

Khi một session bị ngắt do timeout/đóng kết nối trong lúc transaction chưa commit, những thay đổi dữ liệu chưa commit của transaction sẽ không được lưu như một commit thành công. Nhưng không dựa vào ngắt kết nối làm chiến lược rollback chủ động; cần xử lý kết thúc transaction rõ ràng và chẩn đoán các trường hợp mất kết nối tại thời điểm commit.

## 22. DDL, autocommit và khác biệt giữa DBMS

Không phải mọi hệ quản trị xử lý câu DDL (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`) giống nhau.

### 22.1. PostgreSQL có nhiều thao tác DDL mang tính giao dịch

Trong PostgreSQL, có thể thử với bảng tạm:

```sql
BEGIN;

CREATE TEMP TABLE txn_lab_rollback_ddl (
    id INTEGER PRIMARY KEY
);

INSERT INTO txn_lab_rollback_ddl (id) VALUES (1);

ROLLBACK;
```

Khi transaction bị rollback, cả việc tạo bảng tạm và chèn dòng trong transaction đều bị hoàn tác theo cơ chế PostgreSQL trong ví dụ.

Tuy nhiên, một số lệnh PostgreSQL **không được phép trong transaction block**, ví dụ `VACUUM` hoặc `CREATE INDEX CONCURRENTLY` theo quy tắc của chúng.

### 22.2. MySQL có implicit commit với nhiều DDL

Trong MySQL, nhiều lệnh DDL có thể gây **implicit commit** trước/sau thao tác theo quy tắc của hệ quản trị, khác với mô hình DDL giao dịch thường gặp của PostgreSQL.

Do đó, không được lấy kết luận:

```text
“CREATE TABLE được rollback trong PostgreSQL”
```

để tự suy ra:

```text
“Mọi CREATE/ALTER/DROP trên mọi database đều rollback được.”
```

Khi viết migration hoặc script chạy đa hệ, phải biết chính xác DBMS, engine, phiên bản, lệnh và ranh giới transaction được hỗ trợ.

### 22.3. Autocommit khác theo công cụ và hệ

| Hệ hoặc môi trường | Điều cần nhớ |
|---|---|
| PostgreSQL qua `psql` | Psql mặc định autocommit; `BEGIN` mở transaction tường minh; `\set AUTOCOMMIT` là lệnh client |
| PostgreSQL qua JDBC | Chế độ JDBC điều khiển qua `Connection`; framework/pool có thể quản lý |
| MySQL | Có biến `autocommit` ở session/server; DDL và engine có quy tắc riêng |
| SQL Server | Có cơ chế autocommit và implicit/explicit transactions, với cấu hình như `IMPLICIT_TRANSACTIONS` |
| Oracle Database | DML cần commit theo ranh giới session; nhiều DDL gây implicit commit; công cụ có thể hỗ trợ autocommit ở phía client |
| GUI client | Chế độ “Auto-commit” của giao diện và “Run script” là hành vi công cụ, cần kiểm tra cụ thể |

Chỉ khi biết môi trường cụ thể mới có thể nói **chắc chắn** một thao tác đã được commit lúc nào.

## 23. Những dấu hiệu giúp kiểm tra transaction đang được quản lý thế nào

Một số cách quan sát hữu ích:

### 23.1. Trong JDBC

```java
System.out.println(connection.getAutoCommit());
System.out.println(connection.getTransactionIsolation());
```

Hai giá trị này nói về **Connection cụ thể** ở thời điểm gọi. Chúng không chứng minh mọi repository trong ứng dụng dùng cùng connection đó.

Để điều tra thực tế, có thể thêm log đã kiểm soát:

```text
requestId=...
transactionBoundary=TransferService.transfer
connectionIdentifier=...  (không log thông tin bí mật)
autocommitAtEntry=...
rowsDebited=1
rowsCredited=1
commitOutcome=SUCCESS
```

Không log mật khẩu, chuỗi kết nối nhạy cảm, dữ liệu cá nhân hoặc statement với dữ liệu chưa được che theo quy định.

### 23.2. Trong PostgreSQL session

```sql
SELECT pg_backend_pid();
SHOW transaction_isolation;
```

`pg_backend_pid()` giúp quan sát backend session. `SHOW transaction_isolation` chỉ ra mức isolation, **không cho biết trực tiếp ai bấm commit**. Không dùng `txid_current()` như một phép kiểm tra autocommit vì gọi nó có thể làm phát sinh/đánh dấu transaction ID và không diễn tả quyền sở hữu transaction ở tầng ứng dụng.

### 23.3. Trạng thái nút Commit/Rollback ở SQL editor

Quan sát UI có thể hữu ích nhưng chưa đủ nếu:

- Công cụ dùng một kết nối khác để chạy một phần script.
- Script có `COMMIT` tường minh.
- Auto-commit được thay đổi trong lúc thực thi.
- Có reconnect sau timeout.

Một phép thử an toàn là **tạo/đổi một dòng trong bảng thử**, đọc trên cùng session, rollback và đọc lại; sau đó thử kịch bản tương đương ở đúng chế độ công cụ định dùng. Không thử nghiệm bằng dữ liệu production.

## 24. Khi một giao dịch có nhiều database hoặc dịch vụ

Transaction local trên một kết nối PostgreSQL **không tự bao gồm**:

- Một database PostgreSQL khác qua kết nối riêng.
- Một MySQL database.
- Một API thanh toán bên ngoài.
- Email, file hay HTTP callback.
- Một message đã gửi lên broker.

Ví dụ:

```text
Service chuyển tiền
    ├── UPDATE ledger trong PostgreSQL  → chưa commit
    ├── Gọi API đối tác                 → thành công ngoài DB
    └── ROLLBACK PostgreSQL            → API đối tác không tự hủy
```

### 24.1. Vì sao cần outbox?

Nếu sau khi cập nhật đơn hàng phải phát sự kiện, một mẫu phổ biến là:

```text
Transaction PostgreSQL
    ├── UPDATE orders
    └── INSERT outbox_events
    └── COMMIT

Worker tách biệt đọc outbox đã commit
    └── gửi message tới hệ thống khác
```

Trong transaction database, cập nhật đơn và ghi **ý định phát sự kiện** có thể commit cùng nhau. Sau commit, worker gửi event, xử lý retry và idempotency.

Outbox không làm message broker trở thành một phần của transaction local; nó giúp tránh tình huống ghi đơn thành công nhưng không có dấu vết đáng tin cậy để gửi event.

### 24.2. Saga và thao tác bù trừ

Với quy trình nhiều dịch vụ độc lập, một mô hình khác là **saga**: mỗi bước có transaction riêng, kèm các hành động **bù trừ** khi một bước sau thất bại.

```text
Đặt chỗ → Thanh toán → Gửi vé
            │
            └── Thất bại → có thể cần hủy đặt chỗ / hoàn tiền
```

Bù trừ không phải rollback SQL của một transaction duy nhất. Nó là **nghiệp vụ mới** với các lỗi, cạnh tranh và tính idempotent cần thiết kế riêng.

### 24.3. Distributed transaction là vấn đề khác

Một số hệ hỗ trợ giao dịch phân tán/2-phase commit trong giới hạn cụ thể. Nhưng không được mặc định transaction của Spring/JDBC local tự trải qua nhiều database và API ngoài. Đó là cơ chế điều phối đặc biệt, có yêu cầu hạ tầng và các rủi ro vận hành riêng.

## 25. Một lệnh thành công không có nghĩa cả công việc đã thành công

Trong SQL editor hoặc Java, có thể thấy một số tín hiệu “xanh”:

```text
UPDATE 1
INSERT 1
executeUpdate() returned 1
persist() returned
flush() returned
RETURNING yielded one row
```

Mỗi tín hiệu trên chỉ xác nhận **một phần** của tiến trình.

### 25.1. Phân biệt các mốc

| Mốc | Điều được chứng minh | Điều chưa được chứng minh |
|---|---|---|
| Statement chạy không lỗi | Câu SQL không báo lỗi tại thời điểm chạy | Đúng đối tượng, đúng số dòng, commit bền vững |
| `UPDATE 1` | Một dòng được tính là đã tác động | Dòng đó đúng ID hay giá trị thực có thay đổi |
| `RETURNING` một dòng | Dòng được câu lệnh tác động trực tiếp | Transaction đã commit; các bảng cascade không bị ảnh hưởng |
| `flush()` ORM | SQL có thể đã được đẩy xuống DB | Commit hoàn tất |
| `commit()` trả thành công | Transaction được database xác nhận commit theo giao thức | Hệ thống ngoài đã hoàn tất, hoặc replica đã đồng bộ |
| Đọc lại từ replica | Replica thấy một trạng thái | Chắc chắn đó là trạng thái mới nhất tại primary |

### 25.2. Khi kết nối mất đúng lúc commit

Giả sử:

```text
Ứng dụng gửi COMMIT
       ↓
Kết nối bị ngắt trước khi nhận phản hồi
```

Ứng dụng có thể không biết database đã nhận và hoàn tất commit hay chưa. Không nên kết luận chắc chắn **thành công** hoặc **thất bại** chỉ từ lỗi mạng.

Nếu thao tác có thể được gọi lại, dùng **idempotency key** hoặc mã yêu cầu duy nhất cùng khả năng đối soát trạng thái theo khóa đó. Điều này đặc biệt quan trọng với chuyển tiền, tạo đơn hàng, thanh toán và gửi thông báo.

## 26. Các lỗi thường gặp về quyền sở hữu transaction

| Hiểu nhầm hoặc cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| “Đã có `ROLLBACK` cuối file thì các lệnh trước sẽ hủy” | Các lệnh trước có thể đã autocommit | Mở transaction trước khi chạy, xác nhận công cụ |
| “Một file SQL = một transaction” | Script có thể chạy từng statement và commit riêng | Dùng `BEGIN`/cơ chế single-transaction phù hợp |
| “Mọi câu SQL trong một hàm Java là cùng transaction” | Repository lấy connection khác | Dùng một JDBC Connection hoặc transaction manager đúng cách |
| “Một request HTTP là một transaction” | HTTP và transaction DB có phạm vi khác | Đặt ranh giới tại service/data layer |
| “`setAutoCommit(false)` làm các connection khác cùng transaction” | Trạng thái thuộc Connection cụ thể | Đảm bảo các thao tác dùng cùng transaction context |
| “Tắt autocommit rồi không cần commit/rollback” | Transaction treo, giữ lock, thay đổi có thể bị hủy khi đóng | Kết thúc mọi đường chạy bằng commit/rollback |
| “`setAutoCommit(true)` chỉ dọn kết nối” | Có thể commit transaction đang mở | Commit/rollback trước, rồi phục hồi cấu hình theo hợp đồng |
| “`@Transactional` luôn hoạt động khi gọi `this.method()`” | Bỏ qua proxy trong cơ chế thông dụng | Đặt boundary tại lời gọi qua proxy/TransactionTemplate |
| “`@Transactional` rollback mọi checked exception” | Mặc định phổ biến không như vậy | Cấu hình rollback rule phù hợp |
| “Bắt lỗi rồi trả bình thường thì chắc chắn rollback” | Framework có thể commit nếu không đánh dấu rollback | Truyền lỗi hoặc mark rollback-only theo chính sách |
| “Repository tự commit cho chắc” | Commit phá transaction của service | Một thành phần sở hữu commit |
| “`REQUIRES_NEW` chỉ giống `NESTED`” | Inner commit có thể độc lập với outer | Chọn propagation theo ngữ nghĩa |
| “`flush()` nghĩa là dữ liệu đã commit” | ORM chỉ đẩy SQL, transaction vẫn mở | Chờ transaction manager xác nhận |
| “`RETURNING` nghĩa là dữ liệu đã lưu bền vững” | Transaction có thể rollback hoặc commit thất bại | Kiểm tra commit |
| “`UPDATE ... WHERE` trả 0 dòng là lỗi SQL” | 0 dòng thường là kết quả hợp lệ | Kiểm tra row count theo nghiệp vụ |
| “Lỗi trong `BEGIN` rồi chạy tiếp bình thường” | PostgreSQL transaction aborted, lỗi `25P02` | `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` |
| “SQL editor ở hai tab luôn có chung transaction” | Tab có thể khác connection | Kiểm tra session và mode |
| “Temp table dùng để kiểm chứng đọc giữa hai connection” | PostgreSQL TEMP chỉ trong một phiên | Dùng bảng thử dùng chung nếu cần |
| “Isolation cao hơn làm tất cả connection thành một transaction” | Isolation và transaction boundary khác nhau | Thiết kế đúng connection/context |
| “Đóng connection là cách rollback đảm bảo” | Driver/pool có quy tắc riêng | Gọi rollback chủ động trước close |
| “Transaction SQL tự rollback email đã gửi” | Tác động ngoài DB không thuộc transaction local | Outbox, idempotency, saga |
| “DDL trên mọi DB đều rollback được” | Nhiều DB có implicit commit với DDL | Kiểm tra DBMS và lệnh cụ thể |
| “Có kết quả xanh nghĩa là đủ bước nghiệp vụ” | Có thể thiếu bước, sai target hoặc chưa commit | Đối chiếu bất biến, row count và commit outcome |

## 27. Thực hành có hướng dẫn

Các ví dụ dưới đây chạy trên bảng `txn_lab_accounts` trong **một phiên PostgreSQL**. Vì một số tình huống cố ý commit hoặc gây lỗi, hãy mở **phiên thực hành mới** và tạo lại bảng khi muốn có trạng thái gốc.

### 27.1. Thí nghiệm A — thấy giá trị mới trước commit

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 70
WHERE account_id = 1
RETURNING account_id, balance;
-- 930.

SELECT balance
FROM txn_lab_accounts
WHERE account_id = 1;
-- 930 trên cùng transaction.

ROLLBACK;

SELECT balance
FROM txn_lab_accounts
WHERE account_id = 1;
-- 1000, nếu bắt đầu từ dữ liệu gốc.
```

Nhận xét: đọc thấy `930` bên trong transaction **không phải bằng chứng đã commit**.

### 27.2. Thí nghiệm B — commit trước rồi rollback sau

Trong **bảng TEMP thực hành**:

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 70
WHERE account_id = 1;

COMMIT;

ROLLBACK;  -- Không hoàn tác transaction đã commit.

SELECT balance
FROM txn_lab_accounts
WHERE account_id = 1;
-- 930.
```

Điều quan trọng: `ROLLBACK` chỉ áp dụng cho **transaction hiện đang mở**; commit trước đã kết thúc transaction.

### 27.3. Thí nghiệm C — lỗi SQL trong transaction

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 30
WHERE account_id = 1;

UPDATE txn_lab_accounts
SET balance = -1
WHERE account_id = 2;
-- Vi phạm CHECK.

SELECT * FROM txn_lab_accounts;
-- PostgreSQL có thể báo 25P02 vì transaction aborted.

ROLLBACK;
```

Lỗi đầu tiên là **ràng buộc**, lỗi `25P02` chỉ là hệ quả của transaction đã ở trạng thái failed.

### 27.4. Thí nghiệm D — savepoint và bước tùy chọn

```sql
BEGIN;

UPDATE txn_lab_accounts
SET version_no = version_no + 1
WHERE account_id = 1;

SAVEPOINT optional_job;

UPDATE txn_lab_accounts
SET balance = -1
WHERE account_id = 2;
-- CHECK failure.

ROLLBACK TO SAVEPOINT optional_job;

SELECT account_id, balance, version_no
FROM txn_lab_accounts
ORDER BY account_id;

ROLLBACK;
```

`SAVEPOINT` giúp khôi phục transaction để tiếp tục sau lỗi, nhưng **không làm transaction có thêm một commit riêng**.

### 27.5. Thí nghiệm E — `UPDATE 0` nhưng SQL không lỗi

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance + 100
WHERE account_id = 999
RETURNING account_id, balance;
-- 0 rows.

ROLLBACK;
```

Ứng dụng chuyển tiền phải coi **không tìm thấy tài khoản đích** là lỗi nghiệp vụ và hủy toàn transaction dù SQL không phát sinh ngoại lệ.

## 28. Bài tập tự luyện

Với mỗi bài, hãy xác định: **ai là chủ sở hữu transaction**, **bao nhiêu transaction được tạo**, **khi nào commit**, **có rollback được những thay đổi nào**, và **cần kiểm tra tín hiệu gì**. Những câu liên quan bảng thực hành giả định trạng thái ban đầu A=1000, B=500.

### Bài 1 — Autocommit có nghĩa là bỏ transaction?

Một SQL client bật autocommit. Người dùng thực thi:

```sql
UPDATE txn_lab_accounts
SET balance = balance - 100
WHERE account_id = 1;
```

Câu SQL có còn bảo đảm nguyên tử của statement không? Thời điểm nào câu lệnh được commit?

### Bài 2 — Hai câu độc lập

Autocommit đang bật. Câu 1 trừ 100 từ A thành công; câu 2 định cộng vào account 999 không có, trả 0 dòng. Tổng cuối là bao nhiêu? Tại sao một `ROLLBACK` gửi sau đó không tự sửa được?

### Bài 3 — Một transaction

Viết `BEGIN` cùng hai `UPDATE` chuyển 100 từ A sang B; kiểm tra mỗi câu trả đúng một dòng và tổng sau là 1500. Kết thúc bằng `ROLLBACK` để trả về trạng thái gốc.

### Bài 4 — Sự khác nhau giữa 0 dòng và SQL exception

So sánh:

```sql
UPDATE txn_lab_accounts SET balance = balance + 10
WHERE account_id = 999;
```

và:

```sql
UPDATE txn_lab_accounts SET balance = -1
WHERE account_id = 2;
```

Trên dữ liệu gốc, câu nào thường trả 0 dòng mà không lỗi? Câu nào vi phạm ràng buộc?

### Bài 5 — Sở hữu transaction

Một service Java lấy connection A để trừ tiền, repository khác lấy connection B để cộng tiền. Chỉ có A được `setAutoCommit(false)`. Nếu B đã autocommit, rollback A có hủy phần ghi của B không?

### Bài 6 — `setAutoCommit(true)`

Một đoạn JDBC gọi `setAutoCommit(false)`, cập nhật dữ liệu, rồi gọi `setAutoCommit(true)` mà không `commit()`/`rollback()` trước. Vì sao đây không phải cách “dọn dẹp” an toàn?

### Bài 7 — Editor ở manual mode

Một SQL editor đang tắt auto-commit. Người dùng chạy `UPDATE` rồi thấy 1 row affected. Người dùng cần xác nhận những gì trước khi bấm Commit? Nếu không muốn lưu thay đổi thì làm gì?

### Bài 8 — File SQL không phải transaction

Một file gồm ba câu `UPDATE`, câu thứ hai lỗi. Vì sao chỉ dùng nút “Run script” không chứng minh cả file được rollback? Nêu cách chạy `psql` giúp dừng khi lỗi và bọc file vào một transaction khi các lệnh đủ điều kiện.

### Bài 9 — `25P02`

Trong PostgreSQL:

```sql
BEGIN;
UPDATE txn_lab_accounts SET balance = -1 WHERE account_id = 2;
SELECT * FROM txn_lab_accounts;
```

Vì sao `SELECT` cũng có thể báo lỗi? Câu nào cần chạy tiếp nếu không có savepoint?

### Bài 10 — Savepoint

Một bước tùy chọn trong transaction bị lỗi. Viết đoạn SQL dùng `SAVEPOINT` và `ROLLBACK TO SAVEPOINT` để tiếp tục, rồi `ROLLBACK` cả transaction ở cuối. Những thay đổi trước savepoint có được commit riêng không?

### Bài 11 — JDBC row count

Trong Java, câu cập nhật tài khoản đích `executeUpdate()` trả `0`. Nếu quy trình cần chính xác một tài khoản đích, ứng dụng phải làm gì trước `commit()`?

### Bài 12 — `@Transactional` gọi nội bộ

Trong Spring, `handle()` gọi `this.saveWithTransaction()` trên cùng object; `saveWithTransaction()` có `@Transactional`. Vì sao transaction có thể không hoạt động theo kỳ vọng trong mô hình proxy?

### Bài 13 — Checked exception

Một service Spring `@Transactional` ném checked exception sau khi chèn bản ghi. Có thể mặc định chắc chắn transaction rollback không? Nêu một cách cấu hình rollback khi nghiệp vụ đòi all-or-nothing.

### Bài 14 — Bắt và nuốt lỗi

Service `@Transactional` tạo đơn thành công; giảm tồn kho phát sinh lỗi nghiệp vụ nhưng exception bị catch và chỉ ghi log. Điều gì có thể xảy ra nếu phương thức kết thúc bình thường?

### Bài 15 — `REQUIRES_NEW`

Service cha mở transaction, gọi service con `REQUIRES_NEW` ghi audit và commit, sau đó cha rollback. Bản ghi audit có nhất thiết rollback cùng cha không? Tại sao cần cân nhắc đây là chính sách nghiệp vụ?

### Bài 16 — `NESTED` và `REQUIRES_NEW`

Trong môi trường hỗ trợ nested bằng savepoint, hãy mô tả một khác biệt quan trọng giữa `NESTED` và `REQUIRES_NEW`.

### Bài 17 — `flush` trong ORM

`EntityManager.flush()` chạy không lỗi trong một transaction chưa commit. Có thể nói dữ liệu đã được lưu bền vững không? Nếu transaction rollback sau đó thì sao?

### Bài 18 — Đọc từ session khác

Session A cập nhật một bảng dùng chung trong transaction chưa commit. Session B ở `READ COMMITTED` đọc cùng dòng. B có thể thấy giá trị mới chưa commit không? Vì sao bảng TEMP của mục 4 không dùng trực tiếp để thử điều này với hai connection?

### Bài 19 — Transaction lâu

Một nhân viên mở `BEGIN; SELECT ... FOR UPDATE;` trong SQL editor rồi rời máy 30 phút. Nêu ba tác động có thể xảy ra và biện pháp giảm rủi ro.

### Bài 20 — Commit không chắc chắn

Ứng dụng gửi `COMMIT` nhưng mất kết nối trước khi nhận phản hồi. Có thể kết luận chắc chắn giao dịch chưa lưu không? Nên thiết kế retry như thế nào cho yêu cầu chuyển tiền?

### Bài 21 — Autocommit và DDL

Vì sao không nên suy ra “DDL có thể rollback trong PostgreSQL” đồng nghĩa `CREATE/ALTER/DROP` luôn rollback được trong MySQL hoặc các DBMS khác?

### Bài 22 — Tác động ngoài database

Một service cập nhật đơn hàng trong transaction rồi gửi email trước commit. Sau đó transaction rollback. Email có tự thu hồi không? Nêu một mẫu thiết kế cải thiện tính đáng tin cậy.

### Bài 23 — Ai điều phối repository?

Một Spring service gồm bước ghi đơn, ghi chi tiết, giảm tồn và ghi outbox. Nếu từng repository tự commit, khi bước ba lỗi sẽ có vấn đề gì? Đề xuất vị trí transaction boundary.

### Bài 24 — Kiểm chứng nhiều câu

Hãy xây dựng checklist tối thiểu cho một transfer JDBC: kiểm tra amount, source/destination, số dòng bị tác động, commit outcome, đóng connection và log/đối soát. Vì sao nhìn `executeUpdate() returned 1` của **chỉ một câu** không đủ?

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Có. Statement vẫn có tính nguyên tử về các thay đổi dữ liệu giao dịch. Khi autocommit bật và không có transaction tường minh chi phối, câu hoàn tất thành công được commit tự động theo cơ chế JDBC/client/database.

**Bài 2:** A=900, B=500, tổng=1400. Câu 1 đã commit riêng, câu 2 trả 0 dòng mà không có lỗi SQL. `ROLLBACK` sau khi commit không đảo ngược transaction đã kết thúc.

**Bài 3:**

```sql
BEGIN;

UPDATE txn_lab_accounts
SET balance = balance - 100
WHERE account_id = 1 AND balance >= 100
RETURNING account_id, balance;

UPDATE txn_lab_accounts
SET balance = balance + 100
WHERE account_id = 2
RETURNING account_id, balance;

SELECT SUM(balance) AS total_balance
FROM txn_lab_accounts;
-- 1500 nếu cả hai UPDATE đúng một dòng.

ROLLBACK;
```

Nếu một `UPDATE` trả 0 dòng, phải quyết định rollback toàn transaction thay vì commit.

**Bài 4:** `UPDATE ... account_id=999` trả 0 dòng, không tự là lỗi SQL. `UPDATE balance=-1` vi phạm `CHECK(balance>=0)`, thường có SQLSTATE `23514` ở PostgreSQL.

**Bài 5:** Không. B đã commit trên connection B thì rollback connection A không hủy phần đó. Hai kết nối local không tự chia sẻ transaction.

**Bài 6:** Theo hợp đồng JDBC, chuyển autocommit từ false sang true có thể **commit transaction hiện tại**. Muốn hủy phải gọi `rollback()` trước khi đổi chế độ/trả connection theo quy tắc quản lý phù hợp.

**Bài 7:** Kiểm tra connection, tập ID, row count, giá trị mới, các bảng liên quan, trạng thái transaction và mục tiêu nghiệp vụ. Nếu không đạt, `Rollback` trên đúng kết nối; không bấm Commit chỉ vì 1 row affected.

**Bài 8:** Công cụ có thể chạy các câu riêng với autocommit hoặc tiếp tục sau lỗi. Với `psql`, có thể dùng `psql -X -v ON_ERROR_STOP=1 -1 -f batch.sql` nếu các lệnh hỗ trợ chạy trong một transaction và script không có điều khiển transaction xung đột.

**Bài 9:** Câu `UPDATE` vi phạm CHECK làm transaction PostgreSQL aborted. `SELECT` tiếp theo có thể báo `25P02`. Không có savepoint thì chạy `ROLLBACK` để thoát và hủy transaction.

**Bài 10:**

```sql
BEGIN;
UPDATE txn_lab_accounts SET version_no = version_no + 1
WHERE account_id = 1;
SAVEPOINT optional_step;
UPDATE txn_lab_accounts SET balance = -1
WHERE account_id = 2;
-- Lỗi CHECK.
ROLLBACK TO SAVEPOINT optional_step;
ROLLBACK;
```

Thay đổi trước savepoint **chưa commit riêng**; rollback toàn transaction vẫn hủy nó.

**Bài 11:** Phát hiện không có tài khoản đích, ném lỗi nghiệp vụ hoặc chủ động rollback transaction **trước commit**. Không tin câu SQL không throw là thành công nghiệp vụ.

**Bài 12:** Lời gọi `this.method()` trên cùng object thường bỏ qua Spring proxy trong mô hình quản lý bằng proxy. Annotation không được interceptor áp dụng trên đường gọi này; cần gọi qua bean được quản lý hoặc dùng cơ chế transaction phù hợp.

**Bài 13:** Không. Chính sách Spring mặc định quen thuộc chỉ rollback với runtime exceptions/Error, không tự rollback mọi checked exception. Có thể dùng `@Transactional(rollbackFor = Exception.class)` nếu đúng nghiệp vụ, hoặc quy tắc rollback cụ thể hơn.

**Bài 14:** Nếu framework thấy phương thức kết thúc bình thường và transaction không bị đánh dấu rollback-only do nguyên nhân khác, nó có thể commit bước tạo đơn dù tồn kho chưa giảm. Cần truyền lỗi hoặc đánh dấu rollback theo chính sách.

**Bài 15:** Không nhất thiết. `REQUIRES_NEW` dùng transaction riêng; bước audit có thể đã commit độc lập khi cha rollback. Phải chọn cấu hình này chỉ khi chấp nhận tồn tại audit riêng với đơn hàng.

**Bài 16:** `NESTED` dùng savepoint trong transaction cha khi được hỗ trợ; rollback cha có thể hủy cả bước nested. `REQUIRES_NEW` là transaction riêng, có thể commit trước và độc lập với rollback cha.

**Bài 17:** Không. Flush thường đẩy SQL xuống DB nhưng chưa kết thúc transaction. Nếu rollback sau đó, các thay đổi dữ liệu giao dịch chưa commit bị hoàn tác.

**Bài 18:** Trong PostgreSQL `READ COMMITTED`, B không đọc thay đổi chưa commit của A; thường thấy phiên bản đã commit trước đó. Bảng `TEMP` thuộc riêng session tạo ra nên B không thấy cùng bảng, phải dùng bảng dùng chung trong môi trường thử.

**Bài 19:** Có thể giữ lock, chiếm pool connection, giữ snapshot cũ gây khó dọn MVCC và tạo timeout. Biện pháp: giữ transaction ngắn, hoàn tất commit/rollback, cấu hình timeout/giám sát `idle in transaction`, vận hành có kiểm soát.

**Bài 20:** Không. Commit có thể đã hoàn tất nhưng phản hồi bị mất. Dùng idempotency key, đối soát trạng thái theo operation ID và retry toàn đơn vị có kiểm soát; tránh tạo lần chuyển tiền thứ hai.

**Bài 21:** DBMS và loại DDL có quy tắc transaction khác nhau; MySQL có implicit commit cho nhiều câu DDL, còn PostgreSQL hỗ trợ giao dịch cho nhiều DDL nhưng không phải tất cả. Phải xem tài liệu đúng DBMS/phiên bản/lệnh.

**Bài 22:** Không. Email là tác động ngoài transaction database. Có thể ghi outbox event cùng transaction cập nhật đơn, rồi worker gửi email sau commit với retry/idempotency.

**Bài 23:** Các repository tự commit khiến bước đơn/chi tiết đã lưu dù tồn kho thất bại, gây dữ liệu nửa vời. Đặt transaction boundary tại service điều phối một lần đặt hàng và để repository tham gia transaction manager đó.

**Bài 24:** Kiểm tra amount dương và nguồn khác đích; dùng cùng Connection/transaction; trừ tiền với điều kiện đủ số dư, xác nhận 1 dòng; cộng tiền xác nhận 1 dòng; kiểm tra bất biến liên quan; ghi log/outbox theo yêu cầu; commit thành công; rollback mọi lỗi; trả connection sạch theo pool; có idempotency/đối soát khi mất kết nối. `executeUpdate()==1` của **một** câu không nói gì về thành công của các câu còn lại hoặc commit.

</details>

## 29. Checklist khi thiết kế hoặc vận hành một transaction

Trước khi sửa SQL hoặc cấu hình transaction, tự trả lời:

1. **Một đơn vị nghiệp vụ gồm những bước nào?** Câu SQL riêng, nhiều DML, nhiều repository hay nhiều dịch vụ?
2. **Ai sở hữu ranh giới transaction?** Người chạy SQL editor, JDBC caller, Spring transaction manager, JTA hay job framework?
3. **Connection nào tham gia?** Các statement có được ràng buộc vào **cùng transaction context** không?
4. **Autocommit thực tế là gì?** Đọc từ connection/client đang dùng, không chỉ suy từ mặc định lý thuyết.
5. **Transaction bắt đầu khi nào?** Có `BEGIN`, `setAutoCommit(false)`, `@Transactional` qua proxy hoặc cơ chế khác?
6. **Điều gì được coi là thất bại?** SQL exception, `UPDATE 0`, thiếu bước nghiệp vụ, lỗi ràng buộc ở commit?
7. **Ai thực hiện rollback?** Có đường xử lý tất cả exception, timeout và trường hợp 0 row không?
8. **Có gọi commit quá sớm không?** Repository/ORM/helper có commit trước khi service hoàn tất?
9. **Có side effect ngoài DB không?** Email/API/broker có cần outbox, saga hoặc bù trừ?
10. **Isolation và lock có phù hợp không?** Cần snapshot chung, chống ghi đè, hay xử lý retry?
11. **Transaction có quá dài không?** Có chờ UI/HTTP/file khiến session `idle in transaction`?
12. **Kết quả commit có được xác nhận không?** Nếu mất kết nối khi commit, có operation ID và cơ chế đối soát?

### 29.1. Sơ đồ quyết định ngắn

```text
Nhiều câu SQL cần cùng thành công?
                │
        ┌───────┴────────┐
        │                │
       KHÔNG             CÓ
        │                │
  Autocommit có thể   Chọn transaction owner
  đủ cho câu độc lập      │
                         ▼
                 Cùng một DB local?
                         │
                ┌────────┴─────────┐
                │                  │
               CÓ                 KHÔNG
                │                  │
        JDBC connection hoặc    Outbox / saga /
        framework transaction   điều phối phân tán
        manager                 theo thiết kế
                │
                ▼
       Check row count, invariant
                │
      ┌─────────┴─────────┐
      │                   │
     ĐẠT                 SAI/LỖI
      │                   │
   COMMIT              ROLLBACK
      │                   │
      ▼                   ▼
  Xác nhận commit     Báo lỗi, xử lý retry
  và audit            theo nguyên nhân
```

## 30. Tổng kết

**Autocommit** không phải việc “SQL có giao dịch hay không”; nó là việc **ranh giới commit** được đặt tự động quanh từng câu lệnh hay được một chủ thể quản lý cho cả nhóm câu lệnh.

**Quyền sở hữu transaction** là câu hỏi quan trọng nhất khi chuyển từ SQL đơn lẻ sang ứng dụng thật:

- Trong **SQL editor**, chế độ chạy statement/script và nút Commit/Rollback quyết định phạm vi thao tác.
- Trong **JDBC thuần**, `Connection` cụ thể và mã gọi chịu trách nhiệm `setAutoCommit`, `commit`, `rollback`.
- Trong **Spring/ORM**, transaction manager đã cấu hình thường là chủ sở hữu; repository không nên tự commit trái ranh giới service.
- Với **nhiều connection hoặc dịch vụ ngoài**, một local transaction không tự bao trùm tất cả.

**Ba quy tắc cần nhớ:**

1. **Một file, một hàm Java hay một request HTTP không tự động là một transaction.** Hãy xác định ranh giới và connection thật.
2. **Chỉ một thành phần được giao trách nhiệm quyết định commit/rollback cho một đơn vị công việc**, và phải xử lý cả lỗi SQL lẫn thất bại nghiệp vụ như `UPDATE 0`.
3. **Không công bố thành công chỉ vì statement chạy xong.** Hãy xác minh đúng các bước bắt buộc, số dòng, trạng thái transaction và kết quả commit.

Hiểu được ba quy tắc đó, bạn sẽ tránh được tình huống “tưởng đã rollback nhưng dữ liệu vẫn còn”, “tưởng đã commit nhưng dữ liệu biến mất” và “một service có nhiều câu SQL nhưng chỉ một phần được lưu” — đồng thời thiết kế được giao dịch SQL rõ ràng, có thể kiểm chứng và phục hồi.
