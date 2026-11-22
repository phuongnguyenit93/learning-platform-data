# DELETE với EXISTS hoặc phép JOIN theo phương ngữ trong SQL

`DELETE` xóa những hàng đã lưu trong bảng. Với điều kiện đơn giản, ta chỉ cần `WHERE` trên chính bảng đích:

```sql
DELETE FROM messages
WHERE message_status = 'DRAFT';
```

Nhưng trong nhiều bài toán thực tế, việc xóa một hàng lại phụ thuộc vào **dữ liệu ở bảng khác**. Ví dụ:

- Xóa các bản nháp đã cũ **của những tài khoản không còn hoạt động**.
- Xóa dòng trong bảng trung gian khi khóa tương ứng xuất hiện trong danh sách thu hồi.
- Xóa tài khoản không hoạt động **chỉ khi không còn bản ghi liên quan**.
- Xóa những hàng đã được gắn cờ vi phạm bởi một bảng kiểm tra khác.
- Dọn lịch sử theo lô, với điều kiện trên bảng chính và các bảng liên quan.

Có hai cách diễn đạt rất thường dùng:

1. **`DELETE ... WHERE EXISTS (...)`**: xóa hàng đích nếu tồn tại ít nhất một hàng liên quan thỏa điều kiện; mẫu này khá dễ chuyển giữa nhiều DBMS.
2. **DELETE với phép JOIN**: kết nối bảng đích với bảng điều kiện. Cú pháp khác nhau đáng kể: PostgreSQL dùng `DELETE ... USING`; MySQL/MariaDB dùng `DELETE alias FROM target JOIN ...`; SQL Server cũng có `DELETE alias FROM target JOIN ...`; còn Oracle và SQLite thông dụng thường dùng `EXISTS`/truy vấn con khi cần điều kiện từ bảng khác.

Để xóa đúng, cần hiểu **bảng nào bị xóa**, **mối liên hệ nào quyết định hàng đích khớp**, tác động của **JOIN nhiều hàng**, **`NULL`**, ràng buộc **khóa ngoại**, giao dịch và mức độ an toàn khi chạy trên dữ liệu thật.

> Tất cả ví dụ tạo bảng và thực hành chung bên dưới viết cho **PostgreSQL**. Các ví dụ MySQL, SQL Server, Oracle, SQLite có nhãn riêng, sử dụng tên bảng minh họa tương đương và không có ý định chạy nguyên văn trong một phiên PostgreSQL. Lệnh `DELETE` làm mất dữ liệu: hãy dùng bảng thử, giao dịch/rollback và điều kiện được kiểm tra trước khi áp dụng lên hệ thống thật.

## 1. DELETE thay đổi dữ liệu, không giống SELECT

Cấu trúc cơ bản:

```sql
DELETE FROM target_table
WHERE condition;
```

Trong đó:

- `target_table` là **bảng có hàng sẽ bị xóa**.
- `WHERE condition` chọn những hàng đủ điều kiện.
- Nếu bỏ `WHERE`, câu lệnh thường nhắm **mọi hàng của bảng đích**, chịu các ràng buộc và quyền tương ứng.
- `DELETE` xóa hàng, không tự xóa định nghĩa bảng hay các chỉ mục của nó.

So với:

```sql
SELECT *
FROM target_table
WHERE condition;
```

`SELECT` chỉ xem các hàng ở một thời điểm truy vấn. `DELETE` là thay đổi dữ liệu và có thể kích hoạt trigger, kiểm tra FK, ghi log hoặc ảnh hưởng đến transaction.

**Quy tắc an toàn:** đừng bắt đầu với `DELETE` trên dữ liệu quan trọng khi chưa xác định rõ tập hàng dự kiến và cách hoàn tác. Luôn phân biệt việc “truy vấn trả đúng tập hàng để xem” và “truy vấn xóa đúng tập hàng trong một giao dịch”.

## 2. Dữ liệu mẫu tự chứa

Tạo ba bảng tạm PostgreSQL:

- `demo_accounts`: tài khoản, có trạng thái `ACTIVE` hoặc `INACTIVE`.
- `demo_messages`: lịch sử thông điệp của tài khoản.
- `demo_message_flags`: nhiều cờ kiểm duyệt có thể gắn cho cùng một thông điệp.

```sql
CREATE TEMP TABLE demo_accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    account_status TEXT NOT NULL
        CHECK (account_status IN ('ACTIVE', 'INACTIVE'))
);

CREATE TEMP TABLE demo_messages (
    message_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL
        REFERENCES demo_accounts(account_id),
    message_status TEXT NOT NULL
        CHECK (message_status IN ('DRAFT', 'SENT')),
    created_on DATE NOT NULL,
    body TEXT NOT NULL
);

CREATE TEMP TABLE demo_message_flags (
    flag_id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL
        REFERENCES demo_messages(message_id)
        ON DELETE CASCADE,
    flag_type TEXT NOT NULL
);

INSERT INTO demo_accounts
    (account_id, account_name, account_status)
VALUES
    (1, 'An',   'ACTIVE'),
    (2, 'Bình', 'INACTIVE'),
    (3, 'Chi',  'INACTIVE'),
    (4, 'Dũng', 'ACTIVE'),
    (5, 'Hà',   'INACTIVE');

INSERT INTO demo_messages
    (message_id, account_id, message_status, created_on, body)
VALUES
    (501, 1, 'DRAFT', DATE '2026-08-10', 'Draft by An'),
    (502, 2, 'DRAFT', DATE '2026-08-15', 'Old draft by Binh'),
    (503, 2, 'SENT',  DATE '2026-08-16', 'Sent by Binh'),
    (504, 3, 'DRAFT', DATE '2026-09-15', 'Old draft by Chi'),
    (505, 3, 'DRAFT', DATE '2026-10-15', 'Recent draft by Chi'),
    (506, 4, 'DRAFT', DATE '2026-07-04', 'Old draft by Dung'),
    (507, 2, 'DRAFT', DATE '2026-07-12', 'Another old draft'),
    (508, 3, 'SENT',  DATE '2026-09-01', 'Sent by Chi'),
    (509, 1, 'SENT',  DATE '2026-09-12', 'Sent by An');

INSERT INTO demo_message_flags (flag_id, message_id, flag_type)
VALUES
    (1001, 502, 'SPAM'),
    (1002, 502, 'REVIEW'),
    (1003, 504, 'SPAM'),
    (1004, 505, 'ARCHIVE'),
    (1005, 506, 'SPAM'),
    (1006, 503, 'REVIEW');
```

Bảng tài khoản:

| account_id | account_name | account_status |
|---:|---|---|
| 1 | An | ACTIVE |
| 2 | Bình | INACTIVE |
| 3 | Chi | INACTIVE |
| 4 | Dũng | ACTIVE |
| 5 | Hà | INACTIVE |

Bảng thông điệp:

| message_id | account_id | message_status | created_on |
|---:|---:|---|---|
| 501 | 1 | DRAFT | 2026-08-10 |
| 502 | 2 | DRAFT | 2026-08-15 |
| 503 | 2 | SENT | 2026-08-16 |
| 504 | 3 | DRAFT | 2026-09-15 |
| 505 | 3 | DRAFT | 2026-10-15 |
| 506 | 4 | DRAFT | 2026-07-04 |
| 507 | 2 | DRAFT | 2026-07-12 |
| 508 | 3 | SENT | 2026-09-01 |
| 509 | 1 | SENT | 2026-09-12 |

Thông điệp 502 có **hai cờ** (`SPAM` và `REVIEW`); điều này sẽ giúp quan sát hiện tượng phép `JOIN` tạo **hai dòng kết quả tạm**, trong khi một hàng đích chỉ bị xóa một lần.

Bài toán xuyên suốt:

> **Xóa thông điệp còn là `DRAFT`, được tạo trước ngày 2026-10-01 và thuộc tài khoản `INACTIVE`.**

Theo dữ liệu mẫu, những hàng cần xóa là **502, 504 và 507**.

- 502: tài khoản 2 không hoạt động, DRAFT, ngày 15/08.
- 504: tài khoản 3 không hoạt động, DRAFT, ngày 15/09.
- 507: tài khoản 2 không hoạt động, DRAFT, ngày 12/07.
- 505 được giữ vì là DRAFT của tài khoản không hoạt động nhưng tạo sau mốc giới hạn.
- 501 và 506 là DRAFT cũ nhưng tài khoản còn `ACTIVE`.
- 503, 508, 509 là `SENT`, không được xóa theo quy tắc này.
- Tài khoản 5 không có thông điệp; đây là dữ liệu minh họa cho `NOT EXISTS`.

Các câu `DELETE` tiếp theo là **những phương án thay thế cho cùng một yêu cầu**. Khi muốn chạy lại từng phương án và so sánh trên dữ liệu gốc, hãy dùng transaction rồi `ROLLBACK` hoặc tạo lại bảng mẫu; không chạy nối tiếp các lệnh xóa và mong mỗi lệnh đều xóa lại ba hàng.

## 3. Bắt đầu bằng SELECT để kiểm tra tập hàng đích

Trước khi xóa, viết câu `SELECT` diễn đạt cùng bộ lọc:

```sql
SELECT
    m.message_id,
    m.account_id,
    m.message_status,
    m.created_on,
    a.account_status
FROM demo_messages AS m
JOIN demo_accounts AS a
  ON a.account_id = m.account_id
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND a.account_status = 'INACTIVE'
ORDER BY m.message_id;
```

Kết quả:

| message_id | account_id | message_status | created_on | account_status |
|---:|---:|---|---|---|
| 502 | 2 | DRAFT | 2026-08-15 | INACTIVE |
| 504 | 3 | DRAFT | 2026-09-15 | INACTIVE |
| 507 | 2 | DRAFT | 2026-07-12 | INACTIVE |

Một truy vấn kiểm tra số lượng có thể giúp phát hiện thao tác bất thường:

```sql
SELECT COUNT(*) AS expected_delete_count
FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
-- expected_delete_count = 3
```

Nếu muốn xóa nhiều hơn hoặc ít hơn số hàng dự kiến, cần làm rõ điều kiện trước khi thực thi.

**Giới hạn của bước kiểm tra trước:** một `SELECT` và `DELETE` ở hai thời điểm có thể thấy dữ liệu khác nhau vì giao dịch khác đã sửa trạng thái tài khoản hay thông điệp. Xem trước giúp giảm lỗi logic nhưng **không tự tạo snapshot cố định**. Khi cần nhất quán nghiêm ngặt, phải dùng giao dịch, mức cô lập/khóa phù hợp và kiểm tra số hàng thực sự xóa.

## 4. Mẫu linh hoạt nhất: DELETE ... WHERE EXISTS

`EXISTS (subquery)` trả điều kiện **TRUE nếu truy vấn con có ít nhất một hàng**. Nó không cần truy vấn con trả đúng một hàng, và không quan tâm giá trị của `SELECT 1`. Mẫu tổng quát:

```sql
DELETE FROM target_table AS t
WHERE other_target_conditions
  AND EXISTS (
      SELECT 1
      FROM related_table AS r
      WHERE r.foreign_key = t.primary_key
        AND related_conditions
  );
```

### 4.1. Xóa bản nháp cũ của tài khoản không hoạt động

PostgreSQL:

```sql
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  )
RETURNING
    m.message_id, m.account_id, m.message_status, m.created_on;
```

Khi chạy trên dữ liệu mẫu còn nguyên, ba hàng được xóa có mã **502, 504, 507**.

Đọc ngữ nghĩa từng phần:

1. `DELETE FROM demo_messages AS m`: **chỉ các hàng của `demo_messages` là mục tiêu trực tiếp**.
2. `m.message_status = 'DRAFT'`: không động tới thông điệp đã gửi.
3. `m.created_on < DATE '2026-10-01'`: loại những bản nháp trước ngày 01/10; không bao gồm đúng ngày 01/10.
4. `EXISTS (...)`: chỉ xóa khi có một tài khoản `a` được liên kết.
5. `a.account_id = m.account_id`: điều kiện **tương quan**, gắn truy vấn con với thông điệp hiện tại.
6. `a.account_status = 'INACTIVE'`: tài khoản liên quan phải không hoạt động.
7. `RETURNING`: PostgreSQL trả thông tin các hàng bị xóa để đối soát; không nên dựa vào thứ tự trả về khi thiếu cơ chế sắp riêng.

Nếu cần cú pháp dễ chuyển qua nhiều DBMS, có thể bỏ `AS` ở alias cho bảng đích và bỏ `RETURNING`:

```sql
DELETE FROM demo_messages
WHERE message_status = 'DRAFT'
  AND created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts a
      WHERE a.account_id = demo_messages.account_id
        AND a.account_status = 'INACTIVE'
  );
```

**Lưu ý:** kiểu literal `DATE 'yyyy-mm-dd'`, cách đặt alias của bảng đích và khả năng trả hàng đã xóa vẫn khác theo DBMS; trong SQL Server/MySQL/SQLite có thể cần thay literal ngày hoặc cú pháp chi tiết. Điều gần portable là **cấu trúc `WHERE EXISTS`**, không phải bảo đảm một câu cụ thể chạy nguyên văn ở mọi hệ.

### 4.2. Vì sao EXISTS phù hợp cho quan hệ một-nhiều?

Giả sử một thông điệp có hai cờ ở `demo_message_flags`. Yêu cầu: “Xóa mọi thông điệp DRAFT đã bị gắn cờ `SPAM` hoặc `REVIEW`”.

```sql
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM demo_message_flags AS f
      WHERE f.message_id = m.message_id
        AND f.flag_type IN ('SPAM', 'REVIEW')
  )
RETURNING m.message_id;
```

Trên dữ liệu mẫu: **502, 504, 506**. Hai cờ của 502 không làm nó bị “xóa hai lần”; `EXISTS` chỉ trả lời **có hay không** một hàng liên quan phù hợp.

Với truy vấn con `EXISTS`:

- `SELECT 1` không có nghĩa “chỉ được trả một dòng”. Nó là một biểu thức không quan trọng về giá trị; `EXISTS` chỉ kiểm tra có hàng.
- `EXISTS` không đếm cờ, không đòi `DISTINCT` và không phụ thuộc vào số hàng cờ phù hợp.
- Bộ tối ưu có thể thực hiện dưới dạng **semi-join** hoặc kế hoạch khác, không nhất thiết chạy truy vấn con từ đầu cho từng hàng một.

### 4.3. Điều kiện tương quan là điểm quan trọng nhất

Sai lầm nguy hiểm:

```sql
-- SAI: không liên kết tài khoản a với thông điệp m.
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_status = 'INACTIVE'
  );
```

Vì **có ít nhất một tài khoản `INACTIVE` trong toàn bảng**, `EXISTS` luôn đúng cho **mọi thông điệp DRAFT**, kể cả tài khoản đang `ACTIVE`. Nó có thể xóa 501 và 506 ngoài ý muốn.

Cách sửa là thêm **điều kiện liên kết bắt buộc**:

```sql
WHERE a.account_id = m.account_id
  AND a.account_status = 'INACTIVE'
```

Trong hệ đa tenant, liên kết có thể cần **cả `tenant_id` và `account_id`**. Quên khóa tenant khiến câu xóa có thể dùng trạng thái từ tài khoản thuộc tenant khác, tạo rủi ro dữ liệu và phân quyền.

### 4.4. Nhiều điều kiện liên quan

Có thể yêu cầu tồn tại tài khoản không hoạt động **và** thông điệp bị gắn cờ. Dùng hai `EXISTS`:

```sql
SELECT m.message_id
FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  )
  AND EXISTS (
      SELECT 1
      FROM demo_message_flags AS f
      WHERE f.message_id = m.message_id
        AND f.flag_type = 'SPAM'
  )
ORDER BY m.message_id;
-- 502, 504.
```

Đây là **SELECT kiểm tra**. Nếu điều kiện đúng nghiệp vụ, có thể thay `SELECT ... FROM demo_messages m` bằng `DELETE FROM demo_messages m` (và dùng `RETURNING` nếu PostgreSQL). Cách tách thành hai `EXISTS` giúp thấy rõ yêu cầu: phải có cả tài khoản không hoạt động và ít nhất một cờ SPAM.

## 5. DELETE ... WHERE NOT EXISTS: xóa khi không còn liên hệ

`NOT EXISTS` đúng khi truy vấn con **không có hàng**.

Ví dụ: “Xóa tài khoản `INACTIVE` không có bất kỳ thông điệp nào”.

```sql
DELETE FROM demo_accounts AS a
WHERE a.account_status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM demo_messages AS m
      WHERE m.account_id = a.account_id
  )
RETURNING a.account_id, a.account_name;
```

Trên bộ dữ liệu mẫu ban đầu, chỉ **tài khoản 5 (Hà)** bị xóa.

Tại sao mẫu này an toàn hơn cách chỉ dựa trên trạng thái?

- Tài khoản 2 và 3 đang `INACTIVE` nhưng **vẫn có thông điệp**.
- Điều kiện `NOT EXISTS` giữ những tài khoản đó.
- Tài khoản 5 `INACTIVE` và **không có thông điệp**, nên được chọn.
- Tài khoản 1 và 4 `ACTIVE` nên không bị xóa.

### 5.1. NOT EXISTS và NULL

So sánh với:

```sql
DELETE FROM demo_accounts
WHERE account_id NOT IN (
    SELECT account_id
    FROM demo_messages
);
```

Đoạn trên còn **thiếu điều kiện `INACTIVE`**, nên không tương đương với yêu cầu. Hơn nữa, nếu truy vấn con `NOT IN` trả một giá trị SQL `NULL`, phép so sánh có thể cho kết quả `UNKNOWN` và khiến nhiều hàng không được chọn theo cách người viết không mong đợi.

Trong **bảng mẫu**, `demo_messages.account_id` được khai báo `NOT NULL` nên không có `NULL` trong cột đó; tuy nhiên khi chuyển sang staging/bảng lịch sử khác chưa có ràng buộc, nguy cơ `NULL` là thật.

Với câu hỏi “không có hàng liên quan”, `NOT EXISTS` thường dễ diễn đạt hơn vì quan hệ được viết trực tiếp:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM child AS c
    WHERE c.parent_id = parent.id
)
```

### 5.2. Không có hàng con theo snapshot không phải bảo đảm vĩnh viễn

Trong môi trường đồng thời, sau khi câu `NOT EXISTS` xét tập hiện tại, giao dịch khác có thể chèn bản ghi liên quan. FK, khóa và mức cô lập quyết định kết quả được phép. Không dùng một lần kiểm tra `NOT EXISTS` rồi vài giây sau xóa bằng một câu lệnh khác mà không xét cạnh tranh ghi.

Việc giữ điều kiện trong **cùng lệnh `DELETE`** giúp DBMS xử lý kiểm tra và thao tác theo ngữ nghĩa của một statement, nhưng không thay thế chiến lược đồng thời cho mọi luồng nghiệp vụ.

## 6. PostgreSQL: DELETE ... USING

PostgreSQL cung cấp cú pháp xóa với bảng liên quan trong `USING`:

```sql
DELETE FROM target_table AS t
USING related_table AS r
WHERE t.key = r.key
  AND other_conditions;
```

`USING` đưa bảng liên quan vào điều kiện của `DELETE`. Nó tương tự hình thức JOIN trong các câu `SELECT`, nhưng **chỉ bảng được nêu sau `DELETE FROM` là mục tiêu xóa trực tiếp**.

### 6.1. Cùng bài toán, viết bằng USING

```sql
DELETE FROM demo_messages AS m
USING demo_accounts AS a
WHERE a.account_id = m.account_id
  AND a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
RETURNING m.message_id, m.account_id;
```

Nếu chạy trên dữ liệu ban đầu, kết quả là các mã **502, 504, 507**, giống mẫu `WHERE EXISTS`.

Cách đọc:

- `DELETE FROM demo_messages AS m`: bảng đích là `demo_messages`.
- `USING demo_accounts AS a`: bảng phụ để chọn điều kiện.
- `a.account_id = m.account_id`: điều kiện liên kết giữa đích và bảng phụ.
- Ba điều kiện còn lại giới hạn tập hàng bị xóa.

Cú pháp `USING` của PostgreSQL **không có nghĩa** “xóa cả `demo_accounts`”. Nếu tài khoản không có `ON DELETE CASCADE` thích hợp, hàng tài khoản vẫn tồn tại sau khi xóa thông điệp. Những thay đổi gián tiếp đến bảng khác chỉ xảy ra theo FK/trigger được khai báo, không phải vì chúng xuất hiện trong `USING`.

### 6.2. USING nhiều bảng

Ví dụ xóa các bản nháp cũ của tài khoản không hoạt động **và** bị đánh dấu SPAM:

```sql
DELETE FROM demo_messages AS m
USING demo_accounts AS a,
      demo_message_flags AS f
WHERE a.account_id = m.account_id
  AND f.message_id = m.message_id
  AND a.account_status = 'INACTIVE'
  AND f.flag_type = 'SPAM'
  AND m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
RETURNING m.message_id;
```

Kết quả trên dữ liệu mẫu: **502, 504**.

Có thể viết tương đương với một `EXISTS` chứa JOIN giữa `a` và `f`, hoặc hai `EXISTS` riêng. Dùng hình thức nào dễ hiểu nhất với điều kiện nghiệp vụ.

### 6.3. Nguy cơ thiếu điều kiện nối trong USING

Đoạn sau nguy hiểm:

```sql
-- SAI: thiếu quan hệ a.account_id = m.account_id.
DELETE FROM demo_messages AS m
USING demo_accounts AS a
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT';
```

Nếu có bất kỳ tài khoản nào không hoạt động, phép kết hợp sẽ tạo hàng khớp cho nhiều thông điệp `DRAFT` **bất kể chúng thuộc ai**. Vì thế, lỗi thiếu một điều kiện JOIN trong `DELETE` nguy hiểm hơn lỗi SELECT: hậu quả là xóa dữ liệu.

Khi dùng nhiều bảng trong `USING`, hãy đảm bảo từng bảng được liên kết qua **đúng khóa** và tập hàng được kiểm tra bằng `SELECT` tương đương.

## 7. Một hàng đích khớp nhiều hàng JOIN thì sao?

Trong dữ liệu mẫu, thông điệp 502 có hai hàng ở `demo_message_flags`:

```sql
SELECT m.message_id, f.flag_id, f.flag_type
FROM demo_messages AS m
JOIN demo_message_flags AS f
  ON f.message_id = m.message_id
WHERE m.message_id = 502
ORDER BY f.flag_id;
```

Kết quả:

| message_id | flag_id | flag_type |
|---:|---:|---|
| 502 | 1001 | SPAM |
| 502 | 1002 | REVIEW |

Truy vấn `SELECT JOIN` có **hai hàng**. Nhưng một `DELETE` từ bảng `demo_messages` dựa trên điều kiện khớp nhiều hàng phụ **không xóa cùng một hàng đích hai lần**.

PostgreSQL:

```sql
DELETE FROM demo_messages AS m
USING demo_message_flags AS f
WHERE f.message_id = m.message_id
  AND f.flag_type IN ('SPAM', 'REVIEW')
  AND m.message_status = 'DRAFT'
RETURNING m.message_id;
```

Hàng đích 502 chỉ xuất hiện một lần trong tập **hàng đã xóa**, mặc dù có hai cờ phù hợp. Các mã xóa trên dữ liệu mẫu là **502, 504, 506**.

**Quan trọng:** Nếu truy vấn có `JOIN` được dùng để tính toán/cập nhật giá trị từ các hàng phụ, việc nhiều hàng khớp có thể gây mơ hồ hoặc nhân kết quả trung gian. Với `DELETE`, kết quả “một hàng đích bị xóa một lần” không cho phép bỏ qua việc kiểm tra cardinality, đặc biệt khi bạn đếm hàng bằng một truy vấn `SELECT JOIN`.

Nếu muốn xem đúng **số thông điệp sẽ xóa**, tránh:

```sql
SELECT COUNT(*)
FROM demo_messages AS m
JOIN demo_message_flags AS f
  ON f.message_id = m.message_id
WHERE f.flag_type IN ('SPAM', 'REVIEW')
  AND m.message_status = 'DRAFT';
```

Vì thông điệp 502 có hai cờ, `COUNT(*)` có thể **đếm lặp**. Dùng `COUNT(DISTINCT m.message_id)` hoặc `COUNT(*)` trên tập đã lọc bằng `EXISTS`:

```sql
SELECT COUNT(*) AS target_rows
FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM demo_message_flags AS f
      WHERE f.message_id = m.message_id
        AND f.flag_type IN ('SPAM', 'REVIEW')
  );
-- 3
```

**Kết luận phần này:** `JOIN` có thể tạo nhiều cặp khớp, còn `EXISTS` diễn đạt ngay ý nghĩa “chỉ cần một cặp khớp” và giúp bước preview không bị nhân hàng.

## 8. So sánh EXISTS và JOIN cho thao tác DELETE

| Khía cạnh | `DELETE ... WHERE EXISTS` | `DELETE` với JOIN/`USING` |
|---|---|---|
| Ý định | Xóa nếu **tồn tại** hàng liên quan | Xóa theo tập hàng khớp điều kiện nối |
| Tính dễ chuyển DBMS | Tương đối cao; cú pháp chi tiết vẫn cần điều chỉnh | Thay đổi lớn theo PostgreSQL/MySQL/SQL Server |
| Quan hệ một-nhiều | Không tạo thêm dòng trong phép kiểm tra tồn tại | JOIN trung gian có thể có nhiều dòng mỗi hàng đích |
| Dễ quên điều kiện tương quan | Có; có thể xóa quá rộng | Có; thiếu `ON`/`WHERE` nối có thể tạo cross join |
| Có thể dùng nhiều bảng phụ | Có, bằng nhiều `EXISTS` hoặc JOIN trong subquery | Có, nếu dialect hỗ trợ |
| Dễ đọc khi quy tắc “có ít nhất một” | Thường rất rõ | Có thể dài hoặc tạo thêm các kết hợp không cần |
| Hiệu năng | Phụ thuộc optimizer, chỉ mục, thống kê và dữ liệu | Cũng phụ thuộc optimizer, không luôn tốt hơn |
| Bảng nào bị xóa? | Bảng sau `DELETE FROM` | Phụ thuộc cú pháp đích; đặc biệt MySQL có multi-table delete |

Không có định luật rằng `EXISTS` luôn nhanh hơn `JOIN` hoặc ngược lại. Nhiều bộ tối ưu có thể chuyển đổi `EXISTS` thành semi-join hoặc xây kế hoạch tương đương. Vì `DELETE` là thao tác ghi và có hậu quả lớn, **sự rõ ràng về mục tiêu và tập hàng thường quan trọng hơn tiết kiệm một vài ký tự SQL**.

## 9. MySQL/MariaDB: DELETE với JOIN

MySQL và MariaDB hỗ trợ cú pháp **multi-table DELETE**. Khi muốn xóa hàng của **một bảng đích** dựa trên quan hệ JOIN, dạng thường thấy là:

```sql
DELETE target_alias
FROM target_table AS target_alias
JOIN related_table AS related_alias
  ON related_alias.key = target_alias.key
WHERE conditions;
```

### 9.1. Ví dụ tương đương trên MySQL/MariaDB

Giả sử có bảng `messages` và `accounts` với những cột tương ứng:

```sql
-- MySQL / MariaDB
DELETE m
FROM messages AS m
INNER JOIN accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < '2026-10-01';
```

`DELETE m` xác định **alias bảng đích sẽ bị xóa**. `FROM messages AS m INNER JOIN accounts AS a` tạo quan hệ xác định hàng khớp. `accounts` không bị xóa chỉ vì xuất hiện sau `JOIN`.

Một biến thể cú pháp thường dùng của MySQL có dạng:

```sql
DELETE FROM m
USING messages AS m
INNER JOIN accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < '2026-10-01';
```

**Không nhầm hai phương ngữ**:

- PostgreSQL: `DELETE FROM messages AS m USING accounts AS a WHERE ...`.
- MySQL/MariaDB: `DELETE m FROM messages AS m JOIN accounts AS a ON ... WHERE ...` hoặc dạng `DELETE FROM m USING ...`.

Cùng từ `USING` nhưng cấu trúc khác và không thể hoán đổi máy móc. Dạng `DELETE FROM m USING ...` của MySQL có **danh sách bảng/alias đích** riêng; không phải viết trực tiếp một bảng phụ sau `USING` giống PostgreSQL.

### 9.2. MySQL có thể xóa từ nhiều bảng cùng một câu

MySQL/MariaDB còn cho phép liệt kê **nhiều alias bảng đích**:

```sql
-- MySQL/MariaDB: minh họa cú pháp, KHÔNG chạy trên dữ liệu thật.
DELETE m, f
FROM messages AS m
JOIN message_flags AS f ON f.message_id = m.message_id
WHERE m.message_status = 'DRAFT'
  AND f.flag_type = 'SPAM';
```

Khác ví dụ trước, đoạn này yêu cầu xóa hàng từ cả `messages` **và** `message_flags`, tùy những hàng khớp và các ràng buộc. Nó có thể gặp vấn đề về thứ tự kiểm tra khóa ngoại khi hai bảng có quan hệ cha-con; đặc biệt không nên xóa cả hai một cách tùy tiện khi `ON DELETE CASCADE` đã được thiết kế.

Bài học này chủ yếu tập trung vào **DELETE một bảng đích dựa trên điều kiện bảng khác**. Khi cần dọn dữ liệu liên quan, ưu tiên phân tích FK và kế hoạch xóa an toàn thay vì thêm tất cả alias vào `DELETE`.

### 9.3. Giới hạn ORDER BY / LIMIT của multi-table DELETE

Trong MySQL, cú pháp **single-table DELETE** có thể hỗ trợ `ORDER BY` và `LIMIT`:

```sql
-- MySQL: ví dụ xóa một số hàng từ một bảng theo điều kiện.
DELETE FROM messages
WHERE message_status = 'DRAFT'
ORDER BY message_id
LIMIT 100;
```

Tuy nhiên, **multi-table DELETE** dạng `DELETE m FROM ... JOIN ...` không hỗ trợ `ORDER BY`/`LIMIT` trực tiếp theo quy tắc cùng loại. Để xóa theo lô với điều kiện JOIN, cần chọn khóa đích qua bước/truy vấn phù hợp và xử lý giới hạn MySQL về đọc/chỉnh sửa cùng bảng, hoặc dùng transaction và công cụ điều phối. Không ghép `LIMIT 100` vào cuối multi-table DELETE rồi cho rằng nó portable.

Dù MySQL có thể xóa theo thứ tự ở single-table form, `ORDER BY` không phải cơ chế chọn “100 hàng bất kỳ” một cách vô hại. Hãy quy định khóa sắp có ý nghĩa, ghi nhận kết quả và kiểm soát cạnh tranh ghi.

### 9.4. MySQL và MariaDB không giống nhau ở mọi tính năng

Hai hệ có nhiều cú pháp chung nhưng đã phát triển độc lập. Mức hỗ trợ `RETURNING`, xử lý khóa, quyền, optimizer, default transaction/storage engine và tính năng liên quan `ORDER BY/LIMIT` có thể khác phiên bản. Khi dùng MariaDB, kiểm tra tài liệu MariaDB đúng phiên bản thay vì suy từ MySQL hiện đại.

## 10. SQL Server: DELETE alias FROM ... JOIN ...

T-SQL có dạng gần với MySQL nhưng là **cú pháp SQL Server**:

```sql
-- SQL Server, giả sử có dbo.messages và dbo.accounts.
DELETE m
FROM dbo.messages AS m
INNER JOIN dbo.accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < CONVERT(date, '2026-10-01', 23);
```

Trong ví dụ:

- `DELETE m`: chọn alias `m` làm mục tiêu.
- `FROM dbo.messages AS m INNER JOIN ...`: tạo nguồn nối.
- `WHERE`: lọc theo cả bảng đích và bảng phụ.

Đây là mẫu phổ biến của SQL Server, nhưng không được hiểu là MySQL và SQL Server có chung toàn bộ ngữ nghĩa của mọi cú pháp xóa.

### 10.1. OUTPUT DELETED: lấy dữ liệu đã xóa trong T-SQL

Trong SQL Server, có thể dùng `OUTPUT DELETED...` để trả các cột của hàng bị xóa:

```sql
-- SQL Server
DELETE m
OUTPUT DELETED.message_id,
       DELETED.account_id
FROM dbo.messages AS m
INNER JOIN dbo.accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < CONVERT(date, '2026-10-01', 23);
```

`DELETED` là bảng logic của SQL Server chứa ảnh chụp các hàng đích bị xóa tại giai đoạn liên quan của câu lệnh. Cú pháp `OUTPUT` khác PostgreSQL `RETURNING` và có hạn chế riêng về trigger/đích xuất.

Không dùng `OUTPUT DELETED` như một phép backup lâu dài; nếu cần lịch sử xóa đáng tin, hãy thiết kế audit table hoặc cơ chế ghi nhận hợp lệ trong cùng transaction.

### 10.2. DELETE TOP (N) không tự xác định thứ tự

SQL Server hỗ trợ `TOP` trong `DELETE`:

```sql
-- SQL Server: không chỉ rõ 100 hàng nào nếu chỉ dựa vào TOP.
DELETE TOP (100)
FROM dbo.messages
WHERE message_status = 'DRAFT';
```

`TOP (100)` giới hạn số hàng, nhưng **không tự xác định tập 100 hàng theo một thứ tự cụ thể**. Muốn chọn các hàng có `message_id` nhỏ nhất hoặc ngày cũ nhất, cần xây tập khóa có `ORDER BY` trong CTE/truy vấn con phù hợp, rồi xóa theo tập khóa ấy.

Với SQL Server, cách thường gặp là một CTE chọn `TOP (100) ... ORDER BY ...` rồi `DELETE` các hàng tương ứng theo khóa, hoặc dùng kỹ thuật table variable/temp table cho lô. Cần kiểm tra plan và cạnh tranh ghi trước khi dùng trên bảng lớn.

### 10.3. Nếu điều kiện chỉ là tồn tại, EXISTS vẫn tốt

```sql
-- SQL Server, không cần DELETE JOIN.
DELETE FROM dbo.messages
WHERE message_status = 'DRAFT'
  AND created_on < CONVERT(date, '2026-10-01', 23)
  AND EXISTS (
      SELECT 1
      FROM dbo.accounts AS a
      WHERE a.account_id = dbo.messages.account_id
        AND a.account_status = 'INACTIVE'
  );
```

Đây là lý do `WHERE EXISTS` thường là điểm xuất phát tốt khi viết SQL cần hoạt động trên nhiều hệ: nó tập trung vào **điều kiện tồn tại**, không vào cách từng DBMS biểu diễn JOIN trong câu `DELETE`.

## 11. Oracle Database: ưu tiên EXISTS hoặc truy vấn con

Với các phiên bản Oracle Database thông dụng, mẫu portable là `DELETE FROM ... WHERE EXISTS (...)`. Không nên sao chép nguyên dạng `DELETE FROM ... USING` của PostgreSQL hoặc `DELETE alias FROM ... JOIN ...` của MySQL/SQL Server vào Oracle.

```sql
-- Oracle Database: bảng MESSAGES và ACCOUNTS có cột tương ứng.
DELETE FROM messages m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM accounts a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
```

`DELETE FROM messages m` dùng alias bảng đích trong cách viết Oracle; không cần từ `AS`. Điều kiện tương quan vẫn là `a.account_id = m.account_id`.

### 11.1. Khi xóa phụ thuộc nhiều bảng

Oracle hỗ trợ truy vấn con có `JOIN`:

```sql
-- Oracle: xóa thông điệp DRAFT có cờ SPAM.
DELETE FROM messages m
WHERE m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM message_flags f
      WHERE f.message_id = m.message_id
        AND f.flag_type = 'SPAM'
  );
```

Oracle có những cơ chế xóa qua view/inline view trong một số trường hợp **key-preserved** và các quy tắc riêng về khả năng cập nhật của view. Nhưng với bài toán “xóa bảng đích theo sự tồn tại ở bảng phụ”, `EXISTS` rõ và ít phụ thuộc các điều kiện updatable view hơn.

### 11.2. RETURNING khác PostgreSQL

Oracle hỗ trợ `DELETE ... RETURNING ... INTO` trong những bối cảnh/kiểu bind phù hợp, thường qua PL/SQL hoặc driver. Nó **không phải** cách gọi `RETURNING message_id` rồi tự nhận result set như PostgreSQL.

Nếu một chương trình Oracle cần biết số hàng đã xóa, có thể sử dụng thông tin affected rows của driver/SQL%ROWCOUNT và cơ chế audit/returning theo API tương ứng. Không dựa vào cú pháp PostgreSQL khi viết JDBC cho Oracle.

## 12. SQLite: DELETE với EXISTS, không có DELETE JOIN dạng phổ biến

SQLite hỗ trợ xóa có `WHERE` và điều kiện `EXISTS`:

```sql
-- SQLite: giả sử messages và accounts có cùng tên cột.
DELETE FROM messages
WHERE message_status = 'DRAFT'
  AND created_on < '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM accounts AS a
      WHERE a.account_id = messages.account_id
        AND a.account_status = 'INACTIVE'
  );
```

Không có cú pháp đa bảng `DELETE m FROM messages m JOIN accounts ...` như MySQL/T-SQL hay `DELETE FROM messages USING accounts ...` như PostgreSQL.

### 12.1. Ngày trong SQLite cần được biểu diễn nhất quán

SQLite thường lưu ngày/thời gian dưới dạng **TEXT, INTEGER hoặc REAL**, không có đúng kiểu `DATE`/`TIMESTAMPTZ` độc lập như PostgreSQL. Ví dụ ở trên giả định `created_on` là chuỗi ISO-8601 `YYYY-MM-DD` nhất quán, để phép so sánh chuỗi theo thứ tự từ điển khớp thứ tự ngày.

Nếu dữ liệu chứa dạng `DD/MM/YYYY` hoặc nhiều kiểu offset, phép so sánh văn bản có thể sai; cần chuẩn hóa và sử dụng hàm ngày/giờ phù hợp trước khi xóa.

### 12.2. RETURNING và LIMIT theo phiên bản/cấu hình

SQLite từ **3.35.0** hỗ trợ mệnh đề `RETURNING` cho `DELETE`:

```sql
-- SQLite 3.35.0+, giả sử bảng và dữ liệu phù hợp.
DELETE FROM messages
WHERE message_status = 'DRAFT'
RETURNING message_id, account_id;
```

SQLite chỉ hỗ trợ `ORDER BY`/`LIMIT` trực tiếp trong `DELETE` ở những bản dựng có tùy chọn biên dịch `SQLITE_ENABLE_UPDATE_DELETE_LIMIT` phù hợp. Không mặc định cú pháp đó chạy trên mọi SQLite embedded.

Ngay cả khi tính năng `DELETE ... ORDER BY ... LIMIT` được bật, thứ tự hàng trong `RETURNING` không nhất thiết phản ánh `ORDER BY` của DELETE. Khi cần batch cố định, nên chọn khóa theo truy vấn con với thứ tự rõ rồi xóa qua khóa, và kiểm tra hành vi trên phiên bản đang dùng.

### 12.3. Bật kiểm tra foreign key khi cần

Trong SQLite, kiểm tra FK phải được cấu hình đúng trên **từng kết nối** theo phiên bản/chính sách ứng dụng. Không dựa vào việc có `REFERENCES` trong schema để suy rằng mọi kết nối đều đang thực thi cascade/restrict như mong đợi. Cần kiểm tra `PRAGMA foreign_keys` và môi trường ứng dụng trước khi chạy thao tác dọn dữ liệu.

## 13. Bảng tóm tắt cú pháp theo hệ quản trị

Cùng yêu cầu “xóa thông điệp DRAFT cũ của tài khoản INACTIVE”, cách diễn đạt thường là:

| Hệ quản trị | Mẫu cú pháp | Ghi chú |
|---|---|---|
| **PostgreSQL** | `DELETE FROM messages m USING accounts a WHERE ...` | `USING` đưa bảng phụ vào điều kiện; xóa bảng đích |
| **MySQL / MariaDB** | `DELETE m FROM messages m JOIN accounts a ON ... WHERE ...` | Có hỗ trợ multi-table DELETE; liệt kê alias đích rõ ràng |
| **SQL Server** | `DELETE m FROM dbo.messages m JOIN dbo.accounts a ON ... WHERE ...` | Có `OUTPUT DELETED` |
| **Oracle Database** | `DELETE FROM messages m WHERE EXISTS (SELECT 1 FROM accounts a WHERE ...)` | Mẫu tương quan phổ biến; cú pháp RETURNING riêng |
| **SQLite** | `DELETE FROM messages WHERE EXISTS (SELECT 1 FROM accounts a WHERE ...)` | Không dùng DELETE JOIN giống MySQL; RETURNING tùy phiên bản |

**Mẫu `EXISTS`** có thể dùng trên tất cả các hệ trên, khi điều chỉnh alias, literal, kiểu dữ liệu và các mệnh đề trả kết quả theo đúng DBMS. Đó thường là lựa chọn tốt khi muốn diễn đạt đúng nghiệp vụ trước khi tối ưu.

## 14. FOREIGN KEY và ON DELETE: xóa bảng đích có thể tác động bảng khác

Câu lệnh `DELETE` không thể tách rời thiết kế quan hệ.

Ở dữ liệu mẫu:

```text
demo_accounts (cha)
      |
      | demo_messages.account_id REFERENCES demo_accounts.account_id
      v
demo_messages (con)
      |
      | demo_message_flags.message_id REFERENCES demo_messages.message_id
      |                         ON DELETE CASCADE
      v
demo_message_flags (con của messages)
```

Ta đã định nghĩa:

```sql
message_id INTEGER NOT NULL
    REFERENCES demo_messages(message_id)
    ON DELETE CASCADE
```

nên khi xóa thông điệp 502, các hàng cờ 1001 và 1002 tham chiếu 502 **cũng bị xóa theo FK cascade**. Khi xóa thông điệp 504, cờ 1003 bị xóa. Đây là **tác động gián tiếp của FK**, không phải vì câu `DELETE` đã chọn bảng `demo_message_flags` làm mục tiêu.

### 14.1. Nếu FK không có CASCADE?

Nếu bảng `message_flags` tham chiếu `messages` bằng khóa ngoại có hành động `RESTRICT`/`NO ACTION` theo quy tắc DBMS, thao tác xóa thông điệp đang có cờ có thể **bị từ chối**.

Các lựa chọn theo nghiệp vụ:

- Không xóa thông điệp còn cờ.
- Xóa các hàng con hợp lệ trước, sau đó xóa cha trong một transaction.
- Sử dụng `ON DELETE CASCADE` nếu việc xóa hàng con cùng cha là quy tắc được chấp nhận.
- Dùng lưu trữ mềm (*soft delete*) nếu cần giữ lịch sử/audit.

Không sửa FK thành `CASCADE` chỉ vì câu `DELETE` báo lỗi; cần xác định hậu quả dữ liệu và chính sách lưu trữ.

### 14.2. Xóa tài khoản cha có thể bị chặn

Bảng `demo_messages` tham chiếu `demo_accounts` nhưng **không khai báo `ON DELETE CASCADE`**. Vì vậy, xóa tài khoản 2 khi vẫn có thông điệp liên quan sẽ không được phép theo kiểm tra FK mặc định, thay vì tự xóa tất cả thông điệp.

Mẫu `NOT EXISTS` ở phần 5 chọn tài khoản 5 vì **không có thông điệp**, nên phù hợp với ràng buộc này. Với hệ thống thực tế, ngay cả khi một câu `SELECT NOT EXISTS` trước đó cho thấy tài khoản rỗng, FK tại DBMS vẫn cần là lớp bảo vệ khi có giao dịch khác chèn hàng con.

### 14.3. Trigger và lịch sử xóa

Một trigger `BEFORE DELETE`/`AFTER DELETE` có thể kiểm tra điều kiện thêm hoặc ghi log. Câu `DELETE` có thể xóa ít hàng hơn hoặc bị từ chối tùy trigger/DBMS. Vì vậy, số hàng dự kiến từ `SELECT` chưa chắc khớp số hàng tác động thực tế trong mọi schema.

Nếu bảng có audit, soft deletion, temporal/history tables hoặc replication, cần xem tác động dây chuyền; câu lệnh đúng cú pháp chưa đủ chứng minh thao tác phù hợp chính sách giữ dữ liệu.

## 15. Kiểm tra trước, xóa trong transaction, rồi đối soát

Trong PostgreSQL, một quy trình thử an toàn là bắt đầu giao dịch, dùng `DELETE ... RETURNING` để quan sát, rồi **`ROLLBACK`** nếu đang kiểm tra.

```sql
BEGIN;

-- Bước 1: xem tập dự kiến.
SELECT
    m.message_id, m.account_id, m.created_on
FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1 FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  )
ORDER BY m.message_id;

-- Bước 2: thao tác đúng cùng điều kiện.
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1 FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  )
RETURNING m.message_id, m.account_id;

-- Bước 3: chỉ dùng ROLLBACK cho bài thử.
ROLLBACK;
```

Đây là ví dụ kiểm tra. Nếu muốn lưu thay đổi **thực sự**, quy trình vận hành riêng cần xét quyền, snapshot, số hàng, tác động FK và dùng `COMMIT` thay cho `ROLLBACK` theo cơ chế phê duyệt thích hợp.

**Không chạy `COMMIT` sau `ROLLBACK` rồi mong thao tác trước được lưu.** Kết quả xóa trong transaction đã rollback không còn tồn tại sau rollback.

### 15.1. Cẩn trọng với vòng lặp SELECT rồi DELETE

Một ứng dụng có thể:

1. `SELECT` danh sách ID sẽ xóa.
2. Cho người dùng xác nhận.
3. `DELETE WHERE id IN (...)` vài phút sau.

Trong thời gian chờ, một số ID có thể đổi trạng thái hoặc đã được sử dụng theo nghiệp vụ khác. Nếu quyết định xóa phụ thuộc điều kiện hiện tại, câu DELETE cần **kiểm tra lại điều kiện** trên các bảng nguồn, hoặc sử dụng cơ chế khóa/phiên bản phù hợp. Không chỉ dựa vào danh sách ID cũ.

### 15.2. Đếm hàng thực sự bị xóa

Trên PostgreSQL có thể dùng `RETURNING` để nhận ID; SQL Server có `OUTPUT DELETED`; MySQL/SQLite/Oracle có API affected rows và cơ chế trả kết quả theo phiên bản.

Hãy đối soát:

- Số hàng dự kiến.
- Số hàng đích thực sự bị xóa.
- Tác động đến hàng con bởi cascade/trigger.
- Số hàng còn lại sau thao tác, nếu cần.
- Audit/correlation ID của yêu cầu xóa.

Câu SQL không báo lỗi **không có nghĩa** đã xóa đúng số lượng dự định: có thể xóa 0 hàng do điều kiện quá chặt hoặc hàng đã bị xóa trước đó.

## 16. Xóa theo lô để tránh transaction quá lớn

Xóa hàng triệu bản ghi trong một câu có thể làm tăng áp lực lên WAL/redo/undo, khóa, replication lag, VACUUM/garbage collection, tài nguyên tạm và thời gian giao dịch. Một giải pháp là **xóa từng lô nhỏ** với tiêu chí ổn định.

PostgreSQL **không có mệnh đề `DELETE ... LIMIT 100` trực tiếp** như single-table DELETE của MySQL. Có thể chọn khóa trong CTE rồi xóa theo khóa.

### 16.1. PostgreSQL: batch bằng CTE chọn khóa

```sql
WITH victims AS (
    SELECT m.message_id
    FROM demo_messages AS m
    WHERE m.message_status = 'DRAFT'
      AND m.created_on < DATE '2026-10-01'
      AND EXISTS (
          SELECT 1
          FROM demo_accounts AS a
          WHERE a.account_id = m.account_id
            AND a.account_status = 'INACTIVE'
      )
    ORDER BY m.message_id
    LIMIT 2
)
DELETE FROM demo_messages AS m
USING victims AS v
WHERE m.message_id = v.message_id
RETURNING m.message_id;
```

Trên dữ liệu mẫu còn nguyên, lô đầu chọn **502 và 504** theo thứ tự ID tăng, rồi xóa hai thông điệp đó. Chạy một lô tiếp theo trên trạng thái đã commit sẽ tiếp tục với ID 507.

Chú ý:

- `ORDER BY` nằm trong **truy vấn chọn khóa**, không phải thứ tự trả hàng của `DELETE ... RETURNING`.
- Không chạy một vòng lặp không giới hạn mà không có điều kiện dừng và giới hạn tài nguyên.
- Nếu cần ghi nhận/tiến độ, sử dụng số hàng xóa thực tế và commit theo chính sách.
- Việc thay đổi trạng thái bảng nguồn giữa các lô có thể làm tập khóa đủ điều kiện thay đổi; cần chính sách đối với dữ liệu mới phát sinh.

### 16.2. Nhiều worker cùng dọn dữ liệu: SKIP LOCKED

Trong PostgreSQL, có thể cân nhắc khóa các hàng được chọn:

```sql
WITH victims AS (
    SELECT m.message_id
    FROM demo_messages AS m
    WHERE m.message_status = 'DRAFT'
      AND m.created_on < DATE '2026-10-01'
    ORDER BY m.message_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
DELETE FROM demo_messages AS m
USING victims AS v
WHERE m.message_id = v.message_id
RETURNING m.message_id;
```

`SKIP LOCKED` có thể giúp nhiều worker tránh chờ trên cùng các hàng mục tiêu; nhưng nó **không mang lại snapshot nhất quán tuyệt đối** và có thể bỏ qua những hàng đang bị khóa. Ví dụ rút gọn chưa có điều kiện tài khoản; nếu yêu cầu thật phụ thuộc tài khoản, phải giữ `EXISTS` trong truy vấn chọn khóa hoặc kiểm tra lại điều kiện ở bước DELETE.

Khi cần bảo đảm một chính sách xóa nhất quán trong lúc dữ liệu liên quan thay đổi, phải xét isolation level, row locking, thứ tự khóa và cơ chế retry. Đây là thiết kế đồng thời, không chỉ thêm `SKIP LOCKED` để tăng tốc.

### 16.3. Hạn chế batch theo phương ngữ

| DBMS | Cách thường làm |
|---|---|
| PostgreSQL | CTE/truy vấn con chọn khóa có `LIMIT`, rồi `DELETE ... USING` hoặc `WHERE ... IN` |
| MySQL | `DELETE FROM t WHERE ... ORDER BY ... LIMIT n` cho single-table form; multi-table JOIN cần chiến lược khác |
| SQL Server | `TOP (n)` giới hạn số hàng, nhưng không bảo đảm thứ tự nếu không chọn khóa theo subquery/CTE |
| Oracle | Chọn khóa qua truy vấn con với `FETCH FIRST`/`ROWNUM` tùy phiên bản rồi xóa theo khóa |
| SQLite | `ORDER BY/LIMIT` trong DELETE phụ thuộc tùy chọn biên dịch; dùng subquery chọn khóa khi cần portable hơn |

Phân lô giúp kiểm soát tài nguyên nhưng có đánh đổi: lặp nhiều transaction có overhead, dữ liệu có thể thay đổi giữa lô, và xóa quá nhanh vẫn có thể làm tăng lag. Chọn kích thước batch và nhịp chạy theo số liệu thật.

## 17. Chỉ mục và hiệu năng khi dùng EXISTS/JOIN

Để `DELETE` tìm đúng các hàng đích, DBMS cần xét hai phía:

- **Bảng đích**: những hàng nào có trạng thái/ngày đủ điều kiện?
- **Bảng liên quan**: có hàng account/flag tương ứng không?

Với ví dụ:

```sql
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
```

các chỉ mục có thể hữu ích trên bảng lớn:

```sql
-- PostgreSQL: ví dụ cân nhắc theo workload thực tế.
CREATE INDEX idx_demo_messages_status_date_account
ON demo_messages (message_status, created_on, account_id);

CREATE INDEX idx_demo_flags_message
ON demo_message_flags (message_id);
```

- Bảng `demo_accounts` đã có PK `account_id`, thường cung cấp chỉ mục tra cứu ID.
- Chỉ mục `demo_messages(message_status, created_on, account_id)` có thể hỗ trợ lọc theo trạng thái và mốc ngày, tùy phân bố dữ liệu.
- Chỉ mục `demo_message_flags(message_id)` có thể hỗ trợ kiểm tra `EXISTS` theo thông điệp và xử lý FK cascade khi thông điệp bị xóa.
- Nếu nghiệp vụ thường hỏi “tài khoản này có thông điệp nào không?”, chỉ mục theo `demo_messages(account_id)` hoặc tổ hợp bắt đầu bằng `account_id` có thể hữu ích hơn thứ tự chỉ mục ở ví dụ đầu.

Không thêm mọi chỉ mục nêu trên một cách máy móc. Mỗi chỉ mục tiêu tốn dung lượng và làm tăng chi phí ghi/xóa, đồng thời optimizer có thể không sử dụng chúng nếu bảng nhỏ hoặc điều kiện ít chọn lọc.

### 17.1. FK không phải lúc nào tự tạo chỉ mục phía con

PostgreSQL tạo chỉ mục cho PK/UNIQUE ở phía được tham chiếu, nhưng **không tự tạo chỉ mục trên mọi cột FK ở bảng con**. Khi xóa một hàng cha, việc kiểm tra/cascade sang bảng con có thể cần tìm các hàng tham chiếu; index FK phía con thường đáng cân nhắc.

Với bảng có hàng triệu `message_flags`, thiếu chỉ mục theo `message_id` có thể làm quá trình xóa thông điệp kèm cascade tốn kém.

### 17.2. Đừng khẳng định EXISTS luôn nhanh hơn JOIN

`EXISTS` có thể được optimizer biến thành semi-join; một `DELETE ... USING` cũng có thể được lập kế hoạch hiệu quả. Lựa chọn nhanh hơn tùy:

- Số lượng hàng đích và bảng liên quan.
- Tỷ lệ hàng khớp và có nhiều hàng liên quan không.
- Chỉ mục, thống kê và phân bố dữ liệu.
- Cách engine thực thi DELETE, trigger và FK.
- Chính sách khóa, log và ảnh hưởng transaction.

Đo bằng `EXPLAIN` ở môi trường phù hợp. Đừng dùng `SELECT` join nhanh hơn làm bằng chứng chắc chắn `DELETE` join sẽ nhanh hơn, vì câu xóa còn phải thực hiện thay đổi dữ liệu và kiểm tra ràng buộc.

### 17.3. EXPLAIN trên PostgreSQL

```sql
EXPLAIN
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
```

`EXPLAIN` không có `ANALYZE` thường chỉ tạo **kế hoạch dự kiến**. Nếu dùng `EXPLAIN ANALYZE`, PostgreSQL **thực thi thật** câu `DELETE`. Muốn thử đo trên dữ liệu có thể phục hồi, dùng một transaction kiểm soát và `ROLLBACK`, đồng thời hiểu các tác dụng của trigger, sequence và các tác động ngoại vi có thể không rollback giống thay đổi hàng.

Không chạy `EXPLAIN ANALYZE DELETE` trực tiếp trên bảng sản xuất khi chưa có kế hoạch an toàn.

## 18. Quyền truy cập và phạm vi tenant

Câu DELETE có thể chứa điều kiện nối đúng về kỹ thuật nhưng sai phạm vi quyền nếu bỏ khóa tenant.

Giả sử các bảng dùng khóa ghép:

```text
messages(tenant_id, message_id, account_id, ...)
accounts(tenant_id, account_id, account_status, ...)
```

Nếu cùng `account_id = 2` tồn tại ở hai tenant, điều kiện sau **không đủ**:

```sql
-- Sai nếu account_id chỉ duy nhất TRONG từng tenant.
a.account_id = m.account_id
```

Phải có đầy đủ khóa liên kết:

```sql
a.tenant_id = m.tenant_id
AND a.account_id = m.account_id
```

Và nếu thao tác đang được thực thi thay mặt một tenant cụ thể, bảng đích cũng cần được giới hạn tới tenant **đã được xác thực/ủy quyền**:

```sql
-- PostgreSQL, ví dụ cấu trúc giả định có tenant_id.
DELETE FROM messages AS m
WHERE m.tenant_id = :authorized_tenant_id
  AND m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM accounts AS a
      WHERE a.tenant_id = m.tenant_id
        AND a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
```

`:authorized_tenant_id` là tham số đại diện của ứng dụng, **không phải cú pháp biến SQL có sẵn trên mọi công cụ**. Giá trị phải đến từ bối cảnh quyền truy cập phía server, không tin hoàn toàn vào ID tenant do client tự nhập.

Điều kiện tenant nên được bảo vệ cả bằng khóa/ràng buộc và chính sách quyền hoặc row-level security khi hệ quản trị/hệ thống sử dụng cơ chế đó. `EXISTS` hay `JOIN` không tự thay thế kiểm soát phân quyền.

## 19. DELETE cứng hay soft delete?

`DELETE` xóa hàng vật lý theo hành vi của DBMS. Một ứng dụng cần giữ nhật ký hoạt động, hóa đơn, tranh chấp hoặc bằng chứng kiểm toán có thể không được phép xóa cứng.

Một chiến lược khác là **soft delete**:

```sql
-- Ví dụ giả định messages có cột deleted_at.
UPDATE messages AS m
SET deleted_at = CURRENT_TIMESTAMP
WHERE m.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
```

Cách này không xóa hàng; nó đánh dấu đã bị xóa theo quy tắc ứng dụng. Nhưng soft delete cũng cần giải quyết:

- Các truy vấn mặc định có lọc `deleted_at IS NULL` hay không?
- `UNIQUE` có còn áp lên bản ghi đã bị đánh dấu?
- FK và báo cáo lịch sử xử lý ra sao?
- Ai có quyền khôi phục hoặc xóa cứng sau thời gian lưu giữ?
- Dữ liệu có thực sự được xóa khi hết hạn lưu trữ không?

Không chọn soft delete chỉ để né lỗi FK. Phải theo chính sách dữ liệu, bảo mật và nghiệp vụ.

## 20. Các sai lầm phổ biến

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Quên `WHERE` | Có thể xóa mọi hàng trong bảng đích | Luôn xác định tập mục tiêu và kiểm tra trước |
| Quên `a.id = m.account_id` trong `EXISTS` | Chỉ cần một hàng phụ tồn tại là nhiều hàng đích bị xóa | Viết điều kiện tương quan rõ |
| Quên một điều kiện `JOIN` trong `USING` | Cartesian match, xóa rộng ngoài ý muốn | Kiểm tra đầy đủ khóa nối |
| Dùng `COUNT(*)` trên JOIN một-nhiều để đo số hàng đích | Đếm lặp thông điệp có nhiều cờ | `COUNT(DISTINCT target.pk)` hoặc `EXISTS` |
| Nhầm `USING` của PostgreSQL với MySQL | Cú pháp sai, hiểu nhầm bảng đích | Viết đúng phương ngữ |
| Cho rằng bảng trong `USING`/`JOIN` đều bị xóa | Hiểu sai phạm vi dữ liệu bị thay đổi | Xác định alias sau `DELETE`; xét FK/trigger riêng |
| Cố dùng `DELETE ... JOIN` MySQL trên Oracle/SQLite | Lỗi cú pháp | Dùng `WHERE EXISTS` |
| Xóa cha còn con mà bỏ qua FK | Câu DELETE thất bại hoặc cascade không mong muốn | Xem `ON DELETE`, ràng buộc và quy tắc lưu trữ |
| Cho rằng xóa 502 không tác động bảng flags | Bỏ qua `ON DELETE CASCADE` | Xem ảnh hưởng gián tiếp FK |
| Dùng `NOT IN` với tập có `NULL` để tìm hàng không liên quan | Logic UNKNOWN có thể loại sai dữ liệu | `NOT EXISTS` với khóa liên kết rõ |
| `SELECT` trước cho 3 hàng nên tin DELETE luôn xóa 3 | Dữ liệu có thể thay đổi giữa hai câu | Giao dịch/khóa phù hợp, kiểm tra affected rows |
| `DELETE ... LIMIT` PostgreSQL | Không đúng cú pháp trực tiếp | Chọn khóa trong CTE/truy vấn con rồi xóa |
| `DELETE TOP (100)` SQL Server và mong xóa 100 hàng cũ nhất | TOP không tự có thứ tự | Chọn khóa bằng `ORDER BY` trước |
| Gọi `EXPLAIN ANALYZE DELETE` trên production như câu xem plan | Thực thi xóa thật | Dùng `EXPLAIN`, thử trong transaction/môi trường an toàn |
| Dùng `DELETE` để thay policy lưu trữ mềm | Có thể mất dữ liệu cần kiểm toán | Xác định hard vs soft delete |
| Quên tenant trong khóa nối | Có thể đụng dữ liệu tenant khác | Liên kết theo khóa ghép đầy đủ và kiểm soát quyền |
| Thiếu index FK phía con khi xóa/cascade nhiều | Kiểm tra hoặc cascade có thể chậm | Xem chỉ mục theo khóa tham chiếu, đo thực tế |

## 21. Bài tập thực hành

Các bài sử dụng dữ liệu mẫu **chưa bị xóa**. Khi chạy từng đáp án, hãy tạo lại dữ liệu hoặc bao câu `DELETE` trong transaction và `ROLLBACK` để bài kế tiếp vẫn có dữ liệu ban đầu.

### Bài 1. Xóa DRAFT cũ của INACTIVE bằng EXISTS

**Yêu cầu:** xóa thông điệp `DRAFT` trước ngày `2026-10-01`, chỉ khi tài khoản của nó `INACTIVE`. Trả ID xóa trong PostgreSQL.

**Đáp án:**

```sql
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  )
RETURNING m.message_id;
```

Các ID mục tiêu là **502, 504, 507**.

### Bài 2. Viết lại bằng PostgreSQL USING

**Đáp án:**

```sql
DELETE FROM demo_messages AS m
USING demo_accounts AS a
WHERE a.account_id = m.account_id
  AND a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
RETURNING m.message_id;
```

Chỉ hàng `demo_messages` bị xóa trực tiếp. Tài khoản liên quan không bị xóa chỉ vì chúng xuất hiện trong `USING`.

### Bài 3. Viết lại cho MySQL/MariaDB

**Đáp án:**

```sql
DELETE m
FROM messages AS m
INNER JOIN accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < '2026-10-01';
```

Không sao chép thêm `RETURNING` từ PostgreSQL vào MySQL mà không kiểm tra tính năng phiên bản. Tên bảng ở đây minh họa hệ có bảng tương đương `messages`, `accounts`.

### Bài 4. Viết lại cho SQL Server

**Đáp án:**

```sql
DELETE m
OUTPUT DELETED.message_id
FROM dbo.messages AS m
JOIN dbo.accounts AS a
  ON a.account_id = m.account_id
WHERE a.account_status = 'INACTIVE'
  AND m.message_status = 'DRAFT'
  AND m.created_on < CONVERT(date, '2026-10-01', 23);
```

`OUTPUT DELETED.message_id` cho phép quan sát các mã đã xóa theo cơ chế T-SQL.

### Bài 5. Vì sao quên correlation nguy hiểm?

```sql
DELETE FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND EXISTS (
      SELECT 1 FROM demo_accounts a
      WHERE a.account_status = 'INACTIVE'
  );
```

**Đáp án:** vì truy vấn trong không liên kết với `m.account_id`, nó đúng với **mọi** dòng DRAFT khi trong hệ có bất kỳ tài khoản INACTIVE nào. Cần thêm `a.account_id = m.account_id` và các điều kiện ngày/trạng thái đúng mục tiêu.

### Bài 6. COUNT(*) trên JOIN báo 4 thay vì 3?

**Câu hỏi:** nếu tìm thông điệp `DRAFT` có cờ `SPAM` hoặc `REVIEW` bằng JOIN, tại sao `COUNT(*)` có thể bằng 4 trong khi chỉ có ba thông điệp cần xóa?

**Đáp án:** thông điệp 502 có hai cờ phù hợp, nên JOIN tạo hai dòng cho 502 và một dòng cho 504, một dòng cho 506: **tổng bốn hàng JOIN nhưng ba message_id khác nhau**. Có thể dùng `COUNT(DISTINCT m.message_id)` hoặc `EXISTS`.

### Bài 7. Xóa tài khoản rỗng

**Yêu cầu:** xóa tài khoản `INACTIVE` không có thông điệp nào.

**Đáp án:**

```sql
DELETE FROM demo_accounts AS a
WHERE a.account_status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM demo_messages AS m
      WHERE m.account_id = a.account_id
  )
RETURNING a.account_id;
```

Trên dữ liệu ban đầu, chỉ ID **5** đủ điều kiện.

### Bài 8. Giải thích tác động cascade

**Câu hỏi:** nếu xóa thông điệp 502, các cờ 1001 và 1002 sẽ ra sao trong schema mẫu?

**Đáp án:** chúng bị xóa theo ràng buộc `demo_message_flags.message_id REFERENCES demo_messages(message_id) ON DELETE CASCADE`. Đây là tác động FK, không cần phải chỉ định `demo_message_flags` là bảng xóa trong PostgreSQL `DELETE ... USING`.

### Bài 9. Chọn một lô hai hàng bằng CTE

**Yêu cầu:** PostgreSQL xóa tối đa hai thông điệp đủ điều kiện ở bài 1 theo `message_id` tăng dần.

**Đáp án:**

```sql
WITH victims AS (
    SELECT m.message_id
    FROM demo_messages m
    WHERE m.message_status = 'DRAFT'
      AND m.created_on < DATE '2026-10-01'
      AND EXISTS (
          SELECT 1
          FROM demo_accounts a
          WHERE a.account_id = m.account_id
            AND a.account_status = 'INACTIVE'
      )
    ORDER BY m.message_id
    LIMIT 2
)
DELETE FROM demo_messages AS m
USING victims AS v
WHERE v.message_id = m.message_id
RETURNING m.message_id;
```

Trên dữ liệu ban đầu, lô đầu chọn **502 và 504**. `RETURNING` không bảo đảm thứ tự hiển thị, dù CTE đã chọn hai khóa đầu theo thứ tự.

### Bài 10. Điều kiện đầy đủ trong hệ đa tenant

**Tình huống:** `messages` và `accounts` đều có `tenant_id`; trong mỗi tenant có thể có cùng `account_id`. Điều kiện liên kết nào phải có?

**Đáp án:**

```sql
a.tenant_id = m.tenant_id
AND a.account_id = m.account_id
```

Khi xóa cho một tenant đã được phân quyền, bảng đích còn cần ràng buộc phạm vi tenant từ bối cảnh server. Chỉ nối theo `account_id` có thể làm sai phạm vi dữ liệu.

### Bài 11. Chọn EXISTS hay JOIN?

**Tình huống A:** “Chỉ xóa nếu có ít nhất một cờ SPAM.”  
**Tình huống B:** “Xóa theo điều kiện của bảng tài khoản, đã có khóa PK rõ và cần tối ưu trên PostgreSQL.”

**Gợi ý:** A thường diễn đạt gọn bằng `EXISTS` vì quan hệ một-nhiều và không quan tâm số cờ. B dùng `EXISTS` hoặc `USING` đều có thể đúng; chọn cách rõ nghĩa, kiểm tra plan và ảnh hưởng FK trên workload thực tế.

### Bài 12. Preview trước khi xóa

**Yêu cầu:** không chạy DELETE ngay; hãy đếm số thông điệp DRAFT cũ của tài khoản INACTIVE.

**Đáp án:**

```sql
SELECT COUNT(*) AS targets
FROM demo_messages AS m
WHERE m.message_status = 'DRAFT'
  AND m.created_on < DATE '2026-10-01'
  AND EXISTS (
      SELECT 1
      FROM demo_accounts AS a
      WHERE a.account_id = m.account_id
        AND a.account_status = 'INACTIVE'
  );
-- targets = 3
```

Sau khi chạy DELETE, kiểm tra affected rows/`RETURNING`; không mặc định preview ở thời điểm khác luôn khớp tuyệt đối.

## 22. Tóm tắt nguyên tắc áp dụng

Khi bài toán yêu cầu **xóa hàng của bảng A tùy thuộc dữ liệu ở bảng B**, `DELETE ... WHERE EXISTS` là mẫu nên nắm trước: nó diễn đạt trực tiếp “hàng A chỉ bị xóa khi có ít nhất một B phù hợp”, tránh phải đếm số hàng liên quan và có thể chuyển giữa nhiều phương ngữ.

Khi cần cú pháp JOIN cụ thể, hãy nhớ:

- **PostgreSQL:** `DELETE FROM target AS t USING related AS r WHERE ...`.
- **MySQL/MariaDB:** `DELETE t FROM target AS t JOIN related AS r ON ... WHERE ...`; có thêm hình thức xóa nhiều bảng nhưng phải cực kỳ cẩn thận.
- **SQL Server:** `DELETE t FROM dbo.target AS t JOIN dbo.related AS r ON ... WHERE ...`; có `OUTPUT DELETED`.
- **Oracle/SQLite:** mẫu thông dụng cho xóa theo bảng liên quan là `DELETE FROM target WHERE EXISTS (...)`, với cú pháp ngày và `RETURNING` theo hệ.

**Trước khi xóa**, xác định chính xác bảng đích, điều kiện nối đầy đủ, phạm vi tenant, số hàng dự kiến và ràng buộc FK. **Trong khi xóa**, dùng transaction/giới hạn lô đúng môi trường và theo dõi số hàng thực sự tác động. **Sau khi xóa**, xác nhận các hàng liên quan, cascade, audit và trạng thái nghiệp vụ. `EXISTS` hay `JOIN` đều chỉ là công cụ chọn hàng; sự an toàn đến từ ngữ nghĩa được xác định rõ và việc kiểm soát thao tác thay đổi dữ liệu.

