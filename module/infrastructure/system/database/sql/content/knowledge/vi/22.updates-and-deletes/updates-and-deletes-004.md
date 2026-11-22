# Quan hệ nguồn nhiều hàng và nguy cơ cập nhật không xác định

Trong SQL, câu `UPDATE` không phải lúc nào cũng gán một hằng số vào một cột. Nhiều hệ thống cập nhật bảng đích bằng dữ liệu từ bảng khác: áp dụng hạn mức tín dụng mới từ danh sách đề xuất, cập nhật giá bán theo bảng giá, đồng bộ thông tin đơn hàng từ một nguồn nhập liệu, hoặc đánh dấu khách hàng theo các sự kiện gần đây.

Một câu truy vấn thường gặp trong PostgreSQL:

```sql
UPDATE target_table AS t
SET target_column = s.source_value
FROM source_table AS s
WHERE s.business_key = t.business_key;
```

Câu này chỉ đơn giản khi **mỗi hàng đích khớp tối đa một hàng nguồn**. Nếu một hàng đích khớp hai hàng nguồn có giá trị khác nhau, SQL phải đối diện câu hỏi: **nên lấy giá trị từ hàng nào?**

Với `UPDATE ... FROM` của PostgreSQL, nếu một hàng đích khớp nhiều hàng nguồn, hàng đích vẫn chỉ được cập nhật một lần nhưng **không thể dự đoán đáng tin cậy hàng nguồn nào được dùng**. Truy vấn có thể chạy thành công, không báo lỗi, nhưng kết quả phụ thuộc cách hệ quản trị thực thi. Đây là **nguy cơ cập nhật không xác định** (*nondeterministic update*), rất khác với một phép cập nhật cố ý theo quy tắc chọn bản ghi mới nhất.

Bài học thuộc **Database SQL → Cập nhật và xóa → Quan hệ nguồn nhiều hàng và nguy cơ cập nhật không xác định**. Các mục chính gồm:

- Hiểu đúng số hàng của phép nối giữa **bảng đích** và **bảng nguồn**.
- Phát hiện quan hệ một-nhiều trước khi cập nhật.
- Phân biệt `UPDATE ... FROM`, truy vấn con một giá trị, `MERGE` và `DELETE ... USING`.
- Chọn **đúng một hàng nguồn** bằng khóa duy nhất, ràng buộc, `ROW_NUMBER`, `DISTINCT ON` hoặc quy tắc tổng hợp có ý nghĩa.
- Kiểm soát đồng hạng, `NULL`, cập nhật đồng thời, giao dịch và kiểm tra kết quả.
- So sánh các điểm khác nhau giữa PostgreSQL, SQL Server, MySQL và Oracle.

Ví dụ thực hành chính dùng **PostgreSQL**. Các truy vấn có tác động ghi sẽ được tách rõ khỏi các truy vấn chẩn đoán để người học không vô tình biến ví dụ nguy hiểm thành thao tác trên dữ liệu thật.

## 1. Điều kiện nối không tự bảo đảm mỗi đích chỉ có một nguồn

Xét hai bảng:

```text
accounts (đích)                    proposals (nguồn)

account_id | credit_limit          proposal_id | account_id | proposed_limit
-----------+-------------          ------------+------------+---------------
101        | 1000                  1            | 101        | 1200
102        | 1500                  2            | 101        | 1800
                                   3            | 102        | 1600
```

Khi nối theo `account_id`:

```sql
SELECT a.account_id,
       a.credit_limit,
       p.proposal_id,
       p.proposed_limit
FROM accounts AS a
JOIN proposals AS p
  ON p.account_id = a.account_id;
```

ta nhận được:

| account_id | credit_limit hiện tại | proposal_id | proposed_limit |
| ---: | ---: | ---: | ---: |
| 101 | 1000 | 1 | 1200 |
| 101 | 1000 | 2 | 1800 |
| 102 | 1500 | 3 | 1600 |

Đây là **ba hàng kết quả nối**, nhưng chỉ có **hai hàng đích**. Đối với account 101, cả đề xuất 1 và 2 đều khớp điều kiện. Nếu viết `SET credit_limit = p.proposed_limit`, câu lệnh chưa xác định phải dùng **1200 hay 1800**.

### Cần phân biệt ba đại lượng

| Đại lượng | Ý nghĩa |
| --- | --- |
| **Số hàng đích** | Số bản ghi có thể được thay đổi trong bảng cập nhật |
| **Số cặp khớp của JOIN** | Số cặp `(đích, nguồn)` thỏa điều kiện |
| **Số hàng nguồn trên mỗi đích** | Số lựa chọn giá trị có thể cấp cho một hàng đích |

Nếu một đích khớp nhiều nguồn, số cặp nối có thể lớn hơn số hàng đích. `JOIN` không tự chọn một nguồn tốt nhất, dù truy vấn đích chỉ có một hàng mang khóa chính đó.

### Ba loại quan hệ thường gặp

- **Một–một:** mỗi đích có một nguồn. Thường là hình thức dễ cập nhật nhất khi nguồn có khóa duy nhất phù hợp.
- **Một–nhiều:** một đích có nhiều nguồn, chẳng hạn nhiều phiên bản đề xuất. Cần quy tắc lựa chọn hoặc tổng hợp.
- **Nhiều–nhiều:** cả hai bên có thể có nhiều hàng theo khóa nối. Nếu một bản cập nhật dựa vào quan hệ này mà không rõ mức dữ liệu, rủi ro sai số càng cao.

Không nên suy luận rằng `WHERE s.key = t.key` đã “bảo đảm khóa duy nhất”: đó mới là **điều kiện bằng**, chưa phải **ràng buộc duy nhất**.

## 2. Dữ liệu thực hành PostgreSQL

Các ví dụ dưới đây dùng hai bảng tạm. Hãy tạo chúng trong **một phiên PostgreSQL thực hành riêng**, không chạy vào bảng nghiệp vụ đang vận hành.

- `credit_accounts_275`: bảng **đích**, mỗi tài khoản có một hàng.
- `credit_proposals_275`: bảng **nguồn**, mỗi tài khoản có thể có nhiều đề xuất điều chỉnh hạn mức.

### 2.1. Bảng đích

```sql
CREATE TEMP TABLE credit_accounts_275 (
    account_id             INTEGER PRIMARY KEY,
    customer_name          TEXT NOT NULL,
    tier                   TEXT NOT NULL,
    credit_limit           NUMERIC(12, 2) NOT NULL,
    last_proposal_id       INTEGER
);

INSERT INTO credit_accounts_275
    (account_id, customer_name, tier, credit_limit, last_proposal_id)
VALUES
    (101, 'An',   'BASIC',    1000.00, NULL),
    (102, 'Bình', 'BASIC',    1500.00, NULL),
    (103, 'Chi',  'STANDARD', 2000.00, NULL),
    (104, 'Dũng', 'BASIC',     900.00, NULL),
    (105, 'Hà',   'BASIC',    1100.00, NULL);
```

`account_id` là khóa chính. Mỗi tài khoản chỉ có **một bản ghi đích** và `credit_limit` không cho phép `NULL`.

### 2.2. Bảng nguồn có các trường hợp gây tranh chấp

```sql
CREATE TEMP TABLE credit_proposals_275 (
    proposal_id    INTEGER PRIMARY KEY,
    account_id     INTEGER NOT NULL,
    approved_at    TIMESTAMP NOT NULL,
    proposed_limit NUMERIC(12, 2),
    proposed_tier  TEXT NOT NULL,
    proposal_status TEXT NOT NULL,
    note           TEXT
);

INSERT INTO credit_proposals_275
    (proposal_id, account_id, approved_at,
     proposed_limit, proposed_tier, proposal_status, note)
VALUES
    (1, 101, TIMESTAMP '2026-06-01 09:00:00',
     1200.00, 'SILVER', 'APPROVED', 'Đề xuất cũ'),

    (2, 101, TIMESTAMP '2026-06-10 09:00:00',
     1800.00, 'GOLD', 'APPROVED', 'Đề xuất mới'),

    (3, 102, TIMESTAMP '2026-06-04 10:00:00',
     1600.00, 'SILVER', 'APPROVED', 'Chỉ một đề xuất duyệt'),

    (4, 103, TIMESTAMP '2026-06-05 08:00:00',
     2100.00, 'GOLD', 'APPROVED', 'Đồng thời điểm A'),

    (5, 103, TIMESTAMP '2026-06-05 08:00:00',
     2200.00, 'PLATINUM', 'APPROVED', 'Đồng thời điểm B'),

    (6, 104, TIMESTAMP '2026-06-06 10:00:00',
     NULL, 'SILVER', 'APPROVED', 'Thiếu hạn mức'),

    (7, 106, TIMESTAMP '2026-06-12 10:00:00',
     2500.00, 'GOLD', 'APPROVED', 'Không có tài khoản đích'),

    (8, 102, TIMESTAMP '2026-06-11 08:00:00',
     1750.00, 'GOLD', 'REJECTED', 'Đề xuất bị từ chối');
```

Hãy xem dữ liệu nguồn:

```sql
SELECT proposal_id,
       account_id,
       approved_at,
       proposed_limit,
       proposed_tier,
       proposal_status
FROM credit_proposals_275
ORDER BY account_id, approved_at, proposal_id;
```

Các trường hợp cần phân biệt:

| Tài khoản | Nguồn tương ứng | Vấn đề |
| --- | --- | --- |
| 101 | Đề xuất 1 và 2 đã duyệt | Có **hai hàng nguồn** có hạn mức khác nhau |
| 102 | Đề xuất 3 đã duyệt, đề xuất 8 bị từ chối | Phải lọc **trạng thái được duyệt**, không lấy đơn thuần bản mới nhất |
| 103 | Đề xuất 4 và 5 đã duyệt, cùng `approved_at` | Có **đồng hạng** khi xếp theo thời gian |
| 104 | Đề xuất 6 đã duyệt nhưng `proposed_limit = NULL` | Cần chính sách xử lý giá trị thiếu |
| 105 | Không có đề xuất nào | Không được tự gán `NULL` nếu chỉ muốn cập nhật tài khoản có dữ liệu hợp lệ |
| 106 | Có đề xuất 7, không có tài khoản tương ứng | Nguồn **không có đích**, không được tự sinh hàng đích bởi một câu `UPDATE` thông thường |

Định nghĩa nghiệp vụ trong bài: chỉ dùng đề xuất có `proposal_status = 'APPROVED'` và `proposed_limit IS NOT NULL`; nếu một tài khoản có nhiều đề xuất hợp lệ, chọn **`approved_at` mới nhất**, sau đó dùng **`proposal_id` lớn hơn để phá hòa**.

Đây là **quy tắc minh họa**, không phải luật bắt buộc cho mọi hệ thống tín dụng. Hệ thống thật có thể cần một trạng thái hiệu lực và cơ chế giải quyết đồng thời điểm chặt chẽ hơn.

## 3. Xem trước kết quả JOIN trước khi UPDATE

Trước khi chạy một câu cập nhật dựa trên nguồn khác, hãy biến phần nối của nó thành `SELECT` để quan sát tập ứng viên.

```sql
SELECT
    a.account_id,
    a.credit_limit AS old_limit,
    p.proposal_id,
    p.proposed_limit,
    p.approved_at
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
ORDER BY a.account_id, p.approved_at, p.proposal_id;
```

Kết quả:

| account_id | old_limit | proposal_id | proposed_limit |
| ---: | ---: | ---: | ---: |
| 101 | 1000 | 1 | 1200 |
| 101 | 1000 | 2 | 1800 |
| 102 | 1500 | 3 | 1600 |
| 103 | 2000 | 4 | 2100 |
| 103 | 2000 | 5 | 2200 |

Ở đây chỉ có **3 tài khoản đích** (101, 102, 103), nhưng có **5 cặp khớp**. Nếu lập tức cập nhật theo `p.proposed_limit`, tài khoản 101 và 103 không có một nguồn duy nhất.

### Đếm số hàng nguồn trên từng hàng đích

```sql
SELECT
    a.account_id,
    COUNT(*) AS candidate_rows,
    COUNT(DISTINCT p.proposed_limit) AS distinct_limits
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
GROUP BY a.account_id
ORDER BY a.account_id;
```

| account_id | candidate_rows | distinct_limits |
| ---: | ---: | ---: |
| 101 | 2 | 2 |
| 102 | 1 | 1 |
| 103 | 2 | 2 |

`COUNT(*)` đo số ứng viên thực, còn `COUNT(DISTINCT proposed_limit)` đo số **giá trị hạn mức khác nhau**. Cả hai có ích; nhưng **kể cả khi hai nguồn cho cùng một giá trị**, quan hệ vẫn có nhiều hàng và có thể gây vấn đề khi sau này cập nhật thêm cột khác hoặc dùng `MERGE`.

### Tìm riêng các đích bị trùng nguồn

```sql
SELECT p.account_id,
       COUNT(*) AS matching_proposals
FROM credit_proposals_275 AS p
JOIN credit_accounts_275 AS a
  ON a.account_id = p.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
GROUP BY p.account_id
HAVING COUNT(*) > 1
ORDER BY p.account_id;
```

Kết quả là **101 và 103**, mỗi tài khoản có hai đề xuất hợp lệ.

Lưu ý: `GROUP BY` phải theo **khóa định danh hàng đích**. Nếu khóa là cặp `(tenant_id, account_id)`, chỉ nhóm theo `account_id` sẽ đánh đồng những tài khoản thuộc tenant khác nhau.

## 4. PostgreSQL UPDATE ... FROM và lựa chọn nguồn không xác định

Câu dưới đây nhìn bề ngoài hợp lý nhưng **không đáp ứng quy tắc nghiệp vụ đã nêu**:

```sql
-- Ví dụ CỐ Ý KHÔNG AN TOÀN: không thực thi.
-- Khi a.account_id có nhiều p khớp, giá trị nguồn được chọn
-- không được bảo đảm theo approved_at hoặc proposal_id.
--
-- UPDATE credit_accounts_275 AS a
-- SET credit_limit = p.proposed_limit,
--     tier         = p.proposed_tier,
--     last_proposal_id = p.proposal_id
-- FROM credit_proposals_275 AS p
-- WHERE p.account_id = a.account_id
--   AND p.proposal_status = 'APPROVED'
--   AND p.proposed_limit IS NOT NULL;
```

Với PostgreSQL, `UPDATE ... FROM` thực hiện phép nối giữa bảng cập nhật và các quan hệ nguồn. Nếu phép nối tạo **nhiều hàng cho cùng một hàng đích**, **một** hàng nguồn sẽ được sử dụng để cập nhật đích đó, nhưng không được bảo đảm là hàng nào.

Vì thế:

- Với tài khoản **101**, `credit_limit` có thể nhận 1200 hoặc 1800 theo nguồn được sử dụng.
- Với tài khoản **103**, `credit_limit` có thể nhận 2100 hoặc 2200.
- Với tài khoản **102**, nếu chỉ xét đề xuất `APPROVED`, có một ứng viên là 1600.
- Với tài khoản **104**, bộ lọc `proposed_limit IS NOT NULL` giúp không đưa giá trị thiếu vào cột `credit_limit NOT NULL`.
- Với tài khoản **105**, không có nguồn nên không được cập nhật theo câu lệnh này.

**Không nên thử suy luận kết quả từ việc “hàng được INSERT trước”, “đề xuất có ID lớn hơn”, “bảng có index”, hay “SELECT nhìn như đã được sắp xếp”.** Không có `ORDER BY` bảo đảm nguồn nào được dùng trong câu `UPDATE ... FROM` mơ hồ đó.

### Tại sao có thể thấy kết quả ổn định nhiều lần mà vẫn sai?

Một kế hoạch thực thi có thể liên tục chọn cùng một nguồn trên một bộ dữ liệu nhỏ. Nhưng điều đó không trở thành hợp đồng về **thứ tự lựa chọn**:

- Thống kê dữ liệu thay đổi có thể khiến planner chọn kế hoạch khác.
- Một index được thêm hoặc xóa có thể thay đổi thứ tự gặp các hàng.
- Số hàng tăng hoặc phân bố dữ liệu đổi có thể khiến chiến lược join đổi.
- Nâng phiên bản DBMS hoặc thay đổi cấu hình có thể thay đổi cách thực thi.

**“Trên máy tôi luôn ra 1800” không chứng minh câu SQL đã định nghĩa phải chọn 1800.**

### Định tính, không phải cập nhật hai lần tuần tự

Không nên tưởng tượng PostgreSQL chắc chắn chạy:

```text
UPDATE account 101 SET limit = 1200;
UPDATE account 101 SET limit = 1800;
```

rồi lấy “giá trị cuối cùng”. Theo ngữ nghĩa `UPDATE ... FROM` của PostgreSQL, hàng đích được cập nhật một lần trong câu lệnh, nhưng **cặp nguồn dùng cho hàng đó không xác định**. Đó là rủi ro lựa chọn nguồn, không đơn thuần là thứ tự hai phép gán.

## 5. Giải pháp gốc: bảo đảm nguồn có tối đa một hàng cho mỗi đích

Có hai hướng thiết kế quan trọng:

1. **Ràng buộc dữ liệu:** nếu quan hệ về bản chất là một–một, buộc nguồn duy nhất theo khóa quan hệ.
2. **Chọn hoặc tổng hợp:** nếu quan hệ về bản chất là một–nhiều, viết quy tắc chuyển các ứng viên thành **một kết quả xác định** trước khi cập nhật.

### 5.1. Ràng buộc duy nhất khi dữ liệu phải thật sự một–một

Ví dụ bảng hồ sơ `account_profiles` cần tối đa một hàng trên mỗi `account_id`:

```sql
-- Minh họa schema riêng, không dùng cho bảng proposal nhiều phiên bản.
CREATE TEMP TABLE account_profiles_275 (
    account_id INTEGER PRIMARY KEY,
    new_tier TEXT NOT NULL
);
```

Khóa chính làm cho một `account_id` không thể có hai hồ sơ trong bảng. Một câu `UPDATE ... FROM account_profiles_275` nối bằng `account_id` sẽ có tối đa một hồ sơ cho mỗi tài khoản, **nếu điều kiện nối dùng đúng khóa**.

Nhưng bảng `credit_proposals_275` được thiết kế để chứa **lịch sử nhiều đề xuất**, vì thế không thể đặt `UNIQUE(account_id)` mà vẫn giữ mọi phiên bản. Ràng buộc sai có thể phá yêu cầu nghiệp vụ lưu lịch sử.

### 5.2. Ràng buộc duy nhất có điều kiện

Nếu ứng dụng có khái niệm “mỗi tài khoản chỉ được có một đề xuất đang có hiệu lực”, PostgreSQL hỗ trợ **partial unique index** trong trường hợp phù hợp:

```sql
-- Ví dụ một schema khác có cột is_current:
-- CREATE UNIQUE INDEX one_current_proposal_per_account
-- ON account_proposals (account_id)
-- WHERE is_current = TRUE;
```

Đây chỉ là phác thảo, không áp dụng trực tiếp vào bảng thực hành vì `credit_proposals_275` không có cột `is_current`.

Điều kiện duy nhất cũng cần kiểm soát ở luồng ghi: ai được phép đặt `is_current`, cách chuyển trạng thái trong transaction và điều gì xảy ra nếu hai người cùng cập nhật.

### 5.3. Ràng buộc không thay thế điều kiện JOIN chính xác

Ngay cả khi nguồn có `UNIQUE(tenant_id, account_id)`, câu nối chỉ dùng `account_id` có thể vẫn ghép sai hoặc khớp nhiều hàng qua các tenant. Phải bảo đảm **đúng toàn bộ khóa nghiệp vụ** được đưa vào điều kiện `JOIN`.

## 6. Chọn một nguồn xác định bằng ROW_NUMBER

Đây là mẫu dễ đọc và tương đối dễ chuyển hệ cho bài toán **“lấy bản ghi được duyệt mới nhất”**.

Ý tưởng:

1. Lọc các đề xuất hợp lệ.
2. Đánh số theo từng `account_id`.
3. Xếp `approved_at DESC` để ưu tiên thời điểm mới nhất.
4. Thêm `proposal_id DESC` làm **khóa phá hòa**.
5. Chỉ lấy `rn = 1`.
6. Cập nhật từ tập đã chọn, trong đó mỗi `account_id` có tối đa một hàng.

### Bước 1: Xem trước nguồn được chọn

```sql
WITH ranked_proposals AS (
    SELECT
        p.proposal_id,
        p.account_id,
        p.approved_at,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC,
                     p.proposal_id DESC
        ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
SELECT proposal_id,
       account_id,
       approved_at,
       proposed_limit,
       proposed_tier
FROM ranked_proposals
WHERE rn = 1
ORDER BY account_id;
```

Kết quả:

| account_id | proposal_id | proposed_limit | proposed_tier |
| ---: | ---: | ---: | --- |
| 101 | 2 | 1800 | GOLD |
| 102 | 3 | 1600 | SILVER |
| 103 | 5 | 2200 | PLATINUM |
| 106 | 7 | 2500 | GOLD |

`106` xuất hiện trong **nguồn đã chọn** nhưng chưa có bảng đích tương ứng; khi thực hiện `UPDATE` bằng cách nối với accounts, nó không làm phát sinh một tài khoản mới.

Tài khoản `104` không có ứng viên vì `proposed_limit` thiếu. Tài khoản `105` không có đề xuất nào.

### Tại sao cần proposal_id DESC?

Với tài khoản 103, đề xuất 4 và 5 có **cùng `approved_at`**. Nếu chỉ viết:

```sql
ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY approved_at DESC
)
```

thì việc xếp hàng 4 và 5 vào vị trí `rn = 1` có thể không ổn định vì chúng đồng hạng theo tiêu chí duy nhất.

Khi thêm `proposal_id DESC`, đề xuất 5 được chọn rõ ràng. `proposal_id` là khóa chính duy nhất nên mọi ứng viên của cùng tài khoản có thứ tự toàn phần theo cặp `(approved_at, proposal_id)`.

**Phá hòa không phải trang trí cú pháp.** Nếu quy tắc nghiệp vụ không cho phép dùng ID lớn hơn làm ưu tiên, phải đưa ra quy tắc khác có căn cứ: ưu tiên trạng thái, mức phê duyệt, phiên bản duy nhất hoặc thời điểm hệ thống nhận. Không được tự chọn một hàng tùy ý chỉ để làm truy vấn chạy.

### Bước 2: UPDATE an toàn trong transaction

Ví dụ dưới đây thực sự thay đổi bảng tạm nhưng **sẽ được ROLLBACK ở cuối**. Chỉ chạy trên bộ dữ liệu thực hành.

```sql
BEGIN;

WITH ranked_proposals AS (
    SELECT
        p.proposal_id,
        p.account_id,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC,
                     p.proposal_id DESC
        ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
),
chosen_proposals AS (
    SELECT proposal_id,
           account_id,
           proposed_limit,
           proposed_tier
    FROM ranked_proposals
    WHERE rn = 1
)
UPDATE credit_accounts_275 AS a
SET credit_limit     = c.proposed_limit,
    tier             = c.proposed_tier,
    last_proposal_id = c.proposal_id
FROM chosen_proposals AS c
WHERE a.account_id = c.account_id
RETURNING
    a.account_id,
    a.credit_limit,
    a.tier,
    a.last_proposal_id;

SELECT account_id,
       credit_limit,
       tier,
       last_proposal_id
FROM credit_accounts_275
ORDER BY account_id;

ROLLBACK;
```

Kết quả mong đợi trong transaction:

| account_id | credit_limit | tier | last_proposal_id |
| ---: | ---: | --- | ---: |
| 101 | 1800 | GOLD | 2 |
| 102 | 1600 | SILVER | 3 |
| 103 | 2200 | PLATINUM | 5 |
| 104 | 900 | BASIC | `NULL` |
| 105 | 1100 | BASIC | `NULL` |

`UPDATE ... RETURNING` chỉ trả những hàng đã cập nhật (101, 102, 103); thứ tự từ `RETURNING` không được bảo đảm nếu không có một cấp truy vấn sắp xếp riêng. `SELECT` sau đó xem toàn bộ trạng thái bảng đích trong transaction.

`ROLLBACK` khôi phục bảng tạm về dữ liệu ban đầu trước ví dụ cập nhật. Nếu bạn thay `ROLLBACK` bằng `COMMIT`, các thay đổi trong phiên thực hành được giữ cho tới khi bảng tạm bị xóa/kết thúc phiên theo cấu hình.

### Vì sao chọn đủ một hàng là điều kiện quan trọng?

CTE `chosen_proposals` có **tối đa một hàng cho mỗi `account_id`**, nên phép nối cập nhật không còn phải lựa chọn giữa đề xuất 1 hay 2, giữa đề xuất 4 hay 5.

Nguồn được chọn cũng giữ **trọn bộ cột của cùng một đề xuất**: hạn mức, hạng, ID đề xuất đều lấy từ đúng một hàng.

## 7. PostgreSQL DISTINCT ON: lựa chọn gọn khi cần một hàng mỗi khóa

PostgreSQL có cú pháp `DISTINCT ON`, hữu ích khi cần **một hàng đầu tiên trên mỗi nhóm khóa**:

```sql
SELECT DISTINCT ON (p.account_id)
       p.account_id,
       p.proposal_id,
       p.proposed_limit,
       p.proposed_tier,
       p.approved_at
FROM credit_proposals_275 AS p
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
ORDER BY p.account_id,
         p.approved_at DESC,
         p.proposal_id DESC;
```

Kết quả lựa chọn nguồn tương tự `ROW_NUMBER() ... WHERE rn = 1`.

### Đọc quy tắc

- `DISTINCT ON (account_id)`: giữ **một hàng** cho từng account.
- `ORDER BY account_id`: các hàng cùng account đứng cùng nhóm và tuân thủ yêu cầu cú pháp của PostgreSQL.
- `approved_at DESC`: đề xuất mới hơn được ưu tiên.
- `proposal_id DESC`: phá hòa nếu thời điểm trùng nhau.

Đây là **cú pháp riêng của PostgreSQL**, không thể mang nguyên văn sang SQL Server hoặc MySQL.

### UPDATE từ DISTINCT ON

```sql
BEGIN;

WITH chosen AS (
    SELECT DISTINCT ON (p.account_id)
           p.account_id,
           p.proposal_id,
           p.proposed_limit,
           p.proposed_tier
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
    ORDER BY p.account_id,
             p.approved_at DESC,
             p.proposal_id DESC
)
UPDATE credit_accounts_275 AS a
SET credit_limit     = c.proposed_limit,
    tier             = c.proposed_tier,
    last_proposal_id = c.proposal_id
FROM chosen AS c
WHERE c.account_id = a.account_id;

ROLLBACK;
```

`DISTINCT ON` gọn, nhưng điều kiện bắt buộc vẫn là **`ORDER BY` thể hiện đúng ưu tiên và phá hòa**. Nếu chỉ viết `DISTINCT ON (account_id)` mà không có thứ tự đáng tin cậy, kết quả “hàng đầu tiên” không có ý nghĩa xác định.

## 8. LATERAL và truy vấn con chọn TOP 1 / LIMIT 1

Một cách khác là thực hiện **lựa chọn nguồn riêng cho từng hàng đích**, hữu ích khi mỗi tài khoản cần tìm bản ghi gần nhất theo các điều kiện tương quan.

### PostgreSQL LEFT JOIN LATERAL để kiểm tra trước

```sql
SELECT
    a.account_id,
    a.credit_limit AS old_limit,
    p.proposal_id,
    p.proposed_limit,
    p.proposed_tier
FROM credit_accounts_275 AS a
LEFT JOIN LATERAL (
    SELECT
        p.proposal_id,
        p.proposed_limit,
        p.proposed_tier
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
    ORDER BY p.approved_at DESC,
             p.proposal_id DESC
    LIMIT 1
) AS p ON TRUE
ORDER BY a.account_id;
```

Kết quả:

| account_id | old_limit | proposal_id | proposed_limit |
| ---: | ---: | ---: | ---: |
| 101 | 1000 | 2 | 1800 |
| 102 | 1500 | 3 | 1600 |
| 103 | 2000 | 5 | 2200 |
| 104 | 900 | `NULL` | `NULL` |
| 105 | 1100 | `NULL` | `NULL` |

`LATERAL` cho phép truy vấn con tham chiếu `a.account_id` của hàng đích đang xét. `LIMIT 1` chỉ hợp lý vì đã có **`ORDER BY` đầy đủ**.

Nếu bỏ `ORDER BY`:

```sql
-- Không an toàn khi có nhiều ứng viên:
-- SELECT ...
-- FROM credit_proposals_275 AS p
-- WHERE p.account_id = a.account_id
-- LIMIT 1;
```

thì “một hàng bất kỳ” không trở thành nguồn đúng theo nghiệp vụ chỉ vì có `LIMIT 1`.

Trong SQL Server, các trường hợp tương tự thường được diễn đạt bằng `OUTER APPLY` cùng `TOP (1) ... ORDER BY ...`; cú pháp chi tiết khác PostgreSQL.

### Vì sao không luôn chọn LATERAL?

Cách lựa chọn theo từng hàng có thể thuận lợi cho một số mẫu index và số lượng đích phù hợp, nhưng hiệu năng cần đo trên dữ liệu thật. Với hàng triệu tài khoản và một bảng lịch sử lớn, bộ tối ưu có nhiều cách lập kế hoạch; không thể khẳng định `LATERAL` luôn nhanh hơn `ROW_NUMBER` hoặc ngược lại.

## 9. Khi có nhiều nguồn, tổng hợp là một lựa chọn khác

Không phải quan hệ một–nhiều nào cũng cần **chọn một hàng**. Có trường hợp nghiệp vụ muốn **tổng hợp tất cả nguồn**.

Ví dụ một tài khoản có nhiều dòng điều chỉnh cộng dồn, và mục tiêu là tổng số tiền của các điều chỉnh đã duyệt:

```sql
WITH totals AS (
    SELECT
        account_id,
        SUM(proposed_limit) AS combined_amount
    FROM credit_proposals_275
    WHERE proposal_status = 'APPROVED'
      AND proposed_limit IS NOT NULL
    GROUP BY account_id
)
SELECT account_id, combined_amount
FROM totals
ORDER BY account_id;
```

Truy vấn có **tối đa một hàng mỗi account** vì `GROUP BY account_id`. Nhưng hãy chú ý: với dữ liệu bài học, `proposed_limit` là **hạn mức đề xuất thay thế**, không phải “khoản tiền điều chỉnh phải cộng”. Do đó **cộng các hạn mức đề xuất là sai nghiệp vụ** dù SQL chạy được.

### Chọn đúng hàm cho đúng ý nghĩa

| Ý nghĩa bảng nguồn | Cách xử lý thường phù hợp |
| --- | --- |
| Nhiều khoản thu/chi cần cộng vào tổng | `SUM(amount)` theo khóa đích |
| Nhiều sự kiện cần đếm | `COUNT(*)` hoặc `COUNT(event_id)` |
| Nhiều kết quả kiểm tra, cần mức cao nhất | `MAX(score)` nếu nghiệp vụ đúng là chọn giá trị lớn nhất |
| Nhiều phiên bản cấu hình, cần bản mới nhất | Chọn **toàn bộ một hàng** theo timestamp và khóa phá hòa |
| Nhiều đề xuất, chỉ một bản đã được phê duyệt có hiệu lực | Ràng buộc dữ liệu hoặc chọn theo trạng thái hiệu lực |
| Nhiều bản nguồn vì JOIN thiếu khóa | **Sửa điều kiện JOIN**, không tổng hợp để che lỗi |

**`GROUP BY` có thể tạo một hàng mỗi đích nhưng không tự chứng minh giá trị tổng hợp là đúng.**

## 10. Không lấy MAX của từng cột rồi ghép thành một bản ghi giả

Một cách sửa có vẻ đơn giản:

```sql
-- Cố ý sai ngữ nghĩa nếu cần lấy toàn bộ một đề xuất.
SELECT
    account_id,
    MAX(proposed_limit) AS chosen_limit,
    MAX(proposed_tier) AS chosen_tier
FROM credit_proposals_275
WHERE proposal_status = 'APPROVED'
  AND proposed_limit IS NOT NULL
GROUP BY account_id;
```

Câu này có một hàng cho mỗi account, nhưng `MAX(proposed_limit)` và `MAX(proposed_tier)` được tính **độc lập**:

- Với account 101, hạn mức lớn nhất là **1800** (đề xuất 2, hạng GOLD).
- Tên hạng lớn nhất theo thứ tự so sánh chuỗi có thể là **SILVER** (đề xuất 1), vì `'SILVER'` được xếp sau `'GOLD'` trong thứ tự chữ thông dụng.

Kết quả có thể tạo ra cặp **(1800, SILVER)**, **không tồn tại trên bất kỳ một đề xuất nào**.

Đây là lỗi *mixing attributes across rows*: lấy từng thuộc tính từ những hàng nguồn khác nhau rồi ghép thành một “bản ghi” không có thật.

Nếu nghiệp vụ muốn bản mới nhất, hãy **xếp hạng hàng** bằng `ROW_NUMBER`/`DISTINCT ON`, sau đó lấy **mọi cột từ chính hàng đã chọn**.

### MAX theo thời gian rồi JOIN ngược cũng có bẫy hòa

```sql
WITH max_dates AS (
    SELECT account_id,
           MAX(approved_at) AS latest_approved_at
    FROM credit_proposals_275
    WHERE proposal_status = 'APPROVED'
      AND proposed_limit IS NOT NULL
    GROUP BY account_id
)
SELECT p.*
FROM credit_proposals_275 AS p
JOIN max_dates AS m
  ON p.account_id = m.account_id
 AND p.approved_at = m.latest_approved_at
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

Tài khoản **103** vẫn có **hai hàng**, vì đề xuất 4 và 5 cùng `approved_at`. Mẫu “lấy `MAX(timestamp)` rồi nối lại” chưa loại được đồng hạng nếu timestamp không duy nhất.

Cần thêm **quy tắc phá hòa** hoặc ràng buộc đảm bảo không thể có hai phiên bản cùng thời điểm theo khóa nghiệp vụ.

## 11. SELECT DISTINCT không giải quyết mọi trường hợp

Có người thử sửa dữ liệu nguồn bằng:

```sql
SELECT DISTINCT
       account_id,
       proposed_limit,
       proposed_tier
FROM credit_proposals_275
WHERE proposal_status = 'APPROVED';
```

`DISTINCT` chỉ loại các hàng **giống nhau trên toàn bộ cột được chọn**. Nó không gộp account 101 có hạn mức 1200 và 1800, cũng không gộp account 103 có hạn mức 2100 và 2200.

Nếu chỉ chọn:

```sql
SELECT DISTINCT account_id
FROM credit_proposals_275;
```

thì được một hàng mỗi account nhưng **đã làm mất giá trị cần cập nhật**. Không thể dùng một tập chỉ có `account_id` để suy ra hạn mức và hạng nên lấy từ đề xuất nào.

### Khi DISTINCT có ý nghĩa

`DISTINCT` có ích nếu nguồn lặp lại **hoàn toàn giống nhau** và bạn chỉ cần tập các khóa có tồn tại. Nhưng đối với câu cập nhật nhiều cột theo **một phiên bản nguồn xác định**, phải có quy tắc chọn một bản ghi thay vì chỉ khử trùng một số trường.

## 12. Truy vấn con một giá trị: lỗi rõ ràng khi có nhiều hàng

PostgreSQL hỗ trợ cập nhật một cột bằng **scalar subquery**:

```sql
-- Chỉ minh họa: KHÔNG chạy UPDATE này trên dữ liệu mẫu.
--
-- UPDATE credit_accounts_275 AS a
-- SET credit_limit = (
--     SELECT p.proposed_limit
--     FROM credit_proposals_275 AS p
--     WHERE p.account_id = a.account_id
--       AND p.proposal_status = 'APPROVED'
--       AND p.proposed_limit IS NOT NULL
-- );
```

Một truy vấn con dùng làm **giá trị vô hướng** được kỳ vọng trả **tối đa một hàng và một cột**:

- Trả một hàng → dùng giá trị cột đó.
- Trả không hàng nào → kết quả vô hướng là `NULL`.
- Trả **nhiều hơn một hàng** → PostgreSQL báo lỗi kiểu “more than one row returned by a subquery used as an expression”.

Với account 101, truy vấn con trả hai hạn mức. Khác `UPDATE ... FROM`, PostgreSQL sẽ **không âm thầm chọn một** từ hai kết quả của scalar subquery này.

### Dùng SELECT để quan sát lỗi mà không cập nhật

```sql
-- PostgreSQL: truy vấn chẩn đoán có chủ đích gây lỗi >1 hàng.
-- Chạy riêng nếu muốn xem thông báo của DBMS, không sửa dữ liệu.
SELECT (
    SELECT p.proposed_limit
    FROM credit_proposals_275 AS p
    WHERE p.account_id = 101
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
) AS ambiguous_value;
```

Do có hai đề xuất hợp lệ của account 101, PostgreSQL báo lỗi thay vì chọn 1200 hay 1800.

### Một bẫy khác: không có hàng nguồn

Nếu scalar subquery trả không hàng cho account 105, giá trị nhận là `NULL`. Vì `credit_limit` của bảng thực hành được khai báo `NOT NULL`, một câu cập nhật tất cả tài khoản có thể lỗi khi cố gán `NULL`.

Nếu nguồn có thể thiếu, hãy quyết định:

- **Giữ nguyên** hàng đích không có đề xuất.
- **Báo lỗi** để người vận hành xử lý.
- **Gán mặc định** nếu chính sách nghiệp vụ cho phép.

Đừng mặc định `COALESCE(NULL,0)` là quyết định đúng cho hạn mức tín dụng.

### Khi nào scalar subquery hợp lý?

Khi schema hoặc truy vấn đã **bảo đảm tối đa một hàng**, scalar subquery mô tả quan hệ khá rõ. Việc “fail fast” khi có nhiều hàng có thể là ưu điểm để phát hiện dữ liệu sai. Tuy nhiên, nó không tự chọn bản mới nhất; muốn chọn phải viết rõ quy tắc, ví dụ `ORDER BY ... LIMIT 1` nếu DBMS và ngữ cảnh hỗ trợ, hoặc chuẩn bị tập nguồn duy nhất.

## 13. MERGE: đừng trông đợi nó tự chọn một nguồn

`MERGE` thường dùng để đối chiếu nguồn với đích rồi `UPDATE`, `INSERT` hoặc `DELETE` tùy điều kiện. Nó **không phải** một giải pháp phép màu cho quan hệ nguồn nhiều hàng.

Ví dụ PostgreSQL 15+:

```sql
-- Minh họa cú pháp, KHÔNG chạy trước khi làm duy nhất nguồn.
--
-- MERGE INTO credit_accounts_275 AS a
-- USING credit_proposals_275 AS p
-- ON a.account_id = p.account_id
-- WHEN MATCHED
--      AND p.proposal_status = 'APPROVED'
--      AND p.proposed_limit IS NOT NULL
-- THEN UPDATE
--      SET credit_limit = p.proposed_limit,
--          tier = p.proposed_tier;
```

Nếu nhiều hàng nguồn khớp cùng một hàng đích và cố tác động cập nhật hàng đó nhiều lần, PostgreSQL `MERGE` có thể **báo lỗi vi phạm số lần tác động/cardinality** thay vì chọn tùy ý. Cụ thể hành vi còn phụ thuộc điều kiện, hành động và phiên bản, nên phải kiểm tra trường hợp truy vấn đang dùng.

Oracle cũng có thể báo lỗi kiểu `ORA-30926` khi tập nguồn không ổn định cho thao tác MERGE; điều kiện xảy ra và cách xử lý chi tiết phụ thuộc phiên bản, dữ liệu và hành động. Không nên viết quy tắc đơn giản hóa “mọi MERGE có nguồn trùng đều báo một lỗi giống nhau” cho mọi DBMS.

### Chuẩn bị nguồn trước MERGE

Một hướng rõ ràng là chọn nguồn:

```sql
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY approved_at DESC, proposal_id DESC
        ) AS rn
    FROM credit_proposals_275 AS p
    WHERE proposal_status = 'APPROVED'
      AND proposed_limit IS NOT NULL
),
chosen AS (
    SELECT account_id,
           proposal_id,
           proposed_limit,
           proposed_tier
    FROM ranked
    WHERE rn = 1
)
SELECT *
FROM chosen
ORDER BY account_id;
```

Chỉ khi `chosen` đã đáp ứng ràng buộc “tối đa một nguồn trên mỗi khóa đích” mới dùng nó làm nguồn cho `MERGE` hoặc `UPDATE ... FROM`.

### MERGE có thêm trách nhiệm về hàng không khớp

Với đề xuất account 106, nguồn tồn tại nhưng đích không có account. Trong `UPDATE` thuần, nguồn này không tạo hàng mới. Với `MERGE ... WHEN NOT MATCHED THEN INSERT`, nó **có thể tạo hàng đích mới** nếu điều kiện và dữ liệu đủ hợp lệ.

Đó là hành vi hoàn toàn khác; trước khi chọn `MERGE` phải xác định có cho phép tạo bản ghi đích mới hay không.

## 14. DELETE ... USING và quan hệ nguồn nhiều hàng

Vấn đề trong **DELETE** có liên quan nhưng không giống **UPDATE**.

PostgreSQL cho phép:

```sql
DELETE FROM target_table AS t
USING source_table AS s
WHERE s.business_key = t.business_key
  AND s.some_condition;
```

Nếu một hàng đích khớp **nhiều hàng nguồn**, bản thân hàng đích chỉ bị xóa **một lần**. Không có bài toán “lấy giá trị từ hàng nguồn nào để gán vào cột” như `UPDATE ... FROM`.

Tuy nhiên, nhiều hàng nguồn vẫn có thể khiến:

- Nhiều hàng đích bị xóa **ngoài ý định** nếu điều kiện nối thiếu khóa.
- Quy tắc “chỉ xóa khi mọi đề xuất đều không hợp lệ” bị diễn đạt thành “xóa nếu tồn tại một đề xuất không hợp lệ”.
- Tập kết quả `JOIN` dùng để dự đoán số hàng bị xóa lớn hơn số hàng đích thực tế.
- Các điều kiện `OR`/`AND` đặt sai làm phạm vi xóa rộng ra.

### Ví dụ sai về nghiệp vụ: có một đề xuất bị từ chối

```sql
-- NGUY HIỂM: chỉ là ví dụ cú pháp; không thực thi.
--
-- DELETE FROM credit_accounts_275 AS a
-- USING credit_proposals_275 AS p
-- WHERE p.account_id = a.account_id
--   AND p.proposal_status = 'REJECTED';
```

Câu này sẽ nhắm tới **account 102** vì có đề xuất 8 bị từ chối, mặc dù **account 102 vẫn có đề xuất 3 đã duyệt**. Nếu ý định là “xóa tài khoản chỉ khi không có đề xuất hợp lệ nào”, điều kiện `EXISTS` trên một đề xuất bị từ chối là **sai quy tắc**.

### Dùng NOT EXISTS để diễn đạt điều kiện phủ định

Ví dụ nghiệp vụ khác: tìm tài khoản **chưa từng có đề xuất nào**.

```sql
SELECT a.account_id,
       a.customer_name
FROM credit_accounts_275 AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
)
ORDER BY a.account_id;
```

Kết quả là **account 105**.

Nếu cần xóa theo đúng quy tắc này trong môi trường thực hành, có thể dùng transaction:

```sql
-- Chỉ chạy trên bảng tạm và ROLLBACK sau khi kiểm tra.
BEGIN;

DELETE FROM credit_accounts_275 AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
)
RETURNING a.account_id, a.customer_name;

ROLLBACK;
```

`NOT EXISTS` diễn đạt: “không có **bất kỳ** hàng đề xuất nào khớp account này”. Nó không quan tâm có bao nhiêu đề xuất ở những account khác; khi điều kiện tương quan đúng, số dòng nguồn không gây lựa chọn giá trị mơ hồ.

### Khác nhau giữa ba yêu cầu xóa

| Yêu cầu nghiệp vụ | Logic cần suy nghĩ |
| --- | --- |
| Xóa account có **ít nhất một** đề xuất bị từ chối | `EXISTS` với `status = 'REJECTED'` |
| Xóa account **không có đề xuất nào** | `NOT EXISTS` theo khóa account |
| Xóa account **không có đề xuất hợp lệ** | `NOT EXISTS` với điều kiện `APPROVED` và giá trị hợp lệ bên trong |

Hai câu `NOT EXISTS` cuối khác nhau. Với account 104, có đề xuất nhưng hạn mức `NULL`: nó **không thiếu mọi đề xuất**, nhưng **thiếu đề xuất hợp lệ** theo quy ước bài học.

Không nên chuyển giữa những điều kiện này chỉ vì chúng đều có từ “không”.

## 15. Tìm nguồn lặp và làm rõ quy tắc “mọi” so với “tồn tại”

Nhiều yêu cầu cập nhật/xóa có các từ “có ít nhất một”, “không có”, “tất cả”, “bản mới nhất” hoặc “bản ưu tiên”. Mỗi yêu cầu nên dẫn đến cấu trúc khác.

### “Có ít nhất một bản hợp lệ”

```sql
SELECT a.account_id
FROM credit_accounts_275 AS a
WHERE EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
ORDER BY a.account_id;
```

Kết quả: **101, 102, 103**.

### “Không có bản hợp lệ nào”

```sql
SELECT a.account_id
FROM credit_accounts_275 AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
ORDER BY a.account_id;
```

Kết quả: **104 và 105**.

### “Có đúng một bản hợp lệ”

```sql
SELECT a.account_id,
       COUNT(*) AS valid_proposal_count
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
GROUP BY a.account_id
HAVING COUNT(*) = 1
ORDER BY a.account_id;
```

Kết quả: **102**.

### “Lấy bản hợp lệ mới nhất”

Cần `ROW_NUMBER`, `DISTINCT ON` hoặc một cách chọn đúng một bản có tiêu chí `ORDER BY` phá hòa. `EXISTS` chỉ xác nhận có hàng, **không cung cấp hạn mức nên gán**.

## 16. NULL trong nguồn và điều kiện nối

`NULL` không phải số 0 và không mặc định là “giữ giá trị cũ”.

Trong bảng mẫu, đề xuất 6 cho account 104 có `proposed_limit = NULL`. Nếu bỏ điều kiện lọc và cập nhật:

```sql
-- KHÔNG CHẠY: nếu gán NULL vào credit_limit NOT NULL,
-- PostgreSQL sẽ báo lỗi ràng buộc.
--
-- UPDATE credit_accounts_275 AS a
-- SET credit_limit = p.proposed_limit
-- FROM credit_proposals_275 AS p
-- WHERE p.account_id = a.account_id
--   AND p.proposal_status = 'APPROVED';
```

việc gán `NULL` vào `credit_limit` có thể bị ràng buộc từ chối. Nếu cột đích cho phép `NULL`, thao tác lại có thể xóa đi một giá trị đang biết thành giá trị thiếu — cũng không nhất thiết đúng nghiệp vụ.

### COALESCE không tự giải quyết dữ liệu nguồn nhiều hàng

```sql
-- Chỉ là ví dụ; KHÔNG khắc phục tình trạng một đích nhiều nguồn:
SET credit_limit = COALESCE(p.proposed_limit, a.credit_limit)
```

Biểu thức này cho phép giữ hạn mức cũ khi **nguồn được chọn** có hạn mức `NULL`, nhưng nó **không xác định được nguồn nào được chọn** nếu một account có nhiều đề xuất.

Hãy giải quyết hai câu hỏi độc lập:

1. **Nguồn nào là hợp lệ và được ưu tiên?**
2. **Nếu cột của nguồn đã chọn là NULL thì làm gì?**

Không nên dùng `COALESCE` như một cách che dấu dữ liệu sai hoặc thay thế việc xác định nguồn.

### Khóa nối có NULL

Điều kiện:

```sql
p.account_id = a.account_id
```

không khớp nếu một trong hai giá trị là `NULL` vì phép so sánh cho UNKNOWN. Trong bảng mẫu, cả hai khóa liên quan đều không `NULL`. Với khóa tùy chọn, phải xác định hợp đồng dữ liệu trước khi dùng `IS NOT DISTINCT FROM` để coi hai `NULL` là khớp.

Hai giá trị “chưa biết” không tự chứng minh chúng cùng một thực thể.

## 17. Khóa ghép và nguy cơ cập nhật chéo tenant

Trong hệ thống nhiều tenant, ID có thể chỉ duy nhất **bên trong một tenant**.

```text
tenant_id | account_id
----------+-----------
T1        | 101
T2        | 101
```

Nếu bảng đích có khóa `(tenant_id, account_id)`, câu cập nhật chỉ nối theo `account_id`:

```sql
-- Sai nếu cùng account_id xuất hiện ở nhiều tenant:
-- ON s.account_id = t.account_id
```

có thể ghép nguồn của T2 vào tài khoản T1, hoặc tạo nhiều nguồn cho cùng một đích.

Điều kiện đúng cần đủ thành phần:

```sql
-- Mẫu đúng cho khóa ghép:
-- ON s.tenant_id  = t.tenant_id
-- AND s.account_id = t.account_id
```

Và nếu cần `ROW_NUMBER` để chọn một nguồn mỗi đích:

```sql
ROW_NUMBER() OVER (
    PARTITION BY tenant_id, account_id
    ORDER BY approved_at DESC, proposal_id DESC
)
```

Nếu chỉ phân hoạch theo `account_id`, một nguồn của tenant này có thể được xếp cạnh tranh với nguồn của tenant khác ngay cả khi bước `UPDATE` sau đó dùng đủ cặp khóa.

**Điều kiện JOIN, khóa phân hoạch của ROW_NUMBER và ràng buộc UNIQUE phải cùng phản ánh một định nghĩa danh tính nghiệp vụ.**

## 18. ORDER BY bên trong truy vấn nguồn không đảm bảo UPDATE chọn đúng

Một nỗ lực sửa thường gặp:

```sql
-- KHÔNG đủ để giải quyết trùng nguồn:
-- UPDATE credit_accounts_275 AS a
-- SET credit_limit = p.proposed_limit
-- FROM (
--     SELECT account_id, proposed_limit
--     FROM credit_proposals_275
--     WHERE proposal_status = 'APPROVED'
--     ORDER BY approved_at DESC
-- ) AS p
-- WHERE p.account_id = a.account_id;
```

Dù truy vấn con `p` có `ORDER BY approved_at DESC`, nó **vẫn trả nhiều hàng cho account 101 và 103**. Sắp xếp không biến quan hệ một–nhiều thành một–một.

Tương tự:

```sql
-- LIMIT 1 áp dụng cho TOÀN BỘ tập nguồn,
-- không phải một bản ghi cho MỖI account.
-- SELECT ...
-- FROM credit_proposals_275
-- ORDER BY approved_at DESC
-- LIMIT 1;
```

Nếu đưa câu trên thành nguồn cập nhật, nó chỉ chọn **một đề xuất trên toàn bảng**, không chọn một đề xuất cho từng account.

Muốn lấy một nguồn mỗi account, phải dùng kỹ thuật **partitioned ranking** (`ROW_NUMBER PARTITION BY account_id`), `DISTINCT ON` của PostgreSQL hoặc subquery tương quan `ORDER BY ... LIMIT 1` cho từng account.

## 19. Tính xác định không có nghĩa đúng nghiệp vụ

Một câu SQL có thể **hoàn toàn xác định** về mặt kỹ thuật nhưng vẫn **sai yêu cầu kinh doanh**.

Ví dụ:

```sql
SELECT DISTINCT ON (account_id)
       account_id, proposal_id, proposed_limit
FROM credit_proposals_275
ORDER BY account_id, proposal_id ASC;
```

Truy vấn này chọn **đề xuất có ID nhỏ nhất** của mỗi account. Kết quả xác định vì `proposal_id` là khóa duy nhất, nhưng account 101 sẽ lấy **đề xuất cũ** (ID 1, 1200) thay vì đề xuất được duyệt mới nhất (ID 2, 1800).

Tính đúng đắn cần đồng thời:

1. **Quy tắc chọn hàng rõ ràng:** có tiêu chí ưu tiên và phá hòa.
2. **Quy tắc phù hợp nghiệp vụ:** chọn bản đúng theo trạng thái và thời điểm hiệu lực.
3. **Ràng buộc kỹ thuật bảo vệ đầu ra:** tối đa một nguồn cho mỗi đích.
4. **Quy tắc dữ liệu thiếu:** nguồn không có, giá trị `NULL` và bản bị từ chối.
5. **Quy tắc thực thi đồng thời:** dữ liệu không bị thay đổi ngoài kiểm soát trong lúc xác định và ghi.

Không nên xem `ORDER BY proposal_id DESC` là “bản mới nhất” trừ khi cơ chế sinh ID bảo đảm điều đó theo hợp đồng dữ liệu.

## 20. Cạnh tranh cập nhật và transaction: một vấn đề khác với nhiều nguồn

**Nondeterministic UPDATE** do một đích khớp nhiều nguồn là vấn đề **ngữ nghĩa truy vấn**. **Concurrent update** là vấn đề hai transaction hoặc quy trình có thể thay đổi dữ liệu cùng lúc.

Ngay cả khi mỗi lần truy vấn đã chọn đúng một nguồn, vẫn cần cân nhắc:

- Một transaction khác có thể ghi thêm đề xuất sau khi ta đọc danh sách ứng viên.
- Một transaction khác có thể sửa account đích trước hoặc trong quá trình cập nhật.
- Nếu đọc dữ liệu để chọn rồi viết trong **hai câu SQL riêng biệt**, trạng thái dữ liệu có thể thay đổi giữa hai bước.
- Mức cô lập transaction quyết định cách mỗi câu lệnh nhìn thấy snapshot dữ liệu.
- Các cơ chế khóa và ràng buộc có thể cần thiết khi nghiệp vụ đòi hỏi đảm bảo mạnh hơn.

### Một câu UPDATE với CTE có lợi gì?

Câu:

```sql
WITH ranked AS (...),
chosen AS (...)
UPDATE ...
FROM chosen ...
```

cho bộ tối ưu và DBMS thực hiện việc chọn nguồn và cập nhật trong **cùng câu lệnh**, có thể giảm những cửa sổ bất nhất do ứng dụng tách riêng `SELECT` và `UPDATE`.

Nhưng **không phải** điều đó tự bảo đảm quy tắc “không ai thêm đề xuất mới trong khi đang thực thi” cho mọi mức cô lập và lịch giao dịch. Hệ thống cần đặc tả nhất quán rõ, ràng buộc phù hợp và có thể phải dùng khóa, mức cô lập cao hơn hoặc cơ chế phiên bản để giải quyết.

### Transaction dùng để kiểm tra mà không giữ thay đổi

Trong môi trường học, mẫu:

```sql
BEGIN;

-- UPDATE ... RETURNING ...;

-- SELECT kiểm tra những hàng đích vừa thay đổi;

ROLLBACK;
```

giúp bạn xem tác động rồi hoàn tác. Tuy nhiên, **không nên coi ROLLBACK là hàng rào an toàn tuyệt đối** cho mọi thao tác trên mọi hệ thống: có các tác dụng phụ ngoài database, trigger gọi dịch vụ ngoài, sequence không được rollback theo cách người mới thường nghĩ, hoặc môi trường không cho phép transaction như dự kiến.

Trong bài này, chỉ chạy ví dụ trên **bảng tạm đã tạo**, không dùng để thử trên hệ thống thật.

## 21. Kiểm chứng tập nguồn trước khi thực thi

Một quy trình thực hành quan trọng là tách **chẩn đoán** khỏi **ghi dữ liệu**.

### 21.1. Kiểm tra số ứng viên trên từng đích

```sql
SELECT a.account_id,
       COUNT(p.proposal_id) AS candidate_count
FROM credit_accounts_275 AS a
LEFT JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
 AND p.proposal_status = 'APPROVED'
 AND p.proposed_limit IS NOT NULL
GROUP BY a.account_id
ORDER BY a.account_id;
```

Kết quả:

| account_id | candidate_count |
| ---: | ---: |
| 101 | 2 |
| 102 | 1 |
| 103 | 2 |
| 104 | 0 |
| 105 | 0 |

`COUNT(p.proposal_id)` đếm **hàng nguồn khớp thực sự**. Nếu dùng `COUNT(*)` sau `LEFT JOIN`, account 104 và 105 vẫn có thể có số đếm 1 do hàng bảo toàn bên trái; đó không phải một đề xuất thật.

### 21.2. Kiểm tra nguồn đã được lựa chọn là duy nhất

```sql
WITH ranked AS (
    SELECT p.account_id,
           p.proposal_id,
           ROW_NUMBER() OVER (
               PARTITION BY p.account_id
               ORDER BY p.approved_at DESC, p.proposal_id DESC
           ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
),
chosen AS (
    SELECT account_id, proposal_id
    FROM ranked
    WHERE rn = 1
)
SELECT account_id,
       COUNT(*) AS chosen_rows
FROM chosen
GROUP BY account_id
HAVING COUNT(*) > 1;
```

Không có hàng nào trong kết quả khi `chosen` đúng như mẫu trên. `ROW_NUMBER ... rn=1` tạo tối đa một hàng theo mỗi khóa phân hoạch; điều kiện này chủ yếu minh họa **cách quan sát hợp đồng duy nhất** và thuận tiện nếu logic chuẩn bị nguồn được thay đổi về sau.

### 21.3. Xem “trước và sau” trên bản ghi đích

```sql
WITH ranked AS (
    SELECT
        p.account_id,
        p.proposal_id,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC, p.proposal_id DESC
        ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
),
chosen AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
SELECT
    a.account_id,
    a.credit_limit AS before_limit,
    c.proposed_limit AS after_limit,
    a.tier AS before_tier,
    c.proposed_tier AS after_tier,
    c.proposal_id AS from_proposal_id
FROM credit_accounts_275 AS a
JOIN chosen AS c
  ON c.account_id = a.account_id
ORDER BY a.account_id;
```

Câu `SELECT` trên chưa thay đổi dữ liệu; nó giúp kiểm tra kế hoạch cập nhật trước khi dùng `UPDATE`.

### 21.4. Ghi nhận nguồn gốc cập nhật

Cột `last_proposal_id` trong bảng đích là một ví dụ về **provenance**: chỉ ra dữ liệu được lấy từ bản nguồn nào.

Nếu update chỉ gán hạn mức mà không lưu ID đề xuất, việc truy vết “vì sao account 103 có limit 2200?” sẽ khó hơn. Trong hệ thống thật, có thể bổ sung lịch sử thay đổi, thời điểm cập nhật, tác nhân thực hiện và giá trị trước/sau theo yêu cầu kiểm toán.

Việc lưu ID nguồn phải dùng **chính ID của hàng được chọn**, không tính `MAX(proposal_id)` độc lập với hạn mức và hạng.

## 22. An toàn khi DELETE: dự đoán số đích, không đếm số cặp JOIN

Một câu `DELETE ... USING` có thể khớp nhiều nguồn cho cùng một đích nhưng **xóa một hàng đích một lần**. Nếu dự đoán số hàng bị xóa bằng:

```sql
SELECT COUNT(*)
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

kết quả là **5**, nhưng số **tài khoản đích phân biệt** thỏa điều kiện chỉ là **3**.

Nếu thật sự muốn đếm tài khoản bị tác động, có thể dùng:

```sql
SELECT COUNT(DISTINCT a.account_id) AS affected_accounts
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

Kết quả là **3**.

Hoặc dùng `EXISTS` để diễn đạt chính xác điều kiện tồn tại và tránh việc tạo các cặp hàng không cần thiết:

```sql
SELECT COUNT(*) AS affected_accounts
FROM credit_accounts_275 AS a
WHERE EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
);
```

Điều này rất hữu ích để kiểm tra phạm vi xóa trước khi dùng câu `DELETE`.

**Cảnh báo:** dự đoán bằng `SELECT` không tự khóa dữ liệu hoặc đảm bảo số hàng sẽ giống hệt nếu có transaction khác sửa dữ liệu trước thao tác xóa. Nếu cần tính nhất quán nghiêm ngặt, phải thiết kế transaction và cơ chế khóa phù hợp.

## 23. SQL Server: UPDATE ... FROM cũng có cảnh báo không xác định

SQL Server hỗ trợ `UPDATE ... FROM` với cú pháp riêng:

```sql
-- SQL Server, dùng tên bảng minh họa phù hợp trong SQL Server:
UPDATE a
SET a.credit_limit = p.proposed_limit,
    a.tier = p.proposed_tier
FROM dbo.credit_accounts AS a
JOIN dbo.credit_proposals AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

Nếu một hàng `a` khớp nhiều hàng `p` và truy vấn **không quy định duy nhất** giá trị cho từng cột cập nhật, kết quả **không được bảo đảm**. Tài liệu SQL Server cũng cảnh báo `UPDATE ... FROM` là không xác định khi không đảm bảo một giá trị cập nhật duy nhất.

Không nên suy ra SQL Server luôn chọn “hàng đầu tiên” hoặc “hàng cuối cùng” trong `JOIN`.

### Cách chọn trước bằng ROW_NUMBER trong SQL Server

```sql
-- SQL Server: mẫu nguồn một hàng mỗi account
WITH ranked AS (
    SELECT
        p.account_id,
        p.proposal_id,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC, p.proposal_id DESC
        ) AS rn
    FROM dbo.credit_proposals AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
UPDATE a
SET a.credit_limit = r.proposed_limit,
    a.tier = r.proposed_tier
FROM dbo.credit_accounts AS a
JOIN ranked AS r
  ON r.account_id = a.account_id
 AND r.rn = 1;
```

Mẫu `ROW_NUMBER` là cách phổ biến để giữ một nguồn theo quy tắc thời gian và phá hòa. Tuy nhiên, cần bảo đảm `proposal_id` thực sự là khóa duy nhất và tiêu chí ưu tiên đúng nghiệp vụ.

SQL Server còn có `OUTPUT` để lấy dữ liệu thay đổi, nhưng cú pháp và khả năng sử dụng khác `RETURNING` của PostgreSQL.

## 24. MySQL: UPDATE JOIN và nguồn một-nhiều

MySQL hỗ trợ cú pháp `UPDATE ... JOIN`, ví dụ:

```sql
-- MySQL: giả định các bảng đã tồn tại trên MySQL
UPDATE credit_accounts AS a
JOIN credit_proposals AS p
  ON p.account_id = a.account_id
SET a.credit_limit = p.proposed_limit,
    a.tier = p.proposed_tier
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

Nếu một đích khớp nhiều nguồn, đừng giả định có một quy tắc ưu tiên ổn định như “sử dụng proposal_id lớn nhất”. Với cú pháp cập nhật nhiều bảng, MySQL có các quy tắc riêng về một hàng khớp nhiều lần; tuy nhiên điều đó **không tạo ra tiêu chí chọn một nguồn có ý nghĩa nghiệp vụ**.

### Chuẩn bị một nguồn rõ ràng trước

Ở phiên bản MySQL hỗ trợ hàm cửa sổ, có thể dùng:

```sql
-- MySQL 8+: xem trước nguồn đã chọn
WITH ranked AS (
    SELECT
        p.account_id,
        p.proposal_id,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC, p.proposal_id DESC
        ) AS rn
    FROM credit_proposals AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
SELECT account_id,
       proposal_id,
       proposed_limit,
       proposed_tier
FROM ranked
WHERE rn = 1;
```

Khi chuyển sang `UPDATE JOIN` thật, cần dùng cách đưa tập nguồn đã chọn vào mệnh đề `JOIN` **được phiên bản MySQL đích hỗ trợ**, chú ý quy tắc của derived table/CTE và giới hạn cập nhật khi truy vấn đọc lại chính bảng đích.

Không sao chép nguyên cú pháp `UPDATE ... FROM` của PostgreSQL sang MySQL.

## 25. Oracle: MERGE, nguồn nhiều hàng và điều kiện ổn định

Trong Oracle, cập nhật theo một nguồn nhiều hàng có thể được viết bằng `MERGE`:

```sql
-- Oracle: ví dụ cấu trúc, không chạy trên bộ dữ liệu có nguồn trùng
MERGE INTO credit_accounts a
USING credit_proposals p
ON (a.account_id = p.account_id)
WHEN MATCHED THEN
    UPDATE SET
        a.credit_limit = p.proposed_limit,
        a.tier = p.proposed_tier;
```

Nếu nguồn có nhiều hàng cố cập nhật cùng một hàng đích trong một `MERGE`, Oracle có thể từ chối vì không xác định được một tập hàng nguồn ổn định, thường được nhắc tới với lỗi `ORA-30926`. Chi tiết phụ thuộc điều kiện và hành vi của bản ghi; không nên xem đây là thuật toán chọn ngầm theo thời điểm.

### Chuẩn bị nguồn bằng ROW_NUMBER

```sql
-- Oracle: xem trước tập nguồn xác định
SELECT account_id,
       proposal_id,
       proposed_limit,
       proposed_tier
FROM (
    SELECT
        p.account_id,
        p.proposal_id,
        p.proposed_limit,
        p.proposed_tier,
        ROW_NUMBER() OVER (
            PARTITION BY p.account_id
            ORDER BY p.approved_at DESC, p.proposal_id DESC
        ) AS rn
    FROM credit_proposals p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
WHERE rn = 1;
```

Đưa tập một hàng mỗi account này thành nguồn `USING (...)` của `MERGE` theo cú pháp Oracle khi thực sự cần cập nhật.

Oracle có những hạn chế riêng về cột được phép thay đổi trong `MERGE` và cách dùng khóa trong `ON`; cần xem tài liệu theo phiên bản thay vì áp dụng suy luận từ PostgreSQL.

## 26. So sánh theo phương ngữ

| Chủ đề | PostgreSQL | SQL Server | MySQL | Oracle |
| --- | --- | --- | --- | --- |
| Cập nhật từ bảng nguồn | `UPDATE ... FROM ... WHERE ...` | `UPDATE ... FROM ... JOIN ...` | `UPDATE ... JOIN ... SET ...` | Thường dùng `MERGE`, subquery hoặc dạng `UPDATE` được hỗ trợ |
| Một đích khớp nhiều nguồn | `UPDATE ... FROM` sử dụng một hàng nguồn không bảo đảm | `UPDATE ... FROM` có cảnh báo không xác định nếu giá trị cập nhật không duy nhất | Không có quy tắc nghiệp vụ “chọn nguồn mới nhất” tự động | `MERGE` có thể báo lỗi khi một đích bị tác động nhiều lần |
| Chọn nguồn theo thứ tự | `ROW_NUMBER`, `DISTINCT ON`, `LATERAL ... LIMIT 1` | `ROW_NUMBER`, `APPLY`/`TOP (1)` | `ROW_NUMBER` và derived table/CTE phù hợp | `ROW_NUMBER`, inline view |
| Scalar subquery nhiều hàng | Lỗi cardinality | Lỗi khi dùng giá trị đơn mà nguồn trả nhiều hàng | Lỗi khi subquery giá trị đơn có nhiều hàng | Lỗi, thường gặp `ORA-01427` |
| Xóa với bảng nguồn | `DELETE ... USING` | `DELETE ... FROM ... JOIN` | `DELETE ... JOIN` hoặc cú pháp nhiều bảng | `DELETE` với `EXISTS`/subquery theo quy tắc Oracle |
| Trả dữ liệu vừa cập nhật | `RETURNING` | `OUTPUT` | Phụ thuộc sản phẩm/phiên bản và cách thực thi | Có cơ chế `RETURNING` với quy tắc riêng |
| Kiểm soát trùng nguồn | Khóa duy nhất, ranking, tổng hợp có chủ đích | Tương tự | Tương tự | Tương tự, đặc biệt quan trọng với `MERGE` |

Cú pháp khác nhau nhưng nguyên tắc giống nhau: **trước khi ghi, phải định nghĩa “một hàng đích được phép lấy giá trị từ đâu”**. Không phụ thuộc vào cách DBMS hiện tại tình cờ chọn một hàng khi phép nối còn mơ hồ.

## 27. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Hạn mức account 101 đôi khi thành 1200, đôi khi 1800 | Một đích khớp hai nguồn đã duyệt | Chọn rõ bản mới nhất theo `approved_at` và phá hòa |
| Một đích có nhiều nguồn nhưng UPDATE không báo lỗi | `UPDATE ... FROM` PostgreSQL có thể chọn một nguồn không bảo đảm | Kiểm tra cardinality trước, không suy từ việc chạy thành công |
| Dùng `ORDER BY` trong subquery nhưng kết quả vẫn mơ hồ | Subquery vẫn trả nhiều hàng trên mỗi đích | Dùng `ROW_NUMBER rn=1` hoặc `DISTINCT ON` đúng |
| `LIMIT 1` chỉ cập nhật được một account | Giới hạn toàn bộ tập, không giới hạn theo từng account | Chọn theo từng nhóm khóa |
| `ROW_NUMBER` chọn bất kỳ đề xuất 4 hoặc 5 | `approved_at` đồng hạng | Thêm khóa phá hòa duy nhất và có ý nghĩa |
| Cột hạn mức và hạng không cùng một đề xuất | `MAX` từng cột độc lập | Chọn trọn một hàng nguồn rồi lấy các thuộc tính |
| `MAX(approved_at)` nối lại vẫn có hai hàng | Hai bản cùng thời điểm duyệt | Có quy tắc phá hòa hoặc ràng buộc thời điểm duy nhất |
| `DISTINCT` không giảm về một nguồn | Nhiều nguồn có giá trị khác nhau | Khử trùng khác với lựa chọn ưu tiên |
| Cập nhật account bị từ chối mới nhất | Lấy bản mới nhất trước khi lọc `APPROVED` | Áp điều kiện hợp lệ ở đúng giai đoạn |
| Cập nhật thành NULL hoặc lỗi NOT NULL | Nguồn được chọn có giá trị thiếu | Xác định chính sách NULL, lọc nguồn hợp lệ |
| Account không có nguồn bị cập nhật thành NULL | Scalar subquery rỗng trả NULL | Dùng điều kiện tồn tại hoặc chỉ cập nhật hàng khớp |
| MERGE lỗi do một đích khớp nhiều nguồn | Nhiều source rows cố tác động cùng target | Chuẩn bị tập nguồn duy nhất trước MERGE |
| Xóa nhầm account có một đề xuất bị từ chối | Dùng `EXISTS rejected` thay vì `NOT EXISTS valid` | Viết điều kiện đúng với từ “mọi”, “không có” |
| Đếm JOIN ra 5 nhưng chỉ 3 account bị tác động | Đếm cặp nối thay vì khóa đích | `COUNT(DISTINCT target_id)` hoặc `EXISTS` |
| Cập nhật nhầm tenant | Thiếu thành phần khóa ghép trong JOIN/ranking | Dùng đủ khóa nghiệp vụ ở mọi bước |
| Chạy thử thành công nhiều lần nên tưởng an toàn | Kết quả tình cờ ổn định theo một kế hoạch | Dùng hợp đồng chọn hàng được xác định |
| CTE chọn nguồn đúng nhưng dữ liệu khác khi ghi | Có transaction khác thay đổi dữ liệu | Thiết kế isolation/locking phù hợp |
| Có một nguồn trên mỗi đích nhưng giá trị vẫn sai | Quy tắc chọn không đúng nghiệp vụ | Kiểm tra tiêu chí ưu tiên, thời điểm hiệu lực, trạng thái |

## 28. Bài tập thực hành

Hãy dùng hai bảng tạm `credit_accounts_275` và `credit_proposals_275` trong mục 2. Chỉ chạy truy vấn `SELECT` để chẩn đoán, trừ khi bài yêu cầu cập nhật **trong transaction có `ROLLBACK`**. Hãy dự đoán kết quả trước khi xem đáp án.

### Bài 1. Quan sát quan hệ nguồn–đích

Viết `SELECT JOIN` giữa hai bảng, chỉ lấy nguồn `APPROVED` với `proposed_limit IS NOT NULL`. Tính số cặp nối và số tài khoản đích phân biệt.

### Bài 2. Tìm đích có nhiều nguồn

Dùng `GROUP BY account_id HAVING COUNT(*) > 1` để liệt kê tài khoản có nhiều đề xuất hợp lệ. Tài khoản nào cần quy tắc lựa chọn?

### Bài 3. Phát hiện đồng hạng thời điểm

Tìm những tài khoản có **nhiều đề xuất hợp lệ cùng `approved_at`**. Trường hợp nào sẽ không được giải quyết nếu chỉ dùng `ORDER BY approved_at DESC`?

### Bài 4. Chọn bản mới nhất bằng ROW_NUMBER

Chỉ lấy một đề xuất hợp lệ theo mỗi account, sắp `approved_at DESC, proposal_id DESC`. Trả `account_id`, `proposal_id`, `proposed_limit` và `proposed_tier`.

### Bài 5. UPDATE có ROLLBACK

Dùng tập nguồn của bài 4 trong `UPDATE ... FROM` để cập nhật `credit_limit`, `tier`, `last_proposal_id`. Thực thi trên bảng tạm trong `BEGIN/ROLLBACK`. Có bao nhiêu account bị thay đổi?

### Bài 6. DISTINCT ON

Viết cách chọn nguồn tương đương bài 4 bằng `DISTINCT ON (account_id)` trong PostgreSQL.

### Bài 7. Phép MAX sai ngữ nghĩa

Tính `MAX(proposed_limit)` và `MAX(proposed_tier)` riêng từng account. Giải thích vì sao account 101 có thể tạo một cặp thuộc tính không có thật trên một bản đề xuất.

### Bài 8. MAX timestamp rồi nối ngược

Tìm thời điểm `MAX(approved_at)` theo account, nối lại bảng proposal để lấy dữ liệu. Có bao nhiêu hàng của account 103 nếu không có khóa phá hòa?

### Bài 9. Scalar subquery nhiều hàng

Vì sao biểu thức `(SELECT proposed_limit FROM credit_proposals_275 WHERE account_id=101 AND ...)` không phải một giá trị vô hướng hợp lệ khi có hai đề xuất? Nếu account 105 không có nguồn, biểu thức tương tự trả gì?

### Bài 10. Kiểm tra nguồn chưa có đích

Tìm đề xuất hợp lệ mà `account_id` không tồn tại trong bảng account. `UPDATE` thuần có tạo tài khoản mới từ nguồn này không?

### Bài 11. Xóa theo “không có bất kỳ đề xuất nào”

Viết `SELECT ... WHERE NOT EXISTS` để tìm tài khoản không có đề xuất, bất kể trạng thái. Dự đoán ID.

### Bài 12. Xóa theo “không có đề xuất hợp lệ”

Viết `SELECT ... WHERE NOT EXISTS` để tìm tài khoản không có nguồn `APPROVED` với `proposed_limit IS NOT NULL`. Kết quả khác bài 11 ở tài khoản nào?

### Bài 13. Nguồn mới nhất không phải bản được duyệt mới nhất

Tài khoản 102 có một đề xuất `REJECTED` mới hơn đề xuất `APPROVED`. Viết ranking đúng để chọn chỉ trong các đề xuất hợp lệ. Giải thích vì sao lọc trạng thái **sau** khi chọn toàn bộ bản mới nhất là sai mục tiêu.

### Bài 14. Preview trước khi cập nhật

Tạo CTE `chosen` và viết `SELECT` có các cột `account_id`, `before_limit`, `after_limit`, `before_tier`, `after_tier`, `from_proposal_id`. Không dùng `UPDATE`.

### Bài 15. Khóa ghép đa tenant

Giả sử bảng đích và nguồn có `tenant_id` cùng `account_id`. Viết điều kiện nối và `PARTITION BY` của `ROW_NUMBER` để tránh lấy đề xuất khác tenant.

## 29. Gợi ý lời giải

### Bài 1

```sql
SELECT
    COUNT(*) AS join_pairs,
    COUNT(DISTINCT a.account_id) AS target_accounts
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON p.account_id = a.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL;
```

Kết quả **join_pairs = 5**, **target_accounts = 3**.

### Bài 2

```sql
SELECT p.account_id,
       COUNT(*) AS candidate_rows
FROM credit_accounts_275 AS a
JOIN credit_proposals_275 AS p
  ON a.account_id = p.account_id
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
GROUP BY p.account_id
HAVING COUNT(*) > 1
ORDER BY p.account_id;
```

Kết quả **101 và 103**, mỗi tài khoản có hai nguồn.

### Bài 3

```sql
SELECT p.account_id,
       p.approved_at,
       COUNT(*) AS proposals_at_same_time
FROM credit_proposals_275 AS p
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
GROUP BY p.account_id, p.approved_at
HAVING COUNT(*) > 1
ORDER BY p.account_id, p.approved_at;
```

Kết quả **account 103**, cùng `2026-06-05 08:00:00` có hai đề xuất 4 và 5. `ORDER BY approved_at DESC` không thể phân biệt chúng.

### Bài 4

```sql
WITH ranked AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY p.account_id
               ORDER BY p.approved_at DESC,
                        p.proposal_id DESC
           ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
SELECT account_id, proposal_id,
       proposed_limit, proposed_tier
FROM ranked
WHERE rn = 1
ORDER BY account_id;
```

Các cặp `account_id → proposal_id`: **101→2, 102→3, 103→5, 106→7**.

### Bài 5

```sql
BEGIN;

WITH ranked AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY p.account_id
               ORDER BY p.approved_at DESC,
                        p.proposal_id DESC
           ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
UPDATE credit_accounts_275 AS a
SET credit_limit = r.proposed_limit,
    tier = r.proposed_tier,
    last_proposal_id = r.proposal_id
FROM ranked AS r
WHERE a.account_id = r.account_id
  AND r.rn = 1
RETURNING a.account_id, a.credit_limit,
          a.tier, a.last_proposal_id;

ROLLBACK;
```

Có **3 hàng đích** được cập nhật: 101, 102, 103. Đề xuất cho 106 không tìm được đích. Sau `ROLLBACK`, dữ liệu về trạng thái trước ví dụ.

### Bài 6

```sql
SELECT DISTINCT ON (account_id)
       account_id,
       proposal_id,
       proposed_limit,
       proposed_tier
FROM credit_proposals_275
WHERE proposal_status = 'APPROVED'
  AND proposed_limit IS NOT NULL
ORDER BY account_id,
         approved_at DESC,
         proposal_id DESC;
```

Cùng kết quả lựa chọn như bài 4, nhưng dùng cú pháp riêng PostgreSQL.

### Bài 7

```sql
SELECT account_id,
       MAX(proposed_limit) AS chosen_limit,
       MAX(proposed_tier) AS chosen_tier
FROM credit_proposals_275
WHERE proposal_status = 'APPROVED'
  AND proposed_limit IS NOT NULL
GROUP BY account_id
ORDER BY account_id;
```

Với account 101, hạn mức lớn nhất **1800** thuộc hạng GOLD, nhưng hạng lớn nhất theo thứ tự chữ có thể là **SILVER** từ đề xuất 1. Đó là cách ghép hai thuộc tính từ hai hàng khác nhau.

### Bài 8

```sql
WITH last_times AS (
    SELECT account_id,
           MAX(approved_at) AS last_time
    FROM credit_proposals_275
    WHERE proposal_status = 'APPROVED'
      AND proposed_limit IS NOT NULL
    GROUP BY account_id
)
SELECT p.account_id, p.proposal_id, p.proposed_limit
FROM credit_proposals_275 AS p
JOIN last_times AS m
  ON m.account_id = p.account_id
 AND m.last_time = p.approved_at
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
ORDER BY p.account_id, p.proposal_id;
```

Account 103 có **2 hàng**: đề xuất 4 và 5 cùng thời điểm.

### Bài 9

Scalar subquery phải trả tối đa một hàng. Với account 101, nó trả hai giá trị 1200 và 1800 nên PostgreSQL báo lỗi cardinality. Với account 105, subquery không có hàng nên trả `NULL`; cập nhật vào `credit_limit NOT NULL` có thể gây lỗi ràng buộc nếu không giới hạn hàng đích.

### Bài 10

```sql
SELECT p.account_id, p.proposal_id
FROM credit_proposals_275 AS p
WHERE p.proposal_status = 'APPROVED'
  AND p.proposed_limit IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM credit_accounts_275 AS a
      WHERE a.account_id = p.account_id
  )
ORDER BY p.account_id, p.proposal_id;
```

Kết quả là **account 106 / proposal 7**. `UPDATE` không tự tạo tài khoản mới; thao tác thêm hàng cần `INSERT` hoặc `MERGE` có nhánh tương ứng.

### Bài 11

```sql
SELECT a.account_id
FROM credit_accounts_275 AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
)
ORDER BY a.account_id;
```

Kết quả **105**.

### Bài 12

```sql
SELECT a.account_id
FROM credit_accounts_275 AS a
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_proposals_275 AS p
    WHERE p.account_id = a.account_id
      AND p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
ORDER BY a.account_id;
```

Kết quả **104 và 105**. Account 104 có đề xuất nhưng hạn mức thiếu nên không được xem là có đề xuất hợp lệ.

### Bài 13

```sql
WITH approved_ranked AS (
    SELECT p.account_id,
           p.proposal_id,
           p.proposed_limit,
           ROW_NUMBER() OVER (
               PARTITION BY p.account_id
               ORDER BY p.approved_at DESC,
                        p.proposal_id DESC
           ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
)
SELECT account_id, proposal_id, proposed_limit
FROM approved_ranked
WHERE rn = 1
ORDER BY account_id;
```

Account 102 lấy đề xuất **3** (1600), không lấy đề xuất 8 bị từ chối. Nếu xếp hạng **mọi** đề xuất rồi chỉ lọc `APPROVED` sau `rn=1`, account 102 có thể bị bỏ qua dù vẫn có một bản được duyệt hợp lệ.

### Bài 14

```sql
WITH ranked AS (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY p.account_id
               ORDER BY p.approved_at DESC,
                        p.proposal_id DESC
           ) AS rn
    FROM credit_proposals_275 AS p
    WHERE p.proposal_status = 'APPROVED'
      AND p.proposed_limit IS NOT NULL
),
chosen AS (
    SELECT *
    FROM ranked
    WHERE rn = 1
)
SELECT a.account_id,
       a.credit_limit AS before_limit,
       c.proposed_limit AS after_limit,
       a.tier AS before_tier,
       c.proposed_tier AS after_tier,
       c.proposal_id AS from_proposal_id
FROM credit_accounts_275 AS a
JOIN chosen AS c
  ON c.account_id = a.account_id
ORDER BY a.account_id;
```

Đây là một `SELECT` không ghi dữ liệu, có thể dùng để xem kế hoạch cập nhật.

### Bài 15

Điều kiện nối:

```sql
-- Khóa ghép:
-- ON c.tenant_id = a.tenant_id
-- AND c.account_id = a.account_id
```

Phân hoạch chọn nguồn:

```sql
ROW_NUMBER() OVER (
    PARTITION BY tenant_id, account_id
    ORDER BY approved_at DESC, proposal_id DESC
)
```

Phải dùng đủ cặp khóa ở cả bước ranking và bước cập nhật.

## 30. Quy trình triển khai một UPDATE/DELETE dựa trên bảng nguồn

Khi chuẩn bị thay đổi dữ liệu thật, hãy đi lần lượt:

1. **Xác định hàng đích:** khóa chính hay khóa ghép nào nhận diện chính xác đối tượng sẽ thay đổi?
2. **Xác định mức dữ liệu nguồn:** một bản ghi trên mỗi đích, nhiều phiên bản, nhiều dòng giao dịch hay nhiều sự kiện?
3. **Viết SELECT kiểm tra JOIN:** hiển thị khóa đích, khóa nguồn và mọi giá trị dự kiến dùng.
4. **Đếm số nguồn trên mỗi đích:** dùng `GROUP BY ... HAVING COUNT(*) > 1` để nhận diện chỗ có nhiều ứng viên.
5. **Lọc nguồn hợp lệ:** trạng thái, thời điểm hiệu lực, tình trạng `NULL` và quyền sử dụng dữ liệu.
6. **Quyết định tổng hợp hay chọn một bản:** nếu cần bản mới nhất, ưu tiên đầy đủ và khóa phá hòa; nếu cần tổng, định nghĩa phép tổng hợp đúng nghiệp vụ.
7. **Kiểm tra nguồn đã chọn là duy nhất:** tối đa một hàng theo **đủ khóa đích**, kể cả tenant nếu có.
8. **Xem trước giá trị trước/sau:** tạo một câu `SELECT` có cột nguồn gốc như `proposal_id`.
9. **Định nghĩa trường hợp không có nguồn:** giữ nguyên, cảnh báo hoặc chặn thao tác; không âm thầm gán `NULL`.
10. **Chạy thao tác ghi theo transaction và chính sách đồng thời phù hợp:** dùng `RETURNING`/`OUTPUT`, kiểm tra số hàng đích, audit và giới hạn tác động khi cần.
11. **Với DELETE, đọc chính xác lượng từ:** “có ít nhất một” dùng `EXISTS`; “không có bất kỳ” dùng `NOT EXISTS`; “bản mới nhất” cần chọn hàng xác định.
12. **Chỉ sau khi đúng ngữ nghĩa mới tối ưu hiệu năng:** index, kế hoạch `EXPLAIN`, kích thước bảng và mức cô lập.

### Kết luận

**Một hàng đích khớp nhiều hàng nguồn là dấu hiệu phải dừng lại và xác định quy tắc dữ liệu, không phải vấn đề có thể giải quyết bằng may rủi của thứ tự JOIN.** Trong PostgreSQL, `UPDATE ... FROM` có thể chạy thành công nhưng lấy giá trị từ một hàng nguồn không được bảo đảm. Với `MERGE` hoặc scalar subquery, tình huống tương tự có thể dẫn đến lỗi thay vì một giá trị ngầm định. Còn `DELETE ... USING` thường xóa mỗi hàng đích một lần, nhưng điều kiện nguồn một–nhiều vẫn có thể làm xóa sai đối tượng nếu diễn đạt sai yêu cầu.

Muốn cập nhật đáng tin cậy, hãy bảo đảm **tối đa một nguồn hợp lệ cho mỗi đích**, bằng ràng buộc duy nhất hoặc bằng bước lựa chọn/tổng hợp được định nghĩa rõ. Sau đó mới thực hiện `UPDATE`, `MERGE` hay `DELETE` với một hợp đồng dữ liệu có thể giải thích, kiểm tra và truy vết.
