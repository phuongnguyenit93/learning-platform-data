# Ngăn thao tác nhầm toàn bảng và kiểm chứng sau thay đổi

Một trong những lỗi SQL gây hậu quả nghiêm trọng nhất không phải là cú pháp sai mà là **câu lệnh hợp lệ nhưng tác động đến quá nhiều dòng**. Chỉ cần quên `WHERE`, dùng điều kiện quá rộng, nhầm phạm vi khách hàng hoặc nối sai bảng nguồn, một thao tác dự kiến sửa **một bản ghi** có thể sửa **hàng nghìn bản ghi**. Khi `DELETE` xuất hiện trong hệ thống có khóa ngoại và cơ chế xóa dây chuyền, số dòng bị mất có thể còn lớn hơn số dòng hiển thị trong thông báo của câu lệnh.

Trong chương **Cập nhật và xóa** của **Database SQL**, bài học này tập trung vào hai câu hỏi thực tế:

1. **Ngăn thao tác nhầm toàn bảng như thế nào?** Không chỉ nhắc “nhớ `WHERE`”, mà còn thiết kế khóa định danh, điều kiện phạm vi, đếm dòng, transaction, phân quyền và các bước kiểm soát.
2. **Kiểm chứng sau thay đổi như thế nào?** Không chỉ thấy SQL chạy xong, mà phải biết **dòng nào đổi**, **bao nhiêu dòng đổi**, **giá trị mới có đúng không**, **các bảng liên quan bị ảnh hưởng thế nào** và **giao dịch đã commit thành công chưa**.

Các ví dụ chính dùng **PostgreSQL** và bảng **tạm** để có thể thử `UPDATE`, `DELETE` rồi `ROLLBACK` mà không ảnh hưởng dữ liệu thật. Những lưu ý riêng cho MySQL, SQL Server và các môi trường khác được tách rõ khi cần.

> **Nguyên tắc cốt lõi:** Một câu lệnh chạy thành công chỉ chứng minh database đã chấp nhận thao tác theo các điều kiện được viết. Nó **không chứng minh điều kiện đó chính là ý định của bạn**.

## 1. Vì sao `UPDATE` và `DELETE` nguy hiểm hơn `SELECT`?

`SELECT` thường chỉ đọc dữ liệu. `UPDATE` thay đổi giá trị đang lưu; `DELETE` loại dòng khỏi bảng theo quy tắc giao dịch và ràng buộc. Một sai sót có thể tác động ngay đến báo cáo, API, giao dịch khác hoặc quy trình nghiệp vụ.

Ví dụ, ý định chỉ **vô hiệu hóa một tài khoản**:

```sql
UPDATE accounts
SET status = 'SUSPENDED'
WHERE account_id = 103;
```

Nếu viết nhầm:

```sql
-- NGUY HIỂM: minh họa lỗi, KHÔNG chạy trên bảng thật.
UPDATE accounts
SET status = 'SUSPENDED';
```

thì câu lệnh có thể đổi trạng thái của **mọi dòng** mà tài khoản kết nối được phép cập nhật.

Tương tự:

```sql
-- NGUY HIỂM: minh họa lỗi, KHÔNG chạy trên bảng thật.
DELETE FROM accounts;
```

có thể xóa **mọi dòng** trong bảng, chịu các quy tắc khóa ngoại/trigger liên quan.

### 1.1. Có `WHERE` vẫn chưa chắc an toàn

Những điều kiện sau có thể quá rộng:

```sql
-- Cùng ý nghĩa như không có WHERE, với mọi dòng:
UPDATE accounts SET status = 'SUSPENDED' WHERE 1 = 1;

-- Có WHERE nhưng có thể chọn đa số tài khoản:
DELETE FROM accounts WHERE status <> 'CLOSED';

-- Chỉ định tenant nhưng vẫn có thể xóa cả tenant:
DELETE FROM accounts WHERE tenant_id = 10;
```

`WHERE` là công cụ **chọn tập dòng đích**, không phải lá chắn tự động chống sai sót. Cần biết điều kiện phải chọn **chính xác bao nhiêu dòng và những khóa nào**.

### 1.2. Rủi ro do thao tác nhầm được phân loại

| Lỗi | Ví dụ | Hậu quả |
|---|---|---|
| Quên điều kiện | `UPDATE ... SET ...` không `WHERE` | Cập nhật toàn bảng |
| Điều kiện quá rộng | `WHERE tenant_id = 10` thay vì thêm `account_id` | Sửa toàn bộ một khách hàng/tổ chức |
| Điều kiện sai giá trị | Chọn `status='ACTIVE'` thay vì `'SUSPENDED'` | Sửa sai nhóm nghiệp vụ |
| Bỏ điều kiện bảo vệ | Không có `deleted_at IS NULL` hoặc `version_no` | Sửa cả dữ liệu đã vô hiệu hoặc bị thay đổi đồng thời |
| `NULL` bị hiểu sai | `WHERE deleted_at = NULL` | Không chọn được dòng như dự kiến |
| Sai bảng nguồn khi nối | `UPDATE ... FROM` thiếu điều kiện join | Sửa nhầm nhiều dòng |
| Xóa dây chuyền | FK `ON DELETE CASCADE` | Xóa thêm dòng ở bảng con |
| Sai biên thời gian | `BETWEEN` hoặc thời điểm không rõ múi giờ | Chọn sai kỳ dữ liệu |
| Tự động commit | Mỗi câu SQL được lưu ngay | Khó hoàn tác bằng `ROLLBACK` sau khi commit |

Các tình huống này cần **nhiều lớp kiểm soát** thay vì phụ thuộc một mẹo duy nhất.

## 2. Dữ liệu thực hành: tài khoản và hóa đơn

Ta mô phỏng hệ thống đa khách hàng (*multi-tenant*): mỗi tài khoản thuộc một `tenant_id`, có trạng thái, hạn mức, số phiên bản và thời điểm vô hiệu hóa mềm. Hóa đơn liên kết với tài khoản.

### 2.1. Tạo bảng tạm trong PostgreSQL

Chạy trên **database thực hành**, trong một phiên SQL riêng:

```sql
CREATE TEMP TABLE safe_dml_accounts (
    account_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    account_name TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    credit_limit NUMERIC(12, 2) NOT NULL
        CHECK (credit_limit >= 0),
    version_no INTEGER NOT NULL DEFAULT 1
        CHECK (version_no >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE TEMP TABLE safe_dml_invoices (
    invoice_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL
        REFERENCES safe_dml_accounts(account_id)
        ON DELETE CASCADE,
    invoice_status TEXT NOT NULL
        CHECK (invoice_status IN ('OPEN', 'PAID', 'VOID')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0)
);

INSERT INTO safe_dml_accounts
    (account_id, tenant_id, account_name, status, credit_limit)
VALUES
    (101, 10, 'An Store',   'ACTIVE',    1000),
    (102, 10, 'Binh Shop',  'ACTIVE',    1500),
    (103, 10, 'Chi Trade',  'SUSPENDED',  500),
    (104, 10, 'Dung Lab',   'ACTIVE',     900),
    (201, 20, 'Mai Shop',   'ACTIVE',    2000),
    (202, 20, 'Nam Market','SUSPENDED',  800);

INSERT INTO safe_dml_invoices
    (invoice_id, account_id, invoice_status, amount)
VALUES
    (1001, 101, 'OPEN', 100),
    (1002, 101, 'PAID', 200),
    (1003, 102, 'OPEN', 300),
    (1004, 103, 'VOID',  50),
    (2001, 201, 'OPEN',1000),
    (2002, 202, 'PAID',  80);

SELECT account_id, tenant_id, account_name,
       status, credit_limit, version_no, deleted_at
FROM safe_dml_accounts
ORDER BY account_id;
```

Kết quả tài khoản ban đầu:

| account_id | tenant_id | account_name | status | credit_limit | version_no |
|---:|---:|---|---|---:|---:|
| 101 | 10 | An Store | ACTIVE | 1000 | 1 |
| 102 | 10 | Binh Shop | ACTIVE | 1500 | 1 |
| 103 | 10 | Chi Trade | SUSPENDED | 500 | 1 |
| 104 | 10 | Dung Lab | ACTIVE | 900 | 1 |
| 201 | 20 | Mai Shop | ACTIVE | 2000 | 1 |
| 202 | 20 | Nam Market | SUSPENDED | 800 | 1 |

Mọi `deleted_at` ban đầu đều `NULL`. Bảng có **6 tài khoản**, trong đó `tenant_id=10` có **4 tài khoản**, `tenant_id=20` có **2 tài khoản**.

Bảng hóa đơn:

| invoice_id | account_id | invoice_status | amount |
|---:|---:|---|---:|
| 1001 | 101 | OPEN | 100 |
| 1002 | 101 | PAID | 200 |
| 1003 | 102 | OPEN | 300 |
| 1004 | 103 | VOID | 50 |
| 2001 | 201 | OPEN | 1000 |
| 2002 | 202 | PAID | 80 |

**Vì sao có `ON DELETE CASCADE`?** Để minh họa rằng `DELETE` một tài khoản có thể xóa **cả hóa đơn liên quan** theo ràng buộc, ngay cả khi câu `DELETE ... RETURNING` chỉ cho thấy tài khoản đã bị xóa. Hệ thống nghiệp vụ thật thường cần chính sách lưu trữ hóa đơn nghiêm ngặt hơn; không suy ra `CASCADE` là lựa chọn mặc định tốt cho dữ liệu tài chính.

### 2.2. Cách sử dụng các ví dụ an toàn

- Những câu `UPDATE`/`DELETE` **minh họa rủi ro** được ghi `KHÔNG CHẠY`.
- Các bài thực hành có thay đổi dữ liệu thường được bọc `BEGIN ... ROLLBACK`; chỉ dùng `COMMIT` khi thực sự muốn giữ thay đổi của ví dụ.
- Nếu đã chạy ví dụ có `COMMIT`, hoặc câu DML ngoài transaction ở chế độ autocommit, bộ dữ liệu sẽ không còn ở trạng thái ban đầu. Có thể mở **phiên mới** để tạo lại bảng tạm.
- Nếu câu SQL lỗi trong transaction tường minh PostgreSQL, transaction thường chuyển sang trạng thái lỗi; cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` hợp lệ trước khi tiếp tục.
- Không sao chép SQL từ bài sang môi trường production chỉ bằng cách đổi tên bảng; mỗi hệ thống cần xác nhận schema, quyền, điều kiện, snapshot và quy trình vận hành riêng.

## 3. Biến ý định nghiệp vụ thành “tập đích”

Trước khi viết `UPDATE` hoặc `DELETE`, hãy phát biểu **tập bản ghi được phép thay đổi** bằng từ ngữ dễ kiểm chứng.

Ví dụ yêu cầu:

> “Đóng tài khoản 103 thuộc tenant 10, **chỉ khi tài khoản đó đang bị tạm ngưng và chưa xóa mềm**.”

Tập đích là:

```sql
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL
```

Ý nghĩa từng điều kiện:

| Điều kiện | Vai trò |
|---|---|
| `account_id = 103` | Chọn đúng định danh |
| `tenant_id = 10` | Kiểm soát phạm vi tenant |
| `status = 'SUSPENDED'` | Chỉ cho phép chuyển trạng thái từ trạng thái được chấp thuận |
| `deleted_at IS NULL` | Không tác động vào dòng đã xóa mềm |

Từ đó tạo **truy vấn xem trước**:

```sql
SELECT
    account_id, tenant_id, account_name, status,
    credit_limit, version_no, deleted_at
FROM safe_dml_accounts
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL;
```

Kết quả mong đợi là **một dòng**, ID 103.

### 3.1. Kiểm tra số dòng kỳ vọng

Nếu yêu cầu là sửa **đúng một tài khoản**, hãy kiểm tra:

```sql
SELECT COUNT(*) AS candidate_count
FROM safe_dml_accounts
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL;
-- 1 trên dữ liệu ban đầu.
```

Một điều kiện xấu có thể trả:

- **0 dòng**: sai ID, sai tenant, trạng thái đã đổi, hoặc dữ liệu đã được xử lý trước.
- **1 dòng**: phù hợp mục tiêu một bản ghi nếu khóa và các trường đã được xác minh.
- **Nhiều dòng**: đáng nghi ngờ nếu yêu cầu chỉ sửa một bản ghi.

**Không mặc định 0 dòng là thành công.** Với lệnh “đóng chính xác tài khoản 103”, 0 dòng có thể là dấu hiệu thao tác đã bị cạnh tranh hoặc request sai.

### 3.2. Chọn khóa ổn định, không chọn tên gần đúng

Không nên dùng:

```sql
-- Có thể chọn nhiều tên chứa "Shop".
UPDATE safe_dml_accounts
SET status = 'CLOSED'
WHERE account_name ILIKE '%Shop%';
```

Điều kiện theo tên hiển thị có thể trùng, đổi theo thời gian hoặc bị ảnh hưởng bởi collation. Với thao tác nhắm một thực thể, ưu tiên **khóa chính hoặc khóa nghiệp vụ có ràng buộc duy nhất**, cộng điều kiện tenant/phiên bản/trạng thái cần thiết.

### 3.3. Khóa ID duy nhất không thay thế kiểm tra phạm vi

Trong bảng mẫu, `account_id` là khóa chính toàn bảng, nên ID 103 không thể trùng ở tenant khác. Tuy vậy, thêm `tenant_id = 10` vẫn có giá trị:

1. Thể hiện **phạm vi yêu cầu** ngay trong SQL.
2. Giúp phát hiện request có tenant sai: kết quả 0 dòng thay vì âm thầm sửa tài khoản ngoài phạm vi.
3. Giảm rủi ro khi schema thực tế dùng khóa **tổng hợp** `(tenant_id, account_id)` hoặc khóa ID chỉ duy nhất trong tenant.

Không nên dùng `tenant_id` lấy trực tiếp từ dữ liệu do client gửi mà không xác thực với quyền truy cập của người dùng.

## 4. Quy tắc an toàn đầu tiên: xem trước bằng `SELECT`

Một quy trình cơ bản có thể nhớ là:

```text
Xác định yêu cầu
      ↓
SELECT cùng điều kiện WHERE
      ↓
Xem khóa và giá trị hiện tại
      ↓
COUNT số dòng và so với mức kỳ vọng
      ↓
UPDATE / DELETE trong transaction
      ↓
RETURNING, kiểm tra lại và đối chiếu
      ↓
COMMIT hoặc ROLLBACK
```

Ví dụ muốn giảm hạn mức của tài khoản 102 từ 1500 xuống 1400:

```sql
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102
  AND tenant_id = 10
  AND status = 'ACTIVE'
  AND deleted_at IS NULL;
```

Nhận kết quả `credit_limit=1500` và `version_no=1`. Sau đó mới xây dựng câu `UPDATE` theo điều kiện tương ứng.

### 4.1. Kiểm tra bằng `SELECT *` có đủ không?

`SELECT *` thuận tiện lúc khám phá schema, nhưng khi phê duyệt thao tác, nên hiển thị **những cột quyết định**:

```sql
SELECT account_id, tenant_id, status, credit_limit, version_no
...
```

Danh sách cột tường minh giúp người thực hiện kiểm tra **đúng trạng thái trước**, **đúng giá trị cũ**, **đúng đối tượng**. Với dữ liệu nhạy cảm, không nên xuất tràn lan tất cả cột ra log.

### 4.2. `SELECT` trước không bảo đảm dữ liệu không đổi

Giữa thời điểm `SELECT` và `UPDATE`, giao dịch khác có thể:

- Đổi trạng thái từ `ACTIVE` sang `CLOSED`.
- Cập nhật hạn mức.
- Xóa mềm tài khoản.
- Chuyển bản ghi sang một trạng thái mà thao tác không còn hợp lệ.

Vì vậy, **xem trước là lớp kiểm tra**, không phải bằng chứng tuyệt đối rằng đến lúc ghi dữ liệu vẫn như cũ. Muốn an toàn hơn cần điều kiện **trạng thái/phiên bản ở chính lệnh DML**, khóa dòng, và kiểm tra số dòng thực sự đã thay đổi.

## 5. Thao tác an toàn trong transaction

Transaction giúp **chưa công bố thay đổi bền vững** cho tới khi quyết định `COMMIT`, đồng thời có đường `ROLLBACK` nếu kiểm tra không đạt.

### 5.1. Mẫu `UPDATE` có kiểm tra trước và sau

```sql
BEGIN;

-- Xem và khóa đúng dòng đích hiện có.
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102
  AND tenant_id = 10
  AND status = 'ACTIVE'
  AND deleted_at IS NULL
FOR UPDATE;

-- Chỉ cập nhật khi khóa, tenant, trạng thái và phiên bản đúng.
UPDATE safe_dml_accounts
SET credit_limit = 1400,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = 102
  AND tenant_id = 10
  AND status = 'ACTIVE'
  AND deleted_at IS NULL
  AND version_no = 1
RETURNING account_id, tenant_id, status, credit_limit, version_no;

-- Đọc lại trong cùng transaction.
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102;

-- Trong buổi thực hành, hủy thử nghiệm:
ROLLBACK;
```

`RETURNING` của câu `UPDATE` phải trả đúng **một dòng**: ID 102, hạn mức 1400, phiên bản 2. `SELECT` sau đó trong transaction phải thấy các giá trị mới. Sau `ROLLBACK`, trạng thái bảng tạm trở lại giá trị ban đầu (hạn mức 1500, phiên bản 1), miễn là không có thay đổi khác được commit trước đó.

### 5.2. Tại sao `FOR UPDATE`?

Trong PostgreSQL, `SELECT ... FOR UPDATE` khóa các **dòng được chọn** để ngăn giao dịch khác thực hiện một số thay đổi xung đột trên các dòng đó trước khi transaction hiện tại kết thúc.

Tuy nhiên:

- Khóa các dòng đã tìm thấy **không tự khóa mọi dòng tương lai** có thể khớp cùng điều kiện.
- Khả năng khóa, mức cô lập và hành vi đợi/timeout khác nhau giữa các hệ quản trị.
- `FOR UPDATE` không chứng minh người dùng có quyền nghiệp vụ đối với dòng đó; kiểm tra phân quyền vẫn bắt buộc.
- Giữ transaction quá lâu có thể gây đợi khóa và ảnh hưởng hiệu năng.

Với lệnh nhắm **khóa chính cụ thể**, khóa dòng kết hợp kiểm tra phiên bản là một mẫu tương đối dễ hiểu. Với lệnh thay đổi **hàng loạt theo predicate**, còn phải xét *phantom rows* và cơ chế nắm danh sách ID đích.

### 5.3. `COMMIT` và `ROLLBACK` là hai quyết định khác nhau

Trong bài này, `ROLLBACK` là lựa chọn mặc định để thực hành mà không để lại sửa đổi. Trong vận hành thật, nếu:

1. Số dòng thực thay đổi đúng kỳ vọng.
2. Giá trị mới và các bất biến đều được xác minh.
3. Những dòng liên quan đúng như kế hoạch.
4. Không có lỗi transaction hoặc điều kiện phê duyệt còn thiếu.

thì mới cho phép **`COMMIT`**. Nếu bất kỳ kiểm tra nào không đạt, **`ROLLBACK`** và điều tra.

**Sau khi commit thành công, `ROLLBACK` không thể đảo ngược transaction đã commit.** Muốn sửa hậu quả phải dùng thao tác bù, dữ liệu lịch sử, bản sao lưu/khôi phục có kiểm soát hoặc cơ chế phục hồi phù hợp.

## 6. `RETURNING`: biết đúng dòng nào được sửa hoặc xóa

PostgreSQL có mệnh đề **`RETURNING`** để trả thông tin của những dòng bị tác động trực tiếp bởi `INSERT`, `UPDATE`, `DELETE`.

Ví dụ:

```sql
BEGIN;

UPDATE safe_dml_accounts
SET status = 'CLOSED',
    updated_at = CURRENT_TIMESTAMP,
    version_no = version_no + 1
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL
RETURNING account_id, tenant_id, account_name,
          status, credit_limit, version_no;

ROLLBACK;
```

Trên dữ liệu gốc, `RETURNING` cho đúng **một dòng** account 103, `status='CLOSED'`, `version_no=2`. Nếu câu lệnh trả **0 dòng**, một điều kiện không còn khớp hoặc dòng không tồn tại.

### 6.1. Giá trị `RETURNING` trong `UPDATE` và `DELETE`

Với PostgreSQL:

- `UPDATE ... RETURNING` thường trả giá trị **dòng sau khi được cập nhật**.
- `DELETE ... RETURNING` trả giá trị **dòng bị xóa**.

Ví dụ xóa đúng account 104 (trong transaction thử nghiệm):

```sql
BEGIN;

DELETE FROM safe_dml_accounts
WHERE account_id = 104
  AND tenant_id = 10
RETURNING account_id, tenant_id, account_name, status;

ROLLBACK;
```

Kết quả trả một dòng mang ID 104, giúp đối chiếu chính xác đối tượng bị xóa. Không nên chỉ tin thông báo kiểu “DELETE 1” nếu ID thực tế không đúng mục tiêu.

### 6.2. `RETURNING` không tự chứng minh giao dịch đã commit

Trong một transaction:

```sql
BEGIN;
UPDATE ... RETURNING ...;
ROLLBACK;
```

`RETURNING` có thể trả giá trị mới **trong transaction**, nhưng sau `ROLLBACK`, thay đổi không được lưu. Để kết luận “thay đổi đã có hiệu lực bền vững”, phải xác nhận **`COMMIT` thành công** và khi cần, kiểm tra lại từ một lần đọc độc lập sau commit.

### 6.3. Dòng do cascade hoặc trigger có thể không nằm trong danh sách chính

`DELETE FROM safe_dml_accounts ... RETURNING ...` cho biết các **tài khoản bị xóa trực tiếp bởi câu lệnh**. Nếu khóa ngoại `ON DELETE CASCADE` xóa cả hóa đơn ở bảng con, những dòng hóa đơn đó **không tự xuất hiện** trong `RETURNING` của câu `DELETE` tài khoản.

Vì vậy, số dòng `RETURNING` không phải tổng số dòng bị ảnh hưởng **trên mọi bảng**. Phải kiểm tra quan hệ liên quan trước và sau.

## 7. Quy trình xóa thử có kiểm chứng dữ liệu liên quan

Giả sử cần xóa vật lý tài khoản 101 ở tenant 10, nhưng bảng `safe_dml_invoices` có khóa ngoại **`ON DELETE CASCADE`**. Trong dữ liệu mẫu, account 101 có **2 hóa đơn**.

### 7.1. Kiểm tra trước khi xóa

```sql
SELECT
    a.account_id,
    a.tenant_id,
    a.account_name,
    COUNT(i.invoice_id) AS invoice_count
FROM safe_dml_accounts AS a
LEFT JOIN safe_dml_invoices AS i
    ON i.account_id = a.account_id
WHERE a.account_id = 101
  AND a.tenant_id = 10
GROUP BY a.account_id, a.tenant_id, a.account_name;
-- account 101 có 2 hóa đơn.
```

Nếu nghiệp vụ **không cho phép xóa tài khoản có hóa đơn**, câu trả lời đúng là **không thực hiện `DELETE`** chỉ vì SQL có thể cascade. Phải chọn chính sách khác như vô hiệu hóa/ẩn tài khoản, hoặc điều chỉnh schema/luồng nghiệp vụ theo phê duyệt.

### 7.2. Minh họa tác động cascade trong transaction thử

```sql
BEGIN;

SELECT invoice_id, account_id, invoice_status, amount
FROM safe_dml_invoices
WHERE account_id = 101
ORDER BY invoice_id;
-- 2 dòng: invoice 1001 và 1002.

DELETE FROM safe_dml_accounts
WHERE account_id = 101
  AND tenant_id = 10
RETURNING account_id, tenant_id, account_name;
-- 1 dòng tài khoản 101.

SELECT COUNT(*) AS remaining_invoices
FROM safe_dml_invoices
WHERE account_id = 101;
-- 0 trong transaction do ON DELETE CASCADE.

SELECT COUNT(*) AS remaining_accounts
FROM safe_dml_accounts
WHERE account_id = 101;
-- 0 trong transaction.

ROLLBACK;
```

Sau `ROLLBACK`, cả tài khoản 101 và hóa đơn 1001, 1002 trở lại trạng thái ban đầu của phiên thử (nếu không có thay đổi được commit xen kẽ từ bước khác).

### 7.3. Vì sao `DELETE 1` không đủ?

Thông báo chỉ báo số dòng bị xóa trực tiếp trong bảng `safe_dml_accounts`. Hậu quả thực tế trên dữ liệu:

```text
DELETE tài khoản 101
         │
         ├── tài khoản 101: 1 dòng
         │
         └── FK CASCADE tới safe_dml_invoices
                  ├── hóa đơn 1001
                  └── hóa đơn 1002
```

Đó là ít nhất **ba dòng trực tiếp và dây chuyền trên hai bảng** trong ví dụ. Trên schema thật, còn có thể có nhiều lớp tham chiếu, trigger hoặc quy trình đồng bộ. Cần kiểm tra **sơ đồ quan hệ và quy tắc FK trước khi xóa vật lý**.

## 8. Đếm trước, đếm sau và đối chiếu bất biến

Một phép kiểm chứng tốt không chỉ hỏi “số dòng đổi bao nhiêu?” mà phải kiểm tra **những bất biến phải đúng sau thao tác**.

Ví dụ sau khi đổi trạng thái account 103 từ `SUSPENDED` sang `CLOSED`:

- Account 103 **vẫn tồn tại**, không bị xóa.
- Trạng thái chuyển thành `CLOSED`.
- `version_no` tăng từ 1 lên 2.
- `credit_limit` **không bị sửa**.
- Các tài khoản 101, 102, 104, 201, 202 **không đổi**.
- Hóa đơn không bị xóa bởi `UPDATE status` (trong schema mẫu không có trigger thực hiện việc đó).

### 8.1. Đếm theo trạng thái trước và sau

```sql
SELECT tenant_id, status, COUNT(*) AS account_count
FROM safe_dml_accounts
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Trên dữ liệu gốc:

| tenant | trạng thái | số tài khoản |
|---:|---|---:|
| 10 | ACTIVE | 3 |
| 10 | SUSPENDED | 1 |
| 20 | ACTIVE | 1 |
| 20 | SUSPENDED | 1 |

Nếu account 103 được đóng thành công, kỳ vọng sau cập nhật:

| tenant | trạng thái | số tài khoản |
|---:|---|---:|
| 10 | ACTIVE | 3 |
| 10 | CLOSED | 1 |
| 20 | ACTIVE | 1 |
| 20 | SUSPENDED | 1 |

**Chỉ số tổng** vẫn là 6 tài khoản; thay đổi là **dịch một dòng giữa hai trạng thái** của tenant 10. Nếu tổng giảm, có thể có hành vi xóa khác ngoài kỳ vọng.

### 8.2. Kiểm chứng theo khóa đích và khóa không được tác động

Sau một `UPDATE` lớn, ngoài `COUNT`, nên đối chiếu:

```sql
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id IN (101, 102, 103, 104, 201, 202)
ORDER BY account_id;
```

`COUNT=1` vẫn có thể là **một dòng sai**. Danh sách ID bị tác động (`RETURNING`/audit) và trạng thái trước–sau sẽ giúp nhận diện tình huống đó.

### 8.3. Kiểm tra điều kiện phủ định

Nếu chỉ muốn đổi account 103 của tenant 10, có thể kiểm tra **tenant 20 không đổi**. Trong hệ thống thực, nên lưu snapshot hoặc dấu vết thay đổi trước thao tác, vì chỉ nhìn dữ liệu sau không đủ chứng minh không có trường khác bị sửa.

```sql
SELECT account_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE tenant_id = 20
ORDER BY account_id;
```

Với dữ liệu mẫu, account 201 và 202 phải giữ nguyên khi chỉ cập nhật account 103.

## 9. Hạn mức dòng: số dòng thực thay đổi phải đúng kỳ vọng

Một thao tác nhắm một tài khoản nên có điều kiện **`affected_rows = 1`**. Một tác vụ hàng loạt có thể có điều kiện **`1 <= affected_rows <= 50`** theo kế hoạch được phê duyệt.

### 9.1. Số dòng do SQL client báo

Sau câu:

```sql
UPDATE safe_dml_accounts
SET credit_limit = 1400
WHERE account_id = 102
  AND tenant_id = 10;
```

PostgreSQL thường báo trạng thái tương tự `UPDATE 1`. Điều đó cho biết **số dòng được cập nhật bởi câu lệnh**.

Tuy nhiên:

- Một dòng có thể được **tác động** dù giá trị gán bằng giá trị hiện có; không tự suy ra mỗi dòng có thay đổi giá trị thực tế khác trước.
- Số dòng không cho biết **đúng ID** hay **đúng giá trị**.
- `UPDATE 0` có thể do không có bản ghi, xung đột trạng thái, điều kiện phiên bản sai hoặc mục tiêu đã thay đổi.

### 9.2. Đếm `RETURNING` trong cùng câu lệnh

PostgreSQL hỗ trợ data-modifying CTE:

```sql
BEGIN;

WITH changed AS (
    UPDATE safe_dml_accounts
    SET status = 'CLOSED',
        version_no = version_no + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE account_id = 103
      AND tenant_id = 10
      AND status = 'SUSPENDED'
      AND deleted_at IS NULL
    RETURNING account_id, tenant_id, status, version_no
)
SELECT COUNT(*) AS affected_rows
FROM changed;
-- 1 trên dữ liệu ban đầu.

ROLLBACK;
```

Đây là cách **đếm kết quả thực sự của chính câu `UPDATE`**, không phải chỉ đếm trước bằng `SELECT`.

### 9.3. Đếm không đủ: kiểm tra đúng tập khóa

Với một batch dự kiến sửa đúng các ID `{101, 102}`, kết quả trả `{102, 103}` vẫn có `COUNT=2` nhưng **sai đối tượng**. Quy trình nghiêm ngặt phải đối chiếu cả:

1. **Số dòng kỳ vọng**.
2. **Danh sách khóa kỳ vọng**.
3. **Giá trị trước và sau kỳ vọng**.
4. **Phạm vi tenant/kỳ/trạng thái được phép**.

Trong công việc nhạy cảm, việc phê duyệt có thể gắn với **danh sách ID đích được lưu** trước khi chạy, không chỉ gắn với một điều kiện văn bản.

## 10. Kiểm soát cardinality ngay trong SQL

Với truy vấn chỉ được phép tác động đến **tối đa hai tài khoản đang `SUSPENDED` thuộc tenant 10**, có thể dùng một **danh sách ứng viên** và điều kiện số lượng ngay trong cùng câu SQL. Ví dụ sau dùng cú pháp PostgreSQL.

```sql
BEGIN;

WITH candidates AS MATERIALIZED (
    SELECT account_id
    FROM safe_dml_accounts
    WHERE tenant_id = 10
      AND status = 'SUSPENDED'
      AND deleted_at IS NULL
    FOR UPDATE
),
guard AS (
    SELECT COUNT(*) AS candidate_count
    FROM candidates
),
changed AS (
    UPDATE safe_dml_accounts AS a
    SET status = 'CLOSED',
        version_no = a.version_no + 1,
        updated_at = CURRENT_TIMESTAMP
    FROM candidates AS c
    WHERE a.account_id = c.account_id
      AND (
          SELECT candidate_count BETWEEN 1 AND 2
          FROM guard
      )
    RETURNING a.account_id, a.tenant_id, a.status, a.version_no
)
SELECT account_id, tenant_id, status, version_no
FROM changed
ORDER BY account_id;

ROLLBACK;
```

Trong dữ liệu gốc, ứng viên của tenant 10 là **account 103**, nên câu lệnh có thể cập nhật đúng một dòng. Nếu có **nhiều hơn hai ứng viên**, điều kiện `guard` là sai và CTE `changed` không cập nhật dòng nào.

### 10.1. Điều kiện 0 dòng không phải là báo lỗi tự động

Mẫu trên khi bị guard chặn sẽ **không tự phát sinh exception**; nó trả **0 dòng** từ `changed`. Ứng dụng hoặc quy trình vận hành **phải kiểm tra kết quả** và xem 0 dòng là **không đạt kỳ vọng** nếu thao tác cần ít nhất một dòng. Không thể ghi “thành công” chỉ vì câu SQL không báo lỗi.

### 10.2. Vì sao chọn tập ứng viên bằng ID?

CTE `candidates` xác định **tập khóa dự kiến**, và `UPDATE` chỉ nối vào các khóa đó. Nó hạn chế nguy cơ một điều kiện quá rộng bị **đánh giá lại ở nơi khác** trong cùng lệnh theo cách không kiểm soát.

`MATERIALIZED` trong PostgreSQL mới hỗ trợ nhấn mạnh rằng CTE ứng viên phải được thực hiện như một kết quả riêng; `FOR UPDATE` khóa những dòng ứng viên hiện có. Mức an toàn cuối cùng vẫn phụ thuộc quyền, isolation và việc xử lý các tác động ngoài bảng.

### 10.3. Hạn chế quan trọng khi có giao dịch đồng thời

`FOR UPDATE` khóa **các dòng đã chọn**, không mặc nhiên ngăn giao dịch khác **chèn thêm một dòng mới** có `tenant_id=10` và `status='SUSPENDED'` sau khi danh sách ứng viên được tạo. Vì vậy mẫu này bảo vệ **tập khóa đã chụp**, chứ không khẳng định mọi tài khoản thỏa predicate ở mọi thời điểm đều đã được đưa vào batch.

Nếu nghiệp vụ yêu cầu một tập hoàn chỉnh không bị thêm/bớt trong lúc xử lý, phải thiết kế isolation/khóa/điều kiện phối hợp phù hợp, hoặc xử lý trên **danh sách ID đã được phê duyệt**. Không suy luận `COUNT` + `FOR UPDATE` đã khóa mọi trường hợp có thể xuất hiện trong tương lai.

## 11. Bắt buộc một dòng: phát sinh lỗi nếu ảnh hưởng sai số lượng

Đối với lệnh **phải sửa đúng một dòng**, có thể kiểm tra ngay trong một khối SQL chạy ở phía database. PostgreSQL hỗ trợ khối `DO` bằng PL/pgSQL:

```sql
BEGIN;

DO $$
DECLARE
    affected_count BIGINT;
BEGIN
    UPDATE safe_dml_accounts
    SET credit_limit = 1400,
        version_no = version_no + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE account_id = 102
      AND tenant_id = 10
      AND status = 'ACTIVE'
      AND deleted_at IS NULL
      AND version_no = 1;

    GET DIAGNOSTICS affected_count = ROW_COUNT;

    IF affected_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one account, changed %',
            affected_count;
    END IF;
END $$;

-- Kiểm tra trực tiếp nếu khối thành công:
SELECT account_id, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102;

-- Buổi thực hành luôn hủy thay đổi:
ROLLBACK;
```

Điểm quan trọng:

- `GET DIAGNOSTICS ... = ROW_COUNT` lấy số dòng bị tác động của câu `UPDATE` vừa chạy trong khối.
- Nếu số dòng **0 hoặc lớn hơn 1**, `RAISE EXCEPTION` báo lỗi.
- Khi một statement `DO` lỗi, những thay đổi transaction do statement đó thực hiện không được giữ; trong transaction PostgreSQL còn cần `ROLLBACK` để thoát trạng thái lỗi.
- Ví dụ `account_id` là khóa chính nên lệnh hợp lệ không thể tác động quá một dòng; kiểm tra `<> 1` đặc biệt quan trọng để phát hiện **0 dòng**.

Trong ứng dụng, một cách đơn giản hơn là để transaction ở tầng driver, chạy `UPDATE ... RETURNING`, xác minh **đúng một dòng** rồi mới gọi `COMMIT`; nếu sai, gọi `ROLLBACK`. Không bắt buộc phải dùng PL/pgSQL cho mọi thao tác.

## 12. `UPDATE ... FROM`: cẩn thận điều kiện nối

Trong PostgreSQL, cú pháp `UPDATE ... FROM` giúp cập nhật một bảng dựa trên dữ liệu từ bảng khác. Nhưng thiếu hoặc sai điều kiện join có thể biến thao tác chính xác thành cập nhật sai hàng loạt.

### 12.1. Ví dụ nguồn hạn mức mới

```sql
CREATE TEMP TABLE safe_dml_limit_changes (
    tenant_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    new_credit_limit NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (tenant_id, account_id)
);

INSERT INTO safe_dml_limit_changes
    (tenant_id, account_id, new_credit_limit)
VALUES
    (10, 101, 1100),
    (10, 102, 1600);
```

Nguồn có hai thay đổi đã chuẩn bị cho tenant 10. Mẫu cập nhật có điều kiện nối rõ ràng:

```sql
BEGIN;

UPDATE safe_dml_accounts AS a
SET credit_limit = s.new_credit_limit,
    version_no = a.version_no + 1,
    updated_at = CURRENT_TIMESTAMP
FROM safe_dml_limit_changes AS s
WHERE a.account_id = s.account_id
  AND a.tenant_id = s.tenant_id
  AND a.tenant_id = 10
  AND a.status = 'ACTIVE'
  AND a.deleted_at IS NULL
RETURNING a.account_id, a.tenant_id, a.credit_limit;

ROLLBACK;
```

Kết quả dự kiến: account 101 thành 1100, account 102 thành 1600, **hai dòng** thuộc tenant 10.

### 12.2. Thiếu join là lỗi cực kỳ nguy hiểm

```sql
-- NGUY HIỂM: minh họa cú pháp sai ý nghĩa, KHÔNG chạy.
UPDATE safe_dml_accounts AS a
SET credit_limit = s.new_credit_limit
FROM safe_dml_limit_changes AS s
WHERE a.tenant_id = 10;
```

Không có `a.account_id = s.account_id` và `a.tenant_id = s.tenant_id`, nên mỗi tài khoản của tenant 10 có thể khớp với **nhiều dòng nguồn**. PostgreSQL có thể chọn một giá trị từ dòng nguồn khớp trong cách cập nhật `UPDATE ... FROM` khi có nhiều match; bạn **không được dựa vào lựa chọn đó** để xác định kết quả.

### 12.3. Một dòng đích phải khớp tối đa một dòng nguồn

Nếu cùng `account_id` xuất hiện nhiều lần trong bảng nguồn, kết quả `UPDATE ... FROM` có thể **không xác định theo quy tắc nghiệp vụ**. Trong bảng `safe_dml_limit_changes`, `PRIMARY KEY(tenant_id,account_id)` giúp ngăn nhiều bản ghi nguồn cho cùng khóa.

Khi nguồn đến từ staging, hãy:

1. Phát hiện trùng khóa `(tenant_id, account_id)`.
2. Chọn chính sách rõ: từ chối, chọn phiên bản mới nhất, hoặc tính tổng/giá trị tổng hợp hợp lệ.
3. Bảo đảm truy vấn nguồn sau xử lý có **một dòng mỗi khóa đích**.
4. Chỉ sau đó mới chạy `UPDATE ... FROM`.

Không để database “tùy chọn” một giá trị khi nhiều bản ghi nguồn xung đột.

## 13. `DELETE ... USING`: kiểm chứng quan hệ nguồn

PostgreSQL hỗ trợ `DELETE ... USING` để xóa dòng đích dựa trên một quan hệ khác.

Giả sử có danh sách ID cần vô hiệu hóa/xóa đã được kiểm duyệt:

```sql
CREATE TEMP TABLE safe_dml_delete_requests (
    tenant_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (tenant_id, account_id)
);

INSERT INTO safe_dml_delete_requests
    (tenant_id, account_id, reason)
VALUES
    (10, 104, 'Approved cleanup');
```

Xóa thử đúng khóa:

```sql
BEGIN;

DELETE FROM safe_dml_accounts AS a
USING safe_dml_delete_requests AS r
WHERE a.account_id = r.account_id
  AND a.tenant_id = r.tenant_id
  AND r.tenant_id = 10
  AND r.reason = 'Approved cleanup'
RETURNING a.account_id, a.tenant_id, a.account_name;

ROLLBACK;
```

Trong dữ liệu gốc, chỉ account 104 khớp yêu cầu, nên `RETURNING` có **một dòng**.

### 13.1. Hai rủi ro lớn

1. **Thiếu điều kiện nối khóa:** có thể chọn sai tập đích vì mọi dòng đích nối được với các dòng yêu cầu theo điều kiện rộng.
2. **Không đối chiếu yêu cầu với dữ liệu thật:** một bản ghi trong bảng yêu cầu xóa có thể sai tenant hoặc không còn đủ điều kiện xóa tại thời điểm thực thi.

Hãy xem trước bằng `SELECT` dùng **cùng các điều kiện nối**, kiểm tra danh sách ID và số lượng, rồi mới chạy `DELETE`.

### 13.2. Tập yêu cầu là dữ liệu, không phải “giấy phép” tự động

Một dòng trong `safe_dml_delete_requests` không nên tự đủ để xóa tài khoản nếu chưa có:

- Nguồn yêu cầu đáng tin cậy.
- Xác thực quyền người yêu cầu.
- Quy tắc nghiệp vụ xác định tài khoản có thể xóa.
- Trạng thái phê duyệt/mốc hết hạn nếu quy trình yêu cầu.
- Khả năng audit và phục hồi.

Trong môi trường nhiều tenant, đặc biệt không được chỉ join `account_id` nếu khóa chỉ duy nhất **bên trong tenant**.

## 14. `UPDATE` theo thời gian: biên kỳ và múi giờ

Một tác vụ định kỳ có thể cần:

> “Vô hiệu hóa các bản ghi được tạo **trước ngày 1/7/2026 theo giờ Việt Nam**.”

Với cột `created_at TIMESTAMPTZ`, nên dùng **một mốc thời gian có múi giờ rõ ràng**:

```sql
WHERE created_at < (
    TIMESTAMP '2026-07-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
```

Nếu lấy một khoảng từ đầu tháng 6 tới trước đầu tháng 7:

```sql
WHERE created_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND created_at < (
    TIMESTAMP '2026-07-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
```

Đó là khoảng **nửa mở** `[start, end)`, tránh lỗi bỏ các bản ghi có phần giây sau `23:59:59`.

### 14.1. Tránh biến “ngày” thành điều kiện lệch múi giờ

Nếu một máy chạy SQL ở UTC và máy khác chạy ở UTC+7, một điều kiện sử dụng timestamp không rõ múi giờ có thể chọn tập dòng khác nhau. Với tác vụ **cập nhật/xóa dữ liệu**, điều này nguy hiểm hơn truy vấn báo cáo vì thay đổi thật được lưu.

Xác định:

- **Múi giờ nghiệp vụ**.
- Kiểu cột là `DATE`, `TIMESTAMP` hay `TIMESTAMPTZ`.
- Hai mốc **bao gồm** và **loại trừ**.
- Tác vụ chạy khi nào và dữ liệu đã đủ điều kiện xử lý chưa.

### 14.2. Khóa kỳ không thay thế điều kiện tenant/trạng thái

Ngay cả khi mốc ngày đúng, thao tác:

```sql
-- NGUY HIỂM nếu đây chưa phải toàn bộ tiêu chí nghiệp vụ.
DELETE FROM accounts
WHERE created_at < :cutoff;
```

có thể xóa mọi bản ghi cũ ở nhiều tenant và nhiều trạng thái. Cần kết hợp **phạm vi, trạng thái, chính sách lưu trữ và phê duyệt** với điều kiện thời gian.

## 15. `NULL`: không được dùng `= NULL`

Trong SQL, `NULL` biểu diễn giá trị chưa xác định/vắng mặt. Muốn chọn dòng **chưa xóa mềm**, phải dùng:

```sql
WHERE deleted_at IS NULL
```

Không viết:

```sql
-- Sai logic, không chọn các dòng NULL theo dự kiến.
WHERE deleted_at = NULL
```

Biểu thức `deleted_at = NULL` thông thường cho **`UNKNOWN`**, không phải `TRUE`, nên `WHERE` loại các dòng đó.

### 15.1. Điều kiện phủ định và `NULL`

```sql
WHERE status <> 'CLOSED'
```

nếu `status` nullable, các dòng `status IS NULL` **không** được chọn vì kết quả so sánh là `UNKNOWN`. Điều đó có thể khác mục tiêu “mọi trạng thái chưa đóng, kể cả thiếu trạng thái”.

Trong bảng thực hành `status NOT NULL`, nên trường hợp này không xảy ra; nhưng trên bảng thật, phải xét tính nullable của từng cột.

### 15.2. `COALESCE` không phải lời giải tự động cho mọi điều kiện

```sql
WHERE COALESCE(status, 'ACTIVE') = 'ACTIVE'
```

có thể làm cả những dòng **trạng thái chưa biết** bị xem như `ACTIVE`. Trước khi dùng nó trong một câu `DELETE`/`UPDATE`, cần xác nhận đây là quyết định nghiệp vụ có chủ đích.

## 16. Tham số lọc tùy chọn có thể vô hiệu hóa `WHERE`

Một cách viết nguy hiểm trong ứng dụng:

```sql
-- Chỉ là mẫu minh họa, không dùng cho thao tác nguy hiểm.
UPDATE accounts
SET status = 'CLOSED'
WHERE (:account_id IS NULL OR account_id = :account_id);
```

Nếu `:account_id` bị truyền `NULL`, điều kiện `:account_id IS NULL` là `TRUE` cho mọi dòng, câu lệnh **có thể cập nhật toàn bảng**.

Tương tự:

```sql
WHERE account_id = COALESCE(:account_id, account_id)
```

thường làm tất cả các dòng có `account_id` khác `NULL` khớp khi tham số bị thiếu.

### 16.1. Cách xử lý an toàn hơn

Với thao tác nhắm **một tài khoản**:

1. **Bắt buộc** `account_id` và `tenant_id` ở tầng API/ứng dụng.
2. Kiểm tra kiểu và quyền sở hữu tenant.
3. Dùng truy vấn có `WHERE account_id = :account_id AND tenant_id = :tenant_id`.
4. Kiểm tra `affected_rows = 1`.
5. Nếu thiếu tham số, **từ chối request trước khi gửi SQL**.

Không xây dựng `WHERE` bằng cách nối chuỗi trực tiếp từ đầu vào. Dùng **prepared statements/bind parameters** để tránh SQL injection, nhưng nhớ rằng bind parameter chỉ bảo vệ cấu trúc SQL — **không tự ngăn một điều kiện hợp lệ nhưng quá rộng**.

### 16.2. Lệnh hàng loạt phải là một API riêng

Thay vì để `account_id = NULL` có nghĩa “áp dụng mọi tài khoản”, nên có **hai đường nghiệp vụ khác nhau**:

- `updateOneAccount(accountId, tenantId, ...)`: yêu cầu đúng một khóa.
- `bulkUpdateAccounts(approvedIds, approvalToken, ...)`: yêu cầu danh sách khóa có kiểm soát và hạn mức.

Tách đường đơn lẻ và hàng loạt giúp tránh một lỗi tham số biến thao tác nhỏ thành thao tác toàn bảng.

## 17. Tránh dùng `LIMIT` như một tấm khiên duy nhất

Một ý tưởng thường gặp:

> “Nếu sợ cập nhật nhầm toàn bảng, chỉ cần thêm `LIMIT 1`.”

Điều này chưa đủ và không phải cú pháp trực tiếp của `UPDATE`/`DELETE` trong PostgreSQL theo cách một số hệ khác hỗ trợ.

### 17.1. `LIMIT 1` có thể sửa **một dòng sai**

Ngay cả khi một hệ quản trị cho phép giới hạn số dòng `UPDATE`, việc giới hạn 1 dòng chỉ ngăn sửa **nhiều dòng**, **không chứng minh dòng được chọn là đúng**. Nếu điều kiện bị sai hoặc thiếu thứ tự xác định, một dòng được sửa vẫn có thể là tài khoản của khách hàng khác.

### 17.2. Khi cần chia batch trong PostgreSQL

PostgreSQL thường dùng CTE tìm các khóa đích rồi cập nhật/xóa theo khóa:

```sql
BEGIN;

WITH candidates AS (
    SELECT account_id
    FROM safe_dml_accounts
    WHERE tenant_id = 10
      AND status = 'SUSPENDED'
      AND deleted_at IS NULL
    ORDER BY account_id
    LIMIT 2
    FOR UPDATE
)
UPDATE safe_dml_accounts AS a
SET status = 'CLOSED',
    version_no = a.version_no + 1
FROM candidates AS c
WHERE a.account_id = c.account_id
RETURNING a.account_id, a.tenant_id, a.status;

ROLLBACK;
```

Đây là **chọn tối đa 2 ứng viên phù hợp** theo thứ tự ID, không phải một quy tắc cho phép sửa bất kỳ 2 tài khoản nào. Trên hệ thống thật, batch còn cần điều kiện nghiệp vụ, checkpoint, audit và xử lý các lần chạy lại.

### 17.3. Lựa chọn tập khóa phải được xác định

Nếu `ORDER BY` không có khóa đủ để phân xử đồng hạng, `LIMIT 2` có thể lấy hai dòng khác nhau giữa các lần chạy. Với thao tác sửa/xóa, dùng **thứ tự ổn định** như khóa chính khi thật sự cần xử lý theo batch.

## 18. Soft delete: đánh dấu xóa thay vì xóa vật lý

Trong nhiều hệ thống, việc xóa hẳn một tài khoản là quá rủi ro hoặc không phù hợp chính sách lưu trữ. **Soft delete** là ghi thời điểm xóa hoặc trạng thái thay vì xóa bản ghi.

Ví dụ:

```sql
BEGIN;

UPDATE safe_dml_accounts
SET deleted_at = CURRENT_TIMESTAMP,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = 104
  AND tenant_id = 10
  AND deleted_at IS NULL
RETURNING account_id, tenant_id, deleted_at, version_no;

ROLLBACK;
```

Khi đó tài khoản vẫn có trong bảng, nhưng ứng dụng có thể chỉ hiển thị các dòng:

```sql
WHERE deleted_at IS NULL
```

### 18.1. Ưu điểm và giới hạn

**Ưu điểm:**

- Không xóa vật lý dòng tài khoản và thường không kích hoạt `ON DELETE CASCADE`.
- Có thể khôi phục hiển thị bằng cách bỏ đánh dấu nếu chính sách cho phép.
- Hữu ích cho quy trình cần xác minh hoặc có thời gian chờ trước khi xóa hẳn.

**Giới hạn:**

- Mọi truy vấn nghiệp vụ phải xử lý đúng `deleted_at`, tránh hiển thị hoặc tính toán dữ liệu đã xóa mềm.
- Ràng buộc `UNIQUE` có thể cần thiết kế lại khi cho phép tái sử dụng khóa của dòng đã xóa.
- Dữ liệu cá nhân có thể vẫn tồn tại; soft delete **không tương đương** xóa theo yêu cầu pháp lý/quy định lưu trữ.
- Trigger, đồng bộ dữ liệu hoặc báo cáo có thể cần xem `deleted_at` để hiểu trạng thái.

### 18.2. Soft delete cần điều kiện trạng thái và idempotency

Nếu chạy lại:

```sql
UPDATE safe_dml_accounts
SET deleted_at = CURRENT_TIMESTAMP
WHERE account_id = 104
  AND deleted_at IS NULL;
```

lần đầu có thể sửa 1 dòng, lần sau **0 dòng** vì đã xóa mềm. Đây là hành vi **không thay đổi lại trạng thái** khi retry, nhưng ứng dụng vẫn phải phân biệt:

- 0 dòng vì **đã xử lý trước đó**.
- 0 dòng vì **sai tenant hoặc không có quyền**.
- 0 dòng vì **ID không tồn tại**.

Không nên trả cùng một thông báo thành công cho mọi nguyên nhân 0 dòng mà không có chính sách rõ ràng.

## 19. Hard delete: bắt buộc xét quan hệ và thời hạn lưu trữ

**Hard delete** là xóa vật lý:

```sql
DELETE FROM safe_dml_accounts
WHERE account_id = 104
  AND tenant_id = 10;
```

Nó có thể phù hợp cho dữ liệu tạm, bản ghi tạo nhầm chưa phát sinh giao dịch, hoặc dữ liệu hết thời hạn lưu theo quy định. Tuy vậy, trước khi xóa cần:

1. Xác định **lý do và quyền xóa**.
2. Kiểm tra dòng đích và các tham chiếu tới nó.
3. Xác nhận có `ON DELETE CASCADE`, `RESTRICT`, `NO ACTION`, `SET NULL` hoặc trigger.
4. Xác định nghĩa vụ lưu trữ/kiểm toán.
5. Đảm bảo có cách phục hồi nếu quy trình yêu cầu.
6. Chạy transaction, `RETURNING` và kiểm tra dữ liệu liên quan.

### 19.1. `TRUNCATE` không phải `DELETE` an toàn

```sql
-- Đặc biệt nguy hiểm trên bảng thật, KHÔNG chạy.
TRUNCATE TABLE safe_dml_accounts;
```

`TRUNCATE` nhằm làm rỗng bảng và **không có `WHERE` để lọc từng dòng**. Trong PostgreSQL nó có hành vi transaction và quy tắc khóa/FK riêng; ở các DBMS khác, `TRUNCATE` có thể có cơ chế commit ngầm hoặc giới hạn rollback khác.

**Không dùng `TRUNCATE` như cách “xóa nhanh hơn” khi yêu cầu chỉ xóa một phần dữ liệu**. Nó là thao tác khác về mục đích và phạm vi.

### 19.2. `DROP TABLE` là một rủi ro khác

`DROP TABLE` loại bỏ cả đối tượng bảng, không chỉ dữ liệu. Nó không phải biến thể của `DELETE WHERE` và có quy tắc phân quyền, phụ thuộc đối tượng và phục hồi riêng. Trong quy trình làm sạch dữ liệu, cần phân biệt **xóa dòng**, **làm rỗng bảng** và **xóa cấu trúc bảng**.

## 20. Kiểm tra phiên bản để chống ghi đè thay đổi đồng thời

Giả sử hai nhân viên vận hành cùng mở tài khoản 102:

```text
08:00 Client A đọc credit_limit=1500, version_no=1
08:01 Client B đổi credit_limit=1800, version_no=2
08:02 Client A vẫn cố ghi credit_limit=1400 dựa trên bản cũ
```

Nếu client A chỉ dùng:

```sql
UPDATE safe_dml_accounts
SET credit_limit = 1400
WHERE account_id = 102;
```

nó có thể ghi đè thay đổi mới của B.

### 20.1. Optimistic locking bằng `version_no`

Client A nên gửi phiên bản mà nó đã đọc:

```sql
UPDATE safe_dml_accounts
SET credit_limit = 1400,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = 102
  AND tenant_id = 10
  AND version_no = 1
  AND status = 'ACTIVE'
  AND deleted_at IS NULL
RETURNING account_id, credit_limit, version_no;
```

Nếu client B đã cập nhật lên `version_no=2` trước đó, câu của A sẽ trả **0 dòng**, không ghi đè dữ liệu. Ứng dụng cần thông báo **xung đột phiên bản** và yêu cầu tải lại thay vì mặc định “tài khoản không tồn tại”.

### 20.2. Kiểm tra phiên bản là một điều kiện nghiệp vụ

`version_no` phải được tăng một cách nhất quán ở mọi luồng cập nhật có liên quan. Nếu có một script sửa tài khoản mà **quên tăng phiên bản**, optimistic locking có thể không phát hiện một thay đổi cạnh tranh.

Với hệ thống dùng ORM, cần hiểu framework có tự quản lý version hay phải tự viết `WHERE version_no = expected_version`. Không tự suy đoán rằng ORM luôn bảo vệ mọi đường ghi SQL thủ công.

### 20.3. Lệnh update trả 0 dòng chưa đủ để kết luận nguyên nhân

Kết quả 0 dòng có thể do:

- Không có ID 102.
- Sai tenant.
- `status` không còn `ACTIVE`.
- `deleted_at` khác `NULL`.
- `version_no` đã đổi.

Ứng dụng cần dùng **các bước chẩn đoán có phân quyền** để xác định lỗi nghiệp vụ. Không tùy tiện tiết lộ rằng một tài khoản ngoài tenant của người dùng có tồn tại hay không.

## 21. Kiểm chứng dữ liệu sau thay đổi với snapshot/audit

Trong thao tác nhạy cảm, nên có **bản ghi trước** và **bản ghi sau** để giải thích được thay đổi.

Một log có ích có thể chứa:

```text
operation_id
actor_id
tenant_id
target_table
target_primary_keys
approved_row_count
actual_row_count
before_values
after_values
business_reason
requested_at
committed_at
transaction_outcome
```

Không phải mọi trường đều được lưu trong cùng một bảng; thiết kế tùy yêu cầu quyền riêng tư, hiệu năng và kiểm toán.

### 21.1. Snapshot trước khi `UPDATE` trong cùng transaction

Ví dụ **thử nghiệm** lưu các giá trị cũ vào bảng tạm trước khi cập nhật:

```sql
CREATE TEMP TABLE safe_dml_before_snapshot AS
SELECT
    account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE FALSE;
```

Khi thực hiện tác vụ:

```sql
BEGIN;

INSERT INTO safe_dml_before_snapshot
    (account_id, tenant_id, status, credit_limit, version_no)
SELECT
    account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102
  AND tenant_id = 10
  AND status = 'ACTIVE'
  AND deleted_at IS NULL
FOR UPDATE;

UPDATE safe_dml_accounts
SET credit_limit = 1400,
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = 102
  AND tenant_id = 10
  AND status = 'ACTIVE'
  AND deleted_at IS NULL
  AND version_no = 1
RETURNING account_id, credit_limit, version_no;

SELECT
    b.account_id,
    b.credit_limit AS before_limit,
    a.credit_limit AS after_limit,
    b.version_no AS before_version,
    a.version_no AS after_version
FROM safe_dml_before_snapshot AS b
JOIN safe_dml_accounts AS a
    ON a.account_id = b.account_id
WHERE b.account_id = 102;

ROLLBACK;
```

Kết quả dự kiến khi bắt đầu từ dữ liệu gốc:

```text
before_limit=1500, after_limit=1400
before_version=1, after_version=2
```

**Lưu ý:** `safe_dml_before_snapshot` là bảng tạm được tạo trước transaction ví dụ. Nếu chạy lại ví dụ nhiều lần trong cùng phiên mà không dọn nó, có thể tích lũy các snapshot cũ và tạo nhiều dòng khi `JOIN`. Trong thực tế phải gắn **`operation_id` duy nhất** hoặc dùng một bảng audit được thiết kế với khóa rõ ràng để không trộn các lần chạy.

### 21.2. Audit cần cùng transaction nếu phải nguyên tử

Nếu yêu cầu audit phải luôn có cùng dữ liệu thay đổi, ghi dữ liệu audit **trong transaction với UPDATE/DELETE**. Nếu ghi audit sau commit bằng một thao tác độc lập, có khả năng dữ liệu đã đổi nhưng audit thất bại.

Tuy nhiên, chỉ log vào bảng trong cùng database không tự giải quyết việc gửi log tới hệ thống ngoài. Nếu cần phát sự kiện tới Kafka/email/API, cân nhắc **outbox** và cơ chế retry/idempotency.

### 21.3. Không coi audit là “bản sao lưu đầy đủ”

Audit có thể chỉ lưu vài trường hoặc chỉ một sự kiện “đã xóa account 101”. Nó không thay thế một bản backup cho việc khôi phục **đầy đủ cấu trúc và quan hệ** sau thao tác sai. Phải xác định năng lực khôi phục thực tế trước khi thao tác xóa quy mô lớn.

## 22. Kiểm chứng sau `COMMIT`

Kết quả `RETURNING` và `SELECT` bên trong transaction xác minh trạng thái **trước khi commit**. Sau khi `COMMIT` thành công, với tác vụ quan trọng có thể đọc lại:

```sql
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 102
  AND tenant_id = 10;
```

Đây là một bước khác với xem trong transaction, giúp xác nhận trạng thái đã commit từ một lần đọc phù hợp. Trong môi trường có replica:

- Một **read replica** có thể trễ, chưa thấy thay đổi đã commit ở primary.
- Đọc ở primary hoặc cơ chế đọc nhất quán theo yêu cầu để tránh kết luận sai “COMMIT không thành công”.
- Nếu có giao dịch khác cập nhật tiếp sau commit, trạng thái tại lần đọc sau có thể khác. Cần audit/phiên bản/snapshot để phân biệt thao tác của mình với thao tác sau đó.

### 22.1. `COMMIT` thành công mới là ranh giới quan trọng

Sau khi DML `RETURNING` đúng số dòng, các ràng buộc deferred hoặc lỗi hệ thống **vẫn có thể khiến commit thất bại**. Chỉ thông báo hoàn thành khi driver nhận và xử lý được kết quả commit theo giao thức.

Trong sự cố mất kết nối ngay lúc commit, ứng dụng có thể **không chắc** commit đã thành công hay chưa. Dùng **operation ID/idempotency key** và bước đối soát đáng tin cậy, thay vì retry mù quáng một thay đổi không idempotent.

### 22.2. Kiểm tra tổng số dòng và bất biến liên bảng

Sau `UPDATE`, có thể kiểm tra:

- Tổng tài khoản theo tenant không đổi khi chỉ cập nhật trạng thái.
- Tổng `credit_limit` trong phạm vi giảm/tăng đúng số dự kiến.
- Hóa đơn không bị xóa khi chỉ cập nhật một thuộc tính tài khoản, nếu schema không có trigger làm vậy.
- Những tài khoản ngoài danh sách đích giữ nguyên.

Sau `DELETE`, có thể kiểm tra:

- Khóa đích không còn tồn tại.
- Các bản ghi liên quan được xử lý theo FK đúng chính sách.
- Không mất dòng ngoài danh sách dự kiến.
- Số lượng archive/audit đúng với danh sách xóa đã được phê duyệt.

## 23. Phân quyền tối thiểu: lớp phòng ngừa trước khi SQL được gửi

Ngay cả một quy trình cẩn thận cũng có thể gặp lỗi thao tác. Phân quyền giúp **giảm phạm vi hậu quả**.

### 23.1. Tách quyền đọc và quyền ghi

Một tài khoản dùng cho báo cáo thường chỉ cần `SELECT`; nó **không nên có `UPDATE`, `DELETE`, `TRUNCATE`** nếu không có yêu cầu.

Một tài khoản vận hành cập nhật có thể được cấp quyền viết trên **những bảng/cột cần thiết**, thay vì quyền quản trị toàn database.

Ví dụ minh họa PostgreSQL (tên role phải thực sự tồn tại và cần quyền quản trị phù hợp):

```sql
-- Minh họa phân quyền trên bảng nghiệp vụ thật, không chạy trực tiếp
-- nếu chưa có role và chính sách quyền tương ứng:
GRANT SELECT, UPDATE (credit_limit)
ON TABLE accounts
TO billing_operator;
```

Quyền cập nhật cột `credit_limit` giúp ngăn role đó tự sửa những cột không được phép như `status`, nhưng **không thay thế điều kiện `WHERE`**: role vẫn có thể cập nhật cột được phép trên nhiều dòng nếu không bị lớp kiểm soát khác giới hạn.

### 23.2. Row-Level Security (RLS) trong PostgreSQL

Với hệ thống đa tenant, PostgreSQL hỗ trợ **Row-Level Security** để áp chính sách cho những dòng người dùng/role được đọc hoặc ghi. RLS có thể bổ sung lớp bảo vệ khi query quên lọc tenant.

Nhưng:

- RLS chỉ có hiệu lực khi được cấu hình và áp dụng đúng cho role/bảng.
- Owner, role có quyền đặc biệt hoặc chính sách cấu hình không đúng có thể có đường vượt qua RLS.
- RLS không tự kiểm tra **số dòng kỳ vọng** hoặc **ý định nghiệp vụ cụ thể**.

Vì vậy, vẫn cần `WHERE tenant_id = ...`, xác thực quyền và kiểm tra `affected_rows`. Không coi RLS là lý do để viết câu `UPDATE` thiếu điều kiện.

### 23.3. Tách môi trường và quyền production

Các biện pháp tổ chức hữu ích:

- SQL client mặc định kết nối **read-only** khi truy cập production để khảo sát.
- Đường cấp quyền ghi yêu cầu thao tác chủ động, có thời hạn hoặc phê duyệt.
- Môi trường staging có dữ liệu thử phản ánh schema, nhưng không chứa dữ liệu nhạy cảm không cần thiết.
- Sử dụng migration/ứng dụng có review cho thay đổi quy mô lớn thay vì chạy tay không lưu dấu vết.

Các biện pháp này bổ trợ cho kiểm soát trong SQL, không thay thế nó.

## 24. Chế độ “safe updates” của công cụ: hữu ích nhưng có giới hạn

Một số SQL client và DBMS có cơ chế cảnh báo hoặc ngăn `UPDATE`/`DELETE` thiếu điều kiện.

### 24.1. MySQL `SQL_SAFE_UPDATES`

MySQL có biến session `SQL_SAFE_UPDATES` (một số client hiển thị là “safe update mode”). Khi bật, nó có thể ngăn một số câu `UPDATE`/`DELETE` không có điều kiện dùng khóa phù hợp hoặc không có giới hạn theo quy tắc của MySQL.

```sql
-- Ví dụ MySQL, KHÔNG phải PostgreSQL:
SET SQL_SAFE_UPDATES = 1;
```

Nhưng **không được coi đây là bằng chứng câu lệnh đúng tập đích**:

- Điều kiện dùng cột khóa vẫn có thể chọn **rất nhiều dòng**.
- Một giới hạn dòng có thể ngăn cập nhật toàn bảng nhưng vẫn chọn **sai dòng**.
- Cấu hình có thể khác giữa các phiên/kết nối.
- PostgreSQL không có biến `SQL_SAFE_UPDATES` theo cú pháp này.

### 24.2. Cảnh báo của IDE/SQL client

Một số công cụ hiển thị cảnh báo khi `UPDATE`/`DELETE` không có `WHERE`, hỗ trợ “preview affected rows” hoặc yêu cầu xác nhận. Tính năng thực tế phụ thuộc phiên bản và cấu hình.

Đó là **hàng rào chống thao tác nhầm**, nhưng không thể hiểu ý nghĩa “chỉ tài khoản đã chấm dứt hợp đồng của tenant 10” nếu bạn viết sai điều kiện.

## 25. Checklist vận hành trước – trong – sau

### 25.1. Trước khi chạy

| Kiểm tra | Câu hỏi |
|---|---|
| Môi trường | Có chắc đây là database/schema/tenant đúng không? |
| Quyền | Role hiện tại có phạm vi quyền tối thiểu phù hợp không? |
| Nghiệp vụ | Lý do thay đổi đã được phê duyệt chưa? |
| Tập khóa | Các ID đích có đúng và đầy đủ không? |
| Trạng thái | Có cần kiểm tra `status`, `deleted_at`, `version_no` không? |
| Số lượng | Dự kiến 1 dòng, N dòng hay một ngưỡng tối đa? |
| Quan hệ | FK/trigger/cascade có thể gây tác động dây chuyền không? |
| Thời gian | Điều kiện ngày giờ, biên kỳ và múi giờ đã rõ chưa? |
| Phục hồi | Có transaction/backup/snapshot và kế hoạch rollback không? |

### 25.2. Trong khi chạy

1. Mở transaction nếu thao tác cần kiểm tra rồi quyết định commit.
2. Xác định/khóa tập khóa đích khi cần, không chỉ đếm số dòng.
3. Chạy câu DML có `WHERE` đầy đủ và `RETURNING` theo khả năng DBMS.
4. Xác minh **số dòng thực bị tác động** và **đúng danh sách ID**.
5. Đối chiếu trước–sau và kiểm tra bất biến ở bảng liên quan.
6. Nếu bất kỳ kết quả nào ngoài kỳ vọng, **`ROLLBACK`**.
7. Chỉ khi kiểm tra đạt mới **`COMMIT`**.

### 25.3. Sau khi chạy

- Xác nhận commit.
- Đọc lại theo cơ chế nhất quán phù hợp (chú ý replica lag).
- Đối chiếu audit với operation ID, row count, danh sách khóa.
- Báo cáo thay đổi: **đã đổi gì, bao nhiêu, khi nào, ai phê duyệt**.
- Nếu có sự cố, kích hoạt quy trình phục hồi/bù trừ đã chuẩn bị.

## 26. Bảng các lỗi thường gặp

| Nhận định hoặc thao tác | Vấn đề | Cách sửa |
|---|---|---|
| “Có `WHERE` là an toàn” | `WHERE` có thể luôn đúng hoặc chọn quá rộng | Preview danh sách khóa và so row count |
| “`UPDATE 1` nghĩa là sửa đúng dòng” | Một dòng vẫn có thể là sai ID/tenant | `RETURNING` và đối chiếu khóa |
| “`DELETE 1` nghĩa là chỉ mất một dòng trong cả database” | FK cascade/trigger có thể tác động bảng khác | Kiểm tra quan hệ và dữ liệu con |
| “SELECT trước rồi UPDATE sau luôn cùng tập” | Có giao dịch đồng thời | Khóa dòng, phiên bản, thao tác theo ID đã chụp |
| “Bọc transaction là chắc chắn đúng” | Transaction cũng có thể commit một thay đổi sai | Kiểm tra điều kiện trước commit |
| “`ROLLBACK` sửa được sau khi commit” | Commit đã hoàn tất thì transaction cũ không đảo lại được | Khôi phục/bù trừ có kiểm soát |
| “`RETURNING` xác nhận đã lưu” | Nó có thể chạy trong transaction chưa commit | Xác nhận COMMIT thành công |
| “Thêm `LIMIT 1` là đủ” | Có thể sửa một dòng sai; PostgreSQL không dùng cú pháp trực tiếp đó | Chọn đúng PK và guard row count |
| “Xóa vật lý account không ảnh hưởng hóa đơn” | `ON DELETE CASCADE` có thể xóa cả bảng con | Kiểm tra FK và lưu trữ nghiệp vụ |
| “`WHERE deleted_at = NULL` chọn dòng chưa xóa” | `= NULL` cho `UNKNOWN` | Dùng `IS NULL` |
| “Thiếu tham số thì điều kiện tùy chọn chỉ bỏ qua lọc vô hại” | `:id IS NULL OR ...` có thể chọn toàn bảng | Bắt buộc tham số ở API và SQL |
| “Trong `UPDATE FROM`, mỗi đích chỉ khớp một nguồn” | Join có thể thiếu khóa hoặc nguồn trùng | Đảm bảo khóa nguồn duy nhất |
| “Dùng `ROW_NUMBER` trước rồi cập nhật đủ an toàn” | Row number không phải khóa bền vững, thứ tự có thể thay đổi | Dùng PK và snapshot có `operation_id` |
| “Lệnh SQL không lỗi nghĩa là số dòng đúng” | `UPDATE 0` vẫn hợp lệ cú pháp và thực thi | Kiểm tra số dòng kỳ vọng |
| “`COUNT(*)` trước ghi là bằng chứng chắc chắn” | Tập có thể đổi do transaction khác | Guard ở lúc ghi, khóa/phiên bản hoặc isolation phù hợp |
| “Soft delete giống xóa thật” | Dữ liệu vẫn còn, query phải lọc | Thiết kế truy vấn và chính sách lưu trữ |
| “Safe update mode ngăn mọi sai sót” | Nó không hiểu ý nghĩa nghiệp vụ | Nhiều lớp kiểm tra độc lập |
| “Mọi hậu quả đều rollback được” | Sequence, email, API ngoài DB có quy tắc khác | Outbox/idempotency và phục hồi có kế hoạch |

## 27. Bài tập thực hành

Sử dụng **trạng thái gốc** của `safe_dml_accounts` và `safe_dml_invoices` ở mục 2 cho mỗi bài, trừ khi ghi rõ. Những bài có DML nên chạy trong `BEGIN ... ROLLBACK`. Với câu hỏi lý thuyết, hãy trả lời **số dòng dự kiến**, **khóa bị tác động** và **các kiểm tra bắt buộc**, không chỉ viết một câu `WHERE`.

### Bài 1 — Phân biệt câu nguy hiểm

So sánh:

```sql
UPDATE safe_dml_accounts SET status = 'CLOSED';
```

và:

```sql
UPDATE safe_dml_accounts
SET status = 'CLOSED'
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL;
```

Trên dữ liệu gốc, mỗi câu sẽ tác động bao nhiêu dòng? Vì sao `WHERE` ở câu hai phù hợp hơn?

### Bài 2 — Xem trước đúng tập đích

Hãy viết `SELECT` hiển thị các cột `account_id, tenant_id, status, credit_limit, version_no` trước khi đóng account 103 của tenant 10. Viết thêm `COUNT(*)` cùng điều kiện và dự đoán số dòng.

### Bài 3 — Transaction thử cập nhật

Viết `BEGIN`, câu `UPDATE ... RETURNING` đổi hạn mức account 102 thành 1400, `SELECT` kiểm tra và `ROLLBACK`. Sau khi rollback, hạn mức và phiên bản account 102 là bao nhiêu?

### Bài 4 — `DELETE` và cascade

Account 101 có bao nhiêu hóa đơn? Nếu chạy `DELETE FROM safe_dml_accounts WHERE account_id=101 RETURNING account_id` trong transaction, `RETURNING` có bao nhiêu dòng và bao nhiêu hóa đơn bị xóa dây chuyền? Điều gì xảy ra sau `ROLLBACK`?

### Bài 5 — Sai tenant

Viết câu `UPDATE` với `account_id=201 AND tenant_id=10`. Trên dữ liệu gốc, số dòng thực tế bị tác động là bao nhiêu? Ứng dụng nên báo gì nếu request dự kiến sửa đúng một dòng?

### Bài 6 — `WHERE 1=1`

Giải thích vì sao `WHERE 1=1` không làm một câu `DELETE` an toàn hơn việc bỏ `WHERE`. Nêu cách xác nhận một predicate thực sự chỉ chọn những ID được phê duyệt.

### Bài 7 — `NULL`

Truy vấn nào chọn tài khoản chưa xóa mềm?

```sql
WHERE deleted_at = NULL
```

hay:

```sql
WHERE deleted_at IS NULL
```

Vì sao?

### Bài 8 — Giới hạn số dòng

Một thao tác theo yêu cầu chỉ được đổi **một tài khoản**. Bạn gọi `UPDATE ... RETURNING`, nhưng kết quả trả **0 dòng**. Hãy nêu ít nhất ba nguyên nhân có thể xảy ra và cách xử lý.

### Bài 9 — `UPDATE ... FROM` thiếu khóa

Trong `safe_dml_limit_changes` có hai dòng thay đổi cho account 101 và 102. Vì sao câu:

```sql
UPDATE safe_dml_accounts AS a
SET credit_limit = s.new_credit_limit
FROM safe_dml_limit_changes AS s
WHERE a.tenant_id = 10;
```

không đúng? Viết điều kiện nối tối thiểu và phạm vi tenant cần thiết.

### Bài 10 — Soft delete

Viết câu `UPDATE` đánh dấu xóa mềm account 104 thuộc tenant 10, chỉ khi `deleted_at IS NULL`. Thêm `RETURNING` và `ROLLBACK`. Hóa đơn có bị cascade xóa bởi `UPDATE deleted_at` trong schema mẫu không?

### Bài 11 — Optimistic locking

Giả sử client đọc `version_no=1` của account 102, nhưng client khác đã tăng lên 2. Viết điều kiện `UPDATE` để tránh ghi đè thay đổi mới. Kết quả `RETURNING` có bao nhiêu dòng khi phiên bản không còn khớp?

### Bài 12 — Đếm có đủ không?

Batch cần cập nhật đúng `{101,102}`, nhưng `RETURNING` trả `{102,103}`. Cả hai đều có hai dòng. Vì sao vẫn phải `ROLLBACK`?

### Bài 13 — Khoảng thời gian nửa mở

Viết điều kiện chọn các bản ghi có `created_at` thuộc **tháng 6/2026 theo giờ Việt Nam**, bao gồm đúng đầu tháng 6 nhưng loại đúng đầu tháng 7. Vì sao không nên dùng `23:59:59`?

### Bài 14 — Chặn thiếu tham số

Tại sao câu `WHERE (:account_id IS NULL OR account_id=:account_id)` nguy hiểm trong thao tác xóa? Thiết kế đầu vào và truy vấn an toàn hơn cho API xóa một tài khoản.

### Bài 15 — Phân quyền

Một role chỉ cần sửa `credit_limit`, không cần xóa tài khoản. Hãy nêu nguyên tắc cấp quyền và giải thích vì sao cấp `UPDATE(credit_limit)` vẫn chưa đủ ngăn việc sửa cả bảng.

### Bài 16 — Đồng thời giữa preview và update

Người A xem `status='ACTIVE', version_no=1` của account 102. Trước khi A cập nhật, người B thay trạng thái hoặc tăng phiên bản. Vì sao `SELECT` trước không bảo đảm an toàn? Nêu hai kỹ thuật xử lý.

### Bài 17 — `LIMIT` không bảo đảm đúng người

Giả sử hệ quản trị cho `UPDATE ... LIMIT 1`. Vì sao nó vẫn có thể sửa sai đối tượng? Trong PostgreSQL, có thể chọn batch theo khóa như thế nào?

### Bài 18 — Kiểm chứng trước và sau commit

Hãy mô tả một quy trình cập nhật **chính xác 50 bản ghi được phê duyệt**: cần đối chiếu gì trước khi chạy, trong transaction và sau khi commit? Nếu chỉ sửa được 49 dòng thì nên làm gì?

### Bài 19 — Audit và khả năng phục hồi

Nếu một tác vụ hard delete được phê duyệt trên 100 account, bạn cần ghi/lưu những thông tin gì để giải thích thao tác và hỗ trợ phục hồi? `RETURNING` có thay thế backup không?

### Bài 20 — Thiết kế truy vấn an toàn theo chính sách

Yêu cầu: “Đóng các tài khoản **đã bị SUSPENDED**, **chưa xóa mềm**, thuộc tenant 10, và **chỉ chấp nhận khi số ứng viên từ 1 đến 2**.” Hãy mô tả hoặc viết CTE chụp tập khóa, đếm ứng viên, khóa các dòng cần thiết, cập nhật đúng tập đó và trả ID đã cập nhật. Nếu có 3 ứng viên, kết quả mong muốn là gì?

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Câu không `WHERE` tác động cả **6 dòng** nếu role có quyền; câu hai chỉ chọn account **103** (1 dòng) ở trạng thái gốc. Điều kiện khóa, tenant, trạng thái và `deleted_at` diễn đạt đúng mục tiêu.

**Bài 2:**

```sql
SELECT account_id, tenant_id, status, credit_limit, version_no
FROM safe_dml_accounts
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL;

SELECT COUNT(*) AS candidate_count
FROM safe_dml_accounts
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND deleted_at IS NULL;
-- 1.
```

**Bài 3:**

```sql
BEGIN;
UPDATE safe_dml_accounts
SET credit_limit = 1400,
    version_no = version_no + 1
WHERE account_id = 102
  AND tenant_id = 10
  AND version_no = 1
RETURNING account_id, credit_limit, version_no;
SELECT credit_limit, version_no
FROM safe_dml_accounts WHERE account_id = 102;
ROLLBACK;
```

Sau rollback về **1500 và phiên bản 1** nếu dữ liệu gốc chưa được thay đổi bởi câu đã commit khác.

**Bài 4:** Account 101 có **2 hóa đơn** (1001,1002). `DELETE ... RETURNING` trả **1 dòng tài khoản**, nhưng FK `ON DELETE CASCADE` xóa **2 hóa đơn** trong transaction. `ROLLBACK` phục hồi dữ liệu bảng và quan hệ đó.

**Bài 5:** **0 dòng** vì account 201 thuộc tenant 20. Nếu cần đúng một dòng, coi đây là **không đạt**, rollback/no-commit và xử lý sai phạm vi; không tự bỏ điều kiện tenant để “làm cho câu lệnh cập nhật được”.

**Bài 6:** `WHERE 1=1` luôn đúng, không giảm phạm vi. Cần preview khóa chính, đếm ứng viên, đối chiếu danh sách ID phê duyệt và kiểm tra `RETURNING` sau DML.

**Bài 7:** Dùng `IS NULL`. Phép `= NULL` có kết quả `UNKNOWN`, nên không khớp như mong muốn trong `WHERE`.

**Bài 8:** 0 dòng có thể do ID không tồn tại, sai tenant, trạng thái đã khác, `deleted_at` đã có giá trị hoặc `version_no` không còn khớp. Không tuyên bố thành công nếu kỳ vọng một dòng; kiểm tra nguyên nhân bằng truy vấn được phân quyền và có thể trả trạng thái conflict/not-found phù hợp.

**Bài 9:** Câu thiếu join theo ID, mỗi đích tenant 10 có thể khớp nhiều nguồn. Cần:

```sql
WHERE a.account_id = s.account_id
  AND a.tenant_id = s.tenant_id
  AND a.tenant_id = 10
```

và chỉ chấp nhận nguồn **duy nhất cho mỗi `(tenant_id,account_id)`**.

**Bài 10:**

```sql
BEGIN;
UPDATE safe_dml_accounts
SET deleted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    version_no = version_no + 1
WHERE account_id = 104
  AND tenant_id = 10
  AND deleted_at IS NULL
RETURNING account_id, deleted_at, version_no;
ROLLBACK;
```

Không có `DELETE` vật lý, nên **không kích hoạt FK `ON DELETE CASCADE`** trong schema mẫu.

**Bài 11:** Dùng `WHERE account_id=102 AND tenant_id=10 AND version_no=1` cùng các điều kiện trạng thái. Khi phiên bản đã thành 2, `UPDATE ... RETURNING` trả **0 dòng**, cần xử lý như xung đột phiên bản.

**Bài 12:** Dù số lượng bằng 2, **tập khóa khác dự kiến**: account 101 không được sửa, account 103 bị sửa nhầm. Phải rollback và điều tra predicate, không commit chỉ dựa vào row count.

**Bài 13:**

```sql
WHERE created_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND created_at < (
    TIMESTAMP '2026-07-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
```

Khoảng nửa mở bao gồm cả các thời điểm có mili/microsecond ngày 30/6; `23:59:59` có thể bỏ phần giây.

**Bài 14:** Nếu tham số `NULL`, biểu thức bên trái `OR` đúng cho mọi dòng. Hãy từ chối thiếu `account_id`, dùng bind parameters và `WHERE account_id=:account_id AND tenant_id=:tenant_id`, cộng kiểm tra quyền và `affected_rows=1`.

**Bài 15:** Chỉ cấp `SELECT`, `UPDATE(credit_limit)` trên bảng cần thiết, không cấp `DELETE`, `TRUNCATE` hoặc quyền quản trị nếu không cần. Nhưng quyền cập nhật cột vẫn cho phép sửa **nhiều dòng của cột ấy** khi `WHERE` rộng; cần kiểm soát ở SQL/API và có thể RLS bổ sung.

**Bài 16:** Dữ liệu có thể đổi giữa lúc đọc và ghi. Có thể sử dụng **optimistic locking** (`version_no` trong `WHERE`) hoặc khóa dòng **`SELECT ... FOR UPDATE` trong transaction**, cùng xác minh `RETURNING`/số dòng.

**Bài 17:** Giới hạn số dòng không chứng minh đúng đối tượng; thiếu khóa thứ tự còn làm chọn dòng không xác định. PostgreSQL có thể dùng CTE chọn các PK theo `ORDER BY` ổn định và `LIMIT`, rồi `UPDATE ... FROM candidates` theo khóa.

**Bài 18:** Trước: kiểm tra đúng 50 ID phê duyệt và trạng thái hiện có, các FK/trigger, snapshot. Trong transaction: cập nhật **đúng danh sách khóa**, `RETURNING` đủ 50 ID và đúng giá trị, kiểm tra bất biến liên quan. Nếu chỉ 49 thì **rollback**, phân tích ID thiếu; không tự commit lô thiếu khi chính sách là đủ 50. Sau commit: kiểm tra lại với đọc nhất quán, audit và operation ID.

**Bài 19:** Lưu operation ID, người thực hiện/phê duyệt, lý do, phạm vi tenant, danh sách ID, snapshot cần thiết của dữ liệu liên quan, số dòng trực tiếp/cascade, thời điểm và trạng thái commit, phiên bản schema/backup. `RETURNING` chỉ cho dữ liệu trực tiếp theo câu SQL, **không thay thế backup hoặc khả năng phục hồi đầy đủ**.

**Bài 20:** Dùng CTE `candidates` chụp các ID có `tenant_id=10`, `status='SUSPENDED'`, `deleted_at IS NULL` và `FOR UPDATE`; CTE `guard` đếm; CTE `UPDATE` chỉ nối vào `candidates` khi `COUNT BETWEEN 1 AND 2`, trả `account_id` qua `RETURNING`. Ví dụ hoàn chỉnh ở mục 10. Nếu có 3 ứng viên, **không sửa dòng nào**, kết quả trả 0 dòng; hệ thống phải xem đây là **guard từ chối** và không báo thành công.

</details>

## 28. Quy trình chuẩn có thể áp dụng khi vận hành

Trước mỗi thao tác sửa/xóa dữ liệu đáng kể, dùng khung tư duy:

```text
ĐỊNH NGHĨA
  - Đúng database/schema/tenant?
  - Mục tiêu nghiệp vụ và khóa đích là gì?
  - Dự kiến chính xác bao nhiêu dòng và giá trị nào?
  - Có FK/trigger hoặc chính sách lưu trữ liên quan không?
         │
         ▼
XEM TRƯỚC
  - SELECT các ID và trạng thái trước
  - COUNT tập ứng viên
  - Đối chiếu danh sách phê duyệt
  - Chuẩn bị snapshot / audit / phương án khôi phục
         │
         ▼
GIAO DỊCH
  - BEGIN
  - Chốt tập khóa, khóa dòng/kiểm tra version nếu cần
  - UPDATE hoặc DELETE với WHERE đầy đủ
  - RETURNING những ID và giá trị trực tiếp bị tác động
         │
         ▼
KIỂM CHỨNG
  - Đúng số dòng và đúng danh sách ID?
  - Trạng thái mới đúng?
  - Bảng liên quan/cascade đúng?
  - Không có thay đổi ngoài phạm vi?
         │
         ├── KHÔNG → ROLLBACK, điều tra và sửa kế hoạch
         │
         └── CÓ   → COMMIT, xác nhận thành công
                          │
                          ▼
                   ĐỌC LẠI / ĐỐI SOÁT
                   - Kiểm tra trạng thái đã commit
                   - Lưu operation ID / audit
                   - Ghi nhận kết quả và cảnh báo nếu có
```

Mẫu PostgreSQL ngắn nhất khi **chỉ sửa một tài khoản cụ thể**:

```sql
BEGIN;

-- 1. Kiểm tra dòng và khóa trong transaction.
SELECT account_id, tenant_id, status, version_no
FROM safe_dml_accounts
WHERE account_id = 103
  AND tenant_id = 10
FOR UPDATE;

-- 2. Cập nhật với các điều kiện bảo vệ.
UPDATE safe_dml_accounts
SET status = 'CLOSED',
    version_no = version_no + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = 103
  AND tenant_id = 10
  AND status = 'SUSPENDED'
  AND version_no = 1
  AND deleted_at IS NULL
RETURNING account_id, tenant_id, status, version_no;

-- 3. Người thực hiện hoặc ứng dụng PHẢI xác minh:
--    đúng 1 dòng, đúng account_id 103, status CLOSED, version_no 2.
--    Có sai khác thì ROLLBACK thay vì COMMIT.

ROLLBACK; -- Buổi thực hành: hủy thử nghiệm.
```

Trong hệ thống thật, bước kiểm tra phải được **thực thi như một điều kiện có khả năng chặn commit**, không chỉ là lời nhắc viết trong comment.

## 29. Kết luận

**Ngăn thao tác nhầm toàn bảng** không thể chỉ dựa vào việc có `WHERE`. Một câu `WHERE` đúng cú pháp nhưng quá rộng, một điều kiện join thiếu khóa, một tham số tùy chọn nhận `NULL` hoặc một FK có `ON DELETE CASCADE` đều có thể làm phạm vi thay đổi vượt xa ý định ban đầu.

Ba quy tắc cần nhớ:

1. **Định danh đúng trước khi ghi:** dùng khóa chính, tenant, trạng thái và phiên bản; xem trước **danh sách ID** và **số lượng kỳ vọng**.
2. **Kiểm chứng trước khi commit:** dùng transaction, `RETURNING`/row count, đối chiếu giá trị trước–sau và ảnh hưởng ở bảng liên quan; không đạt kỳ vọng thì **rollback**.
3. **Giảm phạm vi hậu quả:** phân quyền tối thiểu, tách thao tác hàng loạt, audit, chính sách soft/hard delete, khả năng phục hồi và cách xử lý đồng thời.

Một `UPDATE` hoặc `DELETE` thực sự an toàn khi không chỉ **thực thi thành công**, mà còn có thể trả lời và chứng minh được: **“Đã thay đổi chính xác những bản ghi nào, vì sao, theo quyền nào, với kết quả gì, và có thể đối soát hoặc phục hồi thế nào?”**
