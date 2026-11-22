# FULL OUTER JOIN và cách thay thế khi hệ quản trị không hỗ trợ

Trong **Database SQL**, thao tác `JOIN` kết hợp dữ liệu từ nhiều bảng theo điều kiện liên kết. Khi đối chiếu hai nguồn dữ liệu, đôi khi ta cần xem **tất cả bản ghi của cả hai phía**, không chỉ những bản ghi tìm được đối tác. `FULL OUTER JOIN` đáp ứng nhu cầu đó: nó giữ lại các dòng khớp nhau, các dòng **chỉ có ở bảng trái** và các dòng **chỉ có ở bảng phải**.

Một số hệ quản trị hỗ trợ trực tiếp cú pháp `FULL OUTER JOIN`; một số khác, điển hình là các phiên bản phổ biến của MySQL/MariaDB, không cung cấp cú pháp tương đương. Trong trường hợp đó, ta có thể dựng đúng ý nghĩa bằng **`LEFT JOIN` kết hợp một nhánh tìm dòng chỉ có ở bên phải và `UNION ALL`**.

Bài học giải thích ý nghĩa của phép nối đầy đủ, cách phân biệt bản ghi khớp và không khớp, ảnh hưởng của `NULL`, khóa trùng, `WHERE`/`ON`, cùng những cách thay thế đúng trong các DBMS khác nhau. Ví dụ thực hành dùng hai bảng khách hàng độc lập để minh họa đối soát dữ liệu.

## 1. FULL OUTER JOIN giải quyết bài toán gì?

Giả sử doanh nghiệp có hai nguồn khách hàng:

- **CRM** quản lý hồ sơ và phân khúc khách hàng.
- **Billing** quản lý thông tin lập hóa đơn và số dư.

Không phải mọi khách hàng trong CRM đều đã có hồ sơ Billing; ngược lại, một số hồ sơ Billing có thể chưa được đồng bộ về CRM. Nhiệm vụ của báo cáo đối soát là hiển thị **cả hai nguồn**, kể cả khách hàng chỉ hiện diện ở một bên.

Dữ liệu ví dụ:

**Bảng CRM — `sql_full_crm`**

| customer_key | crm_name | crm_segment |
| --- | --- | --- |
| C01 | An | VIP |
| C02 | Bình | STANDARD |
| C04 | Dũng | STANDARD |
| C05 | Hạnh | VIP |

**Bảng Billing — `sql_full_billing`**

| customer_key | billing_name | billing_balance |
| --- | --- | ---: |
| C01 | An | 50.00 |
| C03 | Chi | 70.00 |
| C04 | Dung | 90.00 |
| C06 | Khoa | 0.00 |

Khóa ghép trong ví dụ là `customer_key`. Từ hai bảng có thể chia kết quả thành ba nhóm:

```text
                 CRM                 Billing
           ┌──────────────────────────────────────┐
           │             ┌────────┐               │
           │  CHỈ CRM    │ CẢ HAI │   CHỈ BILLING │
           │  C02        │ C01    │   C03         │
           │  C05        │ C04    │   C06         │
           │             └────────┘               │
           └──────────────────────────────────────┘

FULL OUTER JOIN = phần chỉ CRM + phần khớp + phần chỉ Billing
```

Mỗi nguồn có **4 bản ghi**; có **2 khóa khớp** (`C01`, `C04`). `FULL OUTER JOIN` cho **6 dòng**:

| customer_key | crm_name | billing_name | Trạng thái |
| --- | --- | --- | --- |
| C01 | An | An | Cả hai |
| C02 | Bình | `NULL` | Chỉ CRM |
| C03 | `NULL` | Chi | Chỉ Billing |
| C04 | Dũng | Dung | Cả hai |
| C05 | Hạnh | `NULL` | Chỉ CRM |
| C06 | `NULL` | Khoa | Chỉ Billing |

Lưu ý ở `C04`: hai nguồn có **cùng khóa** nhưng tên khác nhau (`Dũng` và `Dung`). `FULL OUTER JOIN` vẫn xem đó là **một cặp dòng khớp** vì điều kiện nối chỉ so sánh `customer_key`. Việc kiểm tra nội dung hai cột tên có giống nhau không là **một bước đối soát bổ sung**, không phải điều kiện mặc định của FULL JOIN.

## 2. Phân biệt INNER, LEFT, RIGHT và FULL OUTER JOIN

Cùng một điều kiện `ON a.customer_key = b.customer_key`, các kiểu JOIN giữ lại những dòng khác nhau.

| Loại JOIN | Dòng khớp hai phía | Dòng chỉ ở trái | Dòng chỉ ở phải |
| --- | --- | --- | --- |
| `INNER JOIN` | Có | Không | Không |
| `LEFT [OUTER] JOIN` | Có | Có | Không |
| `RIGHT [OUTER] JOIN` | Có | Không | Có |
| `FULL [OUTER] JOIN` | Có | Có | Có |

Dấu `[OUTER]` trong bảng ký hiệu phần từ khóa **`OUTER` có thể lược bỏ** trong những dialect hỗ trợ; dấu ngoặc vuông ở đây chỉ là cách ghi chú cú pháp, không phải đoạn SQL cần gõ nguyên văn.

Với bộ dữ liệu trên:

- `INNER JOIN` cho các khóa **C01, C04**.
- `LEFT JOIN`, khi CRM đứng bên trái, cho **C01, C02, C04, C05**.
- `RIGHT JOIN`, khi CRM đứng bên trái, cho **C01, C03, C04, C06**.
- `FULL OUTER JOIN` cho **C01, C02, C03, C04, C05, C06**.

**FULL OUTER JOIN không phải CROSS JOIN.** Nó chỉ tạo các cặp dòng **thỏa điều kiện `ON`**; những dòng không tìm được đối tác vẫn xuất hiện với các cột của phía còn thiếu là `NULL`. `CROSS JOIN` lại tạo mọi tổ hợp dòng giữa hai bảng và thường cho số dòng rất lớn, không phải cơ chế đối soát đầy đủ.

### Một câu JOIN luôn có “phía trái” và “phía phải”

Trong:

```sql
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
```

bảng `c` nằm **trái**, bảng `b` nằm **phải**. Trong FULL JOIN, cả hai đều được bảo toàn. Nếu đổi vị trí hai bảng, ý nghĩa đối soát khớp/không khớp vẫn đối xứng, nhưng tên cột và cách bạn viết `CASE`/phân loại nguồn phải được điều chỉnh.

## 3. Cú pháp FULL OUTER JOIN

Dạng tổng quát trên các DBMS hỗ trợ:

```sql
SELECT
    a.column_1,
    b.column_2
FROM table_a AS a
FULL OUTER JOIN table_b AS b
  ON a.join_key = b.join_key;
```

Có thể viết `FULL JOIN` thay cho `FULL OUTER JOIN` trong các hệ hỗ trợ dạng rút gọn.

Ví dụ với hai nguồn khách hàng:

```sql
-- PostgreSQL, SQL Server, Oracle và SQLite 3.39.0+ có hỗ trợ FULL JOIN.
SELECT
    c.customer_key AS crm_key,
    b.customer_key AS billing_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY c.customer_key, b.customer_key;
```

Đối với bản ghi **chỉ CRM**, `billing_key` và các cột của `b` sẽ là `NULL`. Đối với bản ghi **chỉ Billing**, `crm_key` và các cột của `c` sẽ là `NULL`.

Khi chỉ muốn xuất **một cột khóa thống nhất**, dùng `COALESCE`:

```sql
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name,
    c.crm_segment,
    b.billing_balance
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

`COALESCE(x, y)` trả đối số đầu tiên khác `NULL`. Với khóa chính không cho phép `NULL` ở mỗi bảng như trong ví dụ, một dòng kết quả FULL JOIN luôn có ít nhất một `customer_key` có giá trị, nên `COALESCE` trả được khóa chung.

**`COALESCE` ở danh sách SELECT không thay thế điều kiện JOIN.** Việc hai dòng được ghép với nhau vẫn do `ON c.customer_key = b.customer_key` quyết định.

## 4. Ba trạng thái: BOTH, LEFT_ONLY và RIGHT_ONLY

Báo cáo đối soát thường cần phân biệt các trường hợp thay vì chỉ in cột có `NULL`. Với khóa `customer_key` được khai báo **PRIMARY KEY** ở mỗi phía, ta biết cột khóa của một dòng có thật **không bao giờ `NULL`**. Nhờ đó có thể kiểm tra bên nào không có đối tác bằng `CASE`:

```sql
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name,
    CASE
        WHEN c.customer_key IS NULL THEN 'ONLY_BILLING'
        WHEN b.customer_key IS NULL THEN 'ONLY_CRM'
        ELSE 'BOTH'
    END AS match_status
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

Kết quả dự kiến:

| customer_key | crm_name | billing_name | match_status |
| --- | --- | --- | --- |
| C01 | An | An | BOTH |
| C02 | Bình | `NULL` | ONLY_CRM |
| C03 | `NULL` | Chi | ONLY_BILLING |
| C04 | Dũng | Dung | BOTH |
| C05 | Hạnh | `NULL` | ONLY_CRM |
| C06 | `NULL` | Khoa | ONLY_BILLING |

Giải thích thứ tự nhánh:

1. `c.customer_key IS NULL`: dòng không có bản ghi CRM tương ứng, nhưng có bản ghi Billing.
2. `b.customer_key IS NULL`: dòng không có bản ghi Billing tương ứng, nhưng có bản ghi CRM.
3. Nếu cả hai khóa khác `NULL` thì đây là một cặp khớp theo `ON`.

### Vì sao nên dùng khóa không NULL để xác định bên bị thiếu?

Không nên dùng cột **có thể NULL hợp lệ** để kết luận dòng đã khớp hay chưa. Ví dụ `c.crm_segment IS NULL` có thể xảy ra ngay cả khi có hồ sơ CRM. Nếu dùng `WHEN c.crm_segment IS NULL THEN 'ONLY_BILLING'`, báo cáo sẽ **phân loại sai** những khách hàng CRM đã tồn tại nhưng chưa được gán phân khúc.

Tương tự, `b.billing_balance = 0` là **số 0 đã biết**, không có nghĩa là Billing không tồn tại. Điều kiện phát hiện phía thiếu nên dựa trên **khóa chính/cột định danh chắc chắn không `NULL`** của mỗi nguồn.

## 5. FULL JOIN không tự loại bản ghi trùng khóa

Một hiểu lầm phổ biến là mỗi khóa chỉ xuất hiện **một lần** sau FULL JOIN. Điều đó chỉ đúng nếu điều kiện nối tương ứng với một quan hệ **một-một**, ví dụ hai bên đều có `PRIMARY KEY` trên cùng khóa.

Giả sử bảng `a` có **2 dòng** với khóa `X` và bảng `b` có **3 dòng** với khóa `X`. Với điều kiện:

```sql
ON a.code = b.code
```

`FULL OUTER JOIN` tạo **2 × 3 = 6 cặp khớp**, không phải một dòng và cũng không phải năm dòng.

```text
Bảng A: X (a1), X (a2)
Bảng B: X (b1), X (b2), X (b3)

Kết quả khớp:
(a1, b1) (a1, b2) (a1, b3)
(a2, b1) (a2, b2) (a2, b3)
= 6 dòng
```

Tổng quát, với một khóa `k`:

- Nếu bên A có `m` dòng và bên B có `n` dòng, với `m>0` và `n>0`, JOIN theo phép bằng thông thường có thể tạo **`m × n` cặp** cho khóa đó.
- Nếu chỉ A có `m` dòng và B không có khóa `k`, FULL JOIN giữ **`m` dòng trái không khớp**.
- Nếu chỉ B có `n` dòng, FULL JOIN giữ **`n` dòng phải không khớp**.

### Cách hạn chế nhân dòng

Nếu yêu cầu nghiệp vụ là **mỗi mã chỉ xuất hiện một lần ở từng nguồn**, hãy:

- Khai báo `PRIMARY KEY`/`UNIQUE` đúng theo khóa nghiệp vụ khi mô hình cho phép.
- Hoặc tổng hợp/deduplicate từng bảng **trước khi JOIN**, với quy tắc lựa chọn dữ liệu được định nghĩa rõ (chẳng hạn bản ghi mới nhất theo `updated_at` và khóa phụ duy nhất).
- Hoặc chấp nhận nhiều dòng nếu bản chất của quan hệ là một-nhiều và kết quả cần giữ đầy đủ.

**Không tự thêm `DISTINCT` vào kết quả FULL JOIN chỉ để che các dòng trùng.** `DISTINCT` loại trùng **theo các cột được SELECT**, không tự biết những dòng nào là đối tượng nghiệp vụ giống nhau hay nên giữ bản ghi nào.

## 6. Thay thế khi không có FULL OUTER JOIN: LEFT JOIN + anti-join + UNION ALL

Đây là cách diễn đạt quan trọng nhất khi dùng DBMS **không hỗ trợ FULL OUTER JOIN trực tiếp**.

Ta phân chia kết quả thành hai phần **không chồng lặp**:

1. **`A LEFT JOIN B`:** chứa tất cả cặp khớp và tất cả dòng **chỉ có ở A**.
2. **`B LEFT JOIN A WHERE a.id IS NULL`:** chỉ lấy dòng **có ở B nhưng không có đối tác trong A**.

Ghép hai phần bằng `UNION ALL`:

```text
                  FULL OUTER JOIN
                         |
             +-----------+-----------+
             |                       |
       A LEFT JOIN B           B LEFT JOIN A
       (khớp + chỉ A)          WHERE A.id IS NULL
                               (chỉ B)
             |                       |
             +--------- UNION ALL ---+
```

### Câu SQL thay thế hoàn chỉnh

Ví dụ này dùng các cú pháp cơ bản có trên **MySQL/MariaDB**, đồng thời chạy được với PostgreSQL và SQLite; không yêu cầu `RIGHT JOIN`:

```sql
SELECT
    result.customer_key,
    result.crm_name,
    result.billing_name,
    result.match_status
FROM (
    -- Nhánh 1: mọi dòng CRM, kèm Billing nếu tìm được.
    SELECT
        COALESCE(c.customer_key, b.customer_key) AS customer_key,
        c.crm_name,
        b.billing_name,
        CASE
            WHEN b.customer_key IS NULL THEN 'ONLY_CRM'
            ELSE 'BOTH'
        END AS match_status
    FROM sql_full_crm AS c
    LEFT JOIN sql_full_billing AS b
      ON c.customer_key = b.customer_key

    UNION ALL

    -- Nhánh 2: chỉ lấy Billing chưa có CRM tương ứng.
    SELECT
        COALESCE(c.customer_key, b.customer_key) AS customer_key,
        c.crm_name,
        b.billing_name,
        'ONLY_BILLING' AS match_status
    FROM sql_full_billing AS b
    LEFT JOIN sql_full_crm AS c
      ON c.customer_key = b.customer_key
    WHERE c.customer_key IS NULL
) AS result
ORDER BY result.customer_key;
```

Với bảng có khóa `customer_key` không cho phép `NULL`, câu này trả **đúng sáu dòng**, giống câu `FULL OUTER JOIN` trực tiếp trong mục 4.

### Tại sao nhánh 2 phải có WHERE c.customer_key IS NULL?

Không có điều kiện này, cả hai nhánh đều trả lại các dòng **đã khớp** như C01, C04. Vì `UNION ALL` giữ nguyên mọi dòng nên các cặp khớp sẽ bị **đếm hai lần**.

Điều kiện `WHERE c.customer_key IS NULL` chỉ chọn những dòng Billing mà `LEFT JOIN` không ghép được với CRM. Vì `customer_key` là **khóa chính không NULL**, nếu một dòng CRM thật sự khớp thì `c.customer_key` chắc chắn không `NULL` và bị loại khỏi nhánh 2.

**Điểm cần giữ:** nhánh 2 phải tìm **dòng B không có bất kỳ dòng A nào thỏa toàn bộ điều kiện `ON`**, chứ không phải chỉ lấy các dòng có một thuộc tính A bất kỳ mang giá trị `NULL`.

### Vì sao dùng UNION ALL thay vì UNION?

- `UNION ALL` **giữ mọi dòng**, đúng với cách SQL JOIN thông thường bảo toàn tính trùng lặp (bag/multiset semantics).
- `UNION` (không có `ALL`) thường thực hiện **loại dòng trùng toàn bộ các cột đầu ra**, có thể làm mất các dòng hợp lệ có cùng giá trị được hiển thị.

Hai nhánh ở trên đã được thiết kế **không chồng lặp về nguồn gốc dòng**: nhánh đầu chứa khớp + chỉ A; nhánh sau chỉ B. Vì thế không cần `UNION` để khử trùng.

Một ví dụ mất dữ liệu do `UNION`:

```text
A có hai dòng nguồn khác nhau:
(id=1, code='X', name='Một tên')
(id=2, code='X', name='Một tên')

B không có code X.

Nếu SELECT chỉ lấy code, name:
Kết quả FULL JOIN cần giữ 2 dòng ('X', 'Một tên').
UNION của hai nhánh có thể gộp chúng thành 1 dòng.
UNION ALL giữ đủ 2 dòng.
```

Nếu báo cáo thực sự yêu cầu **một dòng trên mỗi khóa**, phải có **bước tổng hợp hoặc chọn bản ghi đại diện** theo quy tắc nghiệp vụ; không thay mục tiêu bằng `UNION` rồi cho rằng đã xử lý khóa trùng.

## 7. Biến thể: LEFT JOIN + RIGHT JOIN + UNION ALL

Trên DBMS có `RIGHT JOIN` nhưng **không có FULL JOIN**, có thể dùng cách viết gần với định nghĩa set hơn:

```sql
-- MySQL/MariaDB hỗ trợ LEFT JOIN và RIGHT JOIN.
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
LEFT JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key

UNION ALL

SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
RIGHT JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE c.customer_key IS NULL;
```

Nhánh `RIGHT JOIN` giữ mọi dòng Billing; `WHERE c.customer_key IS NULL` chỉ lấy phần **chưa khớp ở CRM**.

Biến thể này và cách **đảo bảng rồi dùng `LEFT JOIN`** ở mục 6 có cùng ý tưởng. Cách dùng **hai `LEFT JOIN`** thường dễ chuyển sang DBMS hơn, vì `RIGHT JOIN` cũng không được hỗ trợ ở một số phiên bản SQLite cũ.

Có thể đặt câu truy vấn sau `UNION ALL` vào một derived table rồi `ORDER BY` một lần ở ngoài, như đã làm ở mục 6, để diễn đạt thứ tự cuối cùng rõ ràng cho mọi nhánh.

## 8. Biến thể dùng NOT EXISTS cho phần chỉ có ở bên phải

Thay vì `LEFT JOIN ... WHERE a.id IS NULL`, nhánh tìm dòng chỉ ở B còn có thể diễn đạt bằng **anti-semi-join** với `NOT EXISTS`:

```sql
SELECT
    c.customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
LEFT JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key

UNION ALL

SELECT
    b.customer_key,
    NULL AS crm_name,
    b.billing_name
FROM sql_full_billing AS b
WHERE NOT EXISTS (
    SELECT 1
    FROM sql_full_crm AS c
    WHERE c.customer_key = b.customer_key
);
```

`NOT EXISTS` kiểm tra có dòng CRM nào **thỏa điều kiện khớp với dòng Billing hiện tại** hay không. Nó không phụ thuộc vào cột được chọn từ phía CRM để nhận diện một dòng JOIN giả. Khi điều kiện JOIN phức tạp hoặc không có một cột phía A chắc chắn `NOT NULL`, dạng `NOT EXISTS` có thể rõ ràng hơn.

Tuy nhiên, ở nhánh thứ hai **phải chép đúng điều kiện liên kết** từ nhánh đầu. Nếu nhánh đầu dùng cả `tenant_id` lẫn `customer_key`, nhánh `NOT EXISTS` cũng phải dùng cả hai; nếu bỏ một phần thì kết quả không còn tương đương FULL JOIN.

### Khi nào NOT EXISTS không tự sửa được ngữ nghĩa NULL?

Ở các phép nối bằng `=` thông thường:

```sql
ON a.key = b.key
```

hai giá trị `NULL` **không khớp nhau**. `NOT EXISTS` dùng cùng điều kiện `=` sẽ cho một dòng `b.key IS NULL` là **không có đối tác**, kể cả khi A cũng có dòng `a.key IS NULL`. Điều đó tương đương với FULL JOIN sử dụng `=`.

Nếu nghiệp vụ muốn hai khóa `NULL` được xem là bằng nhau, phải thay **điều kiện nối ở cả hai nhánh** bằng một quy tắc so sánh NULL-safe theo dialect phù hợp (mục 11). `NOT EXISTS` không tự suy ra quy tắc đó.

## 9. Vì sao không thể đơn giản UNION hai LEFT JOIN?

Một cách viết dễ nhầm là:

```sql
-- KHÔNG ĐÚNG để thay FULL JOIN vì chỉ bảo toàn A ở cả hai nhánh:
SELECT ...
FROM a LEFT JOIN b ON ...

UNION ALL

SELECT ...
FROM a LEFT JOIN b ON ...;
```

Hai nhánh đều xuất phát từ A, nên **không thể thu được dòng chỉ có ở B**. Muốn tạo FULL JOIN, nhánh còn lại phải **đảo vị trí bảng**, tức `B LEFT JOIN A`, rồi lọc chỉ B.

Một cách khác:

```sql
-- KHÔNG NÊN dùng như công thức thay thế tổng quát:
SELECT ... FROM a LEFT JOIN b ON ...
UNION
SELECT ... FROM b LEFT JOIN a ON ...;
```

về mặt tập các giá trị đôi khi trông giống FULL JOIN, nhưng:

1. `UNION` có thể **loại các dòng nguồn khác nhau** nếu chúng cho cùng giá trị ở các cột được SELECT.
2. Không phải cú pháp nào cũng sắp cột trả về theo cùng thứ tự; cần liệt kê cột hai nhánh tương ứng chặt chẽ.
3. `UNION` có chi phí loại trùng và có thể vô tình giấu hiện tượng nhiều dòng khớp cùng khóa.
4. Nếu thay bằng `UNION ALL` mà **không lọc nhánh thứ hai**, các cặp khớp xuất hiện hai lần.

Do đó, cách dễ chứng minh đúng là:

```text
(A LEFT JOIN B)
UNION ALL
(B LEFT JOIN A, chỉ giữ các dòng B không tìm thấy A)
```

Với cách này, phần khớp chỉ xuất hiện từ **một nhánh**, còn mỗi phía không khớp xuất hiện đúng ở nhánh được chỉ định.

## 10. Điều kiện ON và WHERE: khác nhau đặc biệt trong OUTER JOIN

`ON` xác định **những cặp dòng được xem là khớp**. `WHERE` lọc **các dòng kết quả sau khi JOIN đã tạo ra**, bao gồm cả những dòng được bổ sung bằng `NULL`.

Với `FULL OUTER JOIN`, di chuyển tùy tiện điều kiện từ `ON` sang `WHERE` có thể làm mất hẳn những dòng cần bảo toàn.

### Lọc sau JOIN có thể loại các dòng chỉ có ở một bên

```sql
-- PostgreSQL:
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_balance
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE b.billing_balance > 60;
```

Điều kiện `WHERE b.billing_balance > 60` không giữ các dòng **chỉ CRM** vì `b.billing_balance` của chúng là `NULL`, nên phép so sánh trả UNKNOWN và bị `WHERE` loại. Dòng Billing có số dư 0 hoặc 50 cũng bị lọc. Truy vấn **không còn là báo cáo toàn bộ hai nguồn**; nó là báo cáo những dòng FULL JOIN có số dư Billing lớn hơn 60.

### Đưa một điều kiện vào ON không giống lọc bảng trước JOIN

```sql
-- PostgreSQL:
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
 AND b.billing_balance > 60;
```

Với C01 có số dư Billing 50, điều kiện `ON` không cho C01 CRM ghép với C01 Billing. Do FULL JOIN **giữ cả hai phía**, nó có thể tạo **hai dòng riêng** cho C01: một dòng chỉ CRM và một dòng chỉ Billing. Đây không phải kết quả của yêu cầu “chỉ xét Billing có số dư trên 60”.

Nếu ý định là **lọc riêng nguồn Billing trước khi đối soát**, nên lọc bằng subquery/CTE:

```sql
-- PostgreSQL; đối soát toàn bộ CRM với riêng tập Billing có balance > 60.
WITH filtered_billing AS (
    SELECT customer_key, billing_name, billing_balance
    FROM sql_full_billing
    WHERE billing_balance > 60
)
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN filtered_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

Lúc này chỉ những dòng Billing được chọn từ đầu mới đi vào phép JOIN; C01 CRM trở thành chỉ CRM, còn C01 Billing có số dư 50 **không xuất hiện** trong tập đối soát đã lọc. Đây là quy tắc khác việc đưa điều kiện `balance > 60` vào `ON`.

**Nguyên tắc:** xác định rõ ba câu hỏi trước khi viết điều kiện: cần **lọc nguồn trước JOIN**, cần **thay đổi tiêu chí khớp ở `ON`**, hay cần **lọc kết quả sau JOIN**? Chúng không tương đương trong OUTER JOIN.

## 11. FULL JOIN và NULL trong khóa nối

Giả sử hai bảng có cột khóa cho phép `NULL`:

```text
A: (key = NULL, value = 'a')
B: (key = NULL, value = 'b')
```

Với điều kiện:

```sql
ON a.key = b.key
```

SQL dùng logic ba giá trị: `NULL = NULL` không trả `TRUE`. Hai dòng trên **không được xem là khớp**, nên FULL JOIN tạo **hai dòng không khớp**, một từ A và một từ B.

Đây là hành vi đúng với phép bằng thông thường, nhưng có thể gây nhầm nếu nghiệp vụ dùng `NULL` như một ký hiệu đặc biệt có nghĩa “cùng nhóm chưa xác định”.

### Nếu nghiệp vụ thật sự muốn NULL khớp NULL

Một số DBMS cung cấp toán tử so sánh **NULL-safe**. Ví dụ PostgreSQL:

```sql
-- PostgreSQL: NULL được coi không phân biệt với NULL theo toán tử này.
SELECT
    a.source_id,
    b.source_id
FROM source_a AS a
FULL OUTER JOIN source_b AS b
  ON a.external_key IS NOT DISTINCT FROM b.external_key;
```

`IS NOT DISTINCT FROM` cho `TRUE` khi hai giá trị cùng `NULL`; khi chúng khác `NULL`, nó đánh giá giống phép bằng theo ngữ nghĩa tương ứng.

Tương đương về logic trong nhiều hệ:

```sql
ON (
    a.external_key = b.external_key
    OR (a.external_key IS NULL AND b.external_key IS NULL)
)
```

Nhưng **không tự mặc định muốn khớp các giá trị thiếu**: nếu nhiều dòng bên A và B cùng có khóa `NULL`, cách so sánh NULL-safe có thể tạo **tích nhiều cặp** ngoài ý nghĩa nghiệp vụ. Khi khóa chỉ “chưa xác định”, thường đúng hơn là coi chúng là **chưa liên kết được** hoặc sử dụng một định danh khác.

### Phát hiện phía không có dòng khi khóa nối có thể NULL

Nếu cột khóa của A có thể `NULL`, điều kiện:

```sql
WHERE a.join_key IS NULL
```

**không còn đủ an toàn** để khẳng định “không có dòng A”, vì một dòng A thật cũng có thể mang `join_key = NULL`.

Hãy dùng một **cột định danh không NULL** khác, ví dụ `a.row_id` là khóa chính:

```sql
-- Mô hình minh họa:
SELECT ...
FROM b
LEFT JOIN a ON a.join_key = b.join_key
WHERE a.row_id IS NULL;
```

Câu lọc cho nhánh phải-only dựa vào **a.row_id IS NULL** chứ không dựa vào cột khóa có thể NULL. Với mọi dòng A thật, `row_id` khác `NULL`; khi không có đối tác, phần A được JOIN điền `NULL`. Như vậy điều kiện phát hiện vắng mặt rõ ràng.

Nếu không có cột định danh không NULL, có thể dùng **`NOT EXISTS` với đúng điều kiện JOIN** (mục 8) hoặc điều chỉnh mô hình/biểu thức để phân biệt dòng thật với dòng bổ sung. Đây là lý do **khóa định danh được thiết kế rõ ràng** rất hữu ích khi làm đối soát.

### Không dùng COALESCE làm phép so sánh NULL-safe một cách tùy tiện

Ví dụ:

```sql
-- DỄ GÂY KHỚP SAI nếu 'UNKNOWN' là một giá trị thật:
ON COALESCE(a.code, 'UNKNOWN') = COALESCE(b.code, 'UNKNOWN')
```

Nếu A có `code = NULL` còn B có `code = 'UNKNOWN'` thật, hai dòng sẽ bị ghép **sai**. Việc bọc hàm lên cột còn có thể ảnh hưởng cách sử dụng index. Hãy dùng toán tử NULL-safe hoặc biểu thức logic rõ ràng khi thực sự cần, thay vì chọn tùy tiện một giá trị thay thế có nguy cơ va chạm.

## 12. FULL JOIN nhiều cột: đừng chỉ ghép một phần khóa

Một số mã chỉ duy nhất trong từng tổ chức. Ví dụ:

```text
CRM:     (tenant_id, customer_key)
Billing: (tenant_id, customer_key)
```

Nếu hai tenant cùng có `customer_key = 'C01'`, điều kiện chỉ so:

```sql
-- SAI nghiệp vụ nếu customer_key chỉ duy nhất trong từng tenant.
ON c.customer_key = b.customer_key
```

có thể ghép hồ sơ của **tenant 10** với Billing của **tenant 20**.

Điều kiện đúng là ghép đủ **toàn bộ khóa nghiệp vụ**:

```sql
SELECT
    COALESCE(c.tenant_id, b.tenant_id) AS tenant_id,
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM crm_by_tenant AS c
FULL OUTER JOIN billing_by_tenant AS b
  ON c.tenant_id = b.tenant_id
 AND c.customer_key = b.customer_key;
```

Khi triển khai cách **UNION ALL + hai LEFT JOIN** thay thế, phải **giữ cùng hai điều kiện trong cả hai nhánh**, không được làm nhánh tìm B-only chỉ theo `customer_key`:

```sql
-- Mẫu điều kiện phải dùng giống nhau ở mọi nhánh.
ON c.tenant_id = b.tenant_id
AND c.customer_key = b.customer_key
```

Việc đối soát theo cặp `(tenant_id, customer_key)` chỉ nhất quán nếu cả hai nguồn tuân theo cùng quy tắc mã hóa tenant và customer key.

## 13. FULL OUTER JOIN với USING và NATURAL JOIN

Một số DBMS hỗ trợ cú pháp ngắn `USING` khi tên cột nối giống nhau:

```sql
-- PostgreSQL:
SELECT
    customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
USING (customer_key)
ORDER BY customer_key;
```

Với `USING (customer_key)`, kết quả chiếu ra **một cột customer_key chung** thay vì hai cột khóa riêng khi dùng `SELECT *`. Trong một FULL JOIN, giá trị cột khóa chung có tính chất tương tự chọn giá trị khóa còn có mặt từ một phía khi phía kia vắng mặt.

Tuy nhiên:

- `USING` chỉ thuận tiện khi **tên cột ở hai bảng giống nhau** và hệ hỗ trợ cú pháp đó.
- Nếu cần quan sát rõ `c.customer_key` và `b.customer_key` để phân loại đối soát, `ON` tường minh có thể dễ đọc và dễ kiểm tra hơn.
- Cách hiển thị cột của `SELECT *`/`USING` và thứ tự cột có khác biệt dialect, vì vậy báo cáo ổn định nên **liệt kê cột cần xuất**.
- Với điều kiện phức tạp hơn phép bằng trên các cột cùng tên, `ON` thường diễn đạt đúng hơn.

**Tránh `NATURAL FULL JOIN` trong mã ứng dụng quan trọng.** `NATURAL JOIN` tự chọn **mọi tên cột chung** giữa hai bảng làm điều kiện nối. Một cột mới được thêm vào cả hai bảng có thể vô tình thay đổi quy tắc ghép, khiến đối soát sai. Hãy viết rõ cặp khóa trong `ON` hoặc `USING`.

## 14. FULL OUTER JOIN làm báo cáo đối soát dữ liệu

Phép nối đầy đủ đặc biệt hữu ích khi cần liệt kê **thiếu dòng** và **khác nội dung** giữa hai nguồn.

### 14.1. Tìm dòng chỉ tồn tại ở một nguồn

```sql
-- PostgreSQL:
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE c.customer_key IS NULL
   OR b.customer_key IS NULL
ORDER BY customer_key;
```

Trên bộ dữ liệu mẫu, truy vấn trả **4 khóa chưa được đồng bộ cả hai phía**: C02, C03, C05, C06.

### 14.2. Tìm dòng tồn tại cả hai bên nhưng nội dung khác

Khớp theo khóa không đồng nghĩa nội dung của hai dòng bằng nhau. Trong PostgreSQL, có thể dùng `IS DISTINCT FROM` để so sánh **NULL-safe** giữa các trường nội dung:

```sql
SELECT
    c.customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE c.crm_name IS DISTINCT FROM b.billing_name
ORDER BY c.customer_key;
```

Ở ví dụ, **C04** có tên `Dũng` trong CRM nhưng `Dung` trong Billing, nên được tìm thấy. Nếu cả hai tên đều là `NULL`, `IS DISTINCT FROM` không coi chúng khác nhau; nếu một bên `NULL` còn bên kia có giá trị, nó coi là khác nhau.

Không phải mọi DBMS hỗ trợ `IS DISTINCT FROM` với cùng cú pháp/phiên bản. Cách diễn đạt logic tương đương cho hai cột văn bản trong nhiều hệ là:

```sql
WHERE c.crm_name <> b.billing_name
   OR (c.crm_name IS NULL AND b.billing_name IS NOT NULL)
   OR (c.crm_name IS NOT NULL AND b.billing_name IS NULL)
```

Tuy nhiên, kết quả so sánh tên vẫn chịu ảnh hưởng **collation**, quy tắc chữ hoa/chữ thường và dấu. Nếu yêu cầu là “khác chuỗi byte” thay vì “khác theo collation”, cần chọn cơ chế so sánh phù hợp của DBMS.

### 14.3. Đếm số dòng theo trạng thái đối soát

Trên PostgreSQL, có thể tính số từng nhóm bằng `FILTER`:

```sql
WITH compared AS (
    SELECT
        c.customer_key AS crm_key,
        b.customer_key AS billing_key
    FROM sql_full_crm AS c
    FULL OUTER JOIN sql_full_billing AS b
      ON c.customer_key = b.customer_key
)
SELECT
    COUNT(*) AS all_join_rows,
    COUNT(*) FILTER (
        WHERE crm_key IS NOT NULL AND billing_key IS NOT NULL
    ) AS matched_rows,
    COUNT(*) FILTER (
        WHERE crm_key IS NOT NULL AND billing_key IS NULL
    ) AS crm_only_rows,
    COUNT(*) FILTER (
        WHERE crm_key IS NULL AND billing_key IS NOT NULL
    ) AS billing_only_rows
FROM compared;
```

Kết quả ví dụ: **6 dòng kết quả**, trong đó **2 khớp**, **2 chỉ CRM**, **2 chỉ Billing**.

Cú pháp `FILTER (WHERE ...)` không có ở mọi DBMS. Cách viết bằng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` là một lựa chọn phổ biến; nếu tập kết quả có thể rỗng, hãy cân nhắc `COALESCE(SUM(...), 0)` vì `SUM` trên tập rỗng thường trả `NULL`, còn `COUNT(*)` trả 0.

**Cảnh báo về cách đọc kết quả:** nếu mỗi nguồn có khóa trùng, những con số trên là **số dòng sau JOIN**, không nhất thiết là số khóa nghiệp vụ riêng biệt. Muốn đếm khóa duy nhất cần xác định quy tắc deduplicate hoặc `COUNT(DISTINCT ...)` phù hợp.

## 15. Hỗ trợ FULL OUTER JOIN theo hệ quản trị

Cú pháp và phiên bản có thể khác nhau:

| Hệ quản trị | Hỗ trợ FULL OUTER JOIN trực tiếp | Cách tiếp cận |
| --- | --- | --- |
| **PostgreSQL** | Có | Dùng `FULL [OUTER] JOIN ... ON ...`; có thể xem `EXPLAIN` |
| **SQL Server** | Có | Dùng `FULL [OUTER] JOIN` trong T-SQL |
| **Oracle Database** | Có | Dùng `FULL OUTER JOIN`; chú ý kiểu dữ liệu và điều kiện so sánh |
| **SQLite 3.39.0 trở lên** | Có | Hỗ trợ `RIGHT JOIN` và `FULL OUTER JOIN`; kiểm tra phiên bản của SQLite thực tế |
| **SQLite trước 3.39.0** | Không | Dùng `LEFT JOIN + UNION ALL + LEFT anti-join` |
| **MySQL** | Không có `FULL OUTER JOIN` trực tiếp trong các phiên bản phổ biến | Dùng hai nhánh `LEFT JOIN` kết hợp `UNION ALL` hoặc biến thể dùng `RIGHT JOIN` |
| **MariaDB** | Không có `FULL OUTER JOIN` trực tiếp trong các phiên bản phổ biến | Dùng cách ghép hai phía như MySQL; kiểm tra tính năng theo phiên bản đang chạy |

### PostgreSQL

```sql
SELECT
    COALESCE(a.id, b.id) AS id,
    a.left_value,
    b.right_value
FROM source_a AS a
FULL OUTER JOIN source_b AS b
  ON a.id = b.id;
```

Nếu cần kiểm tra hiệu năng, PostgreSQL có công cụ `EXPLAIN` cho phép xem cách thực thi phép JOIN. Với dữ liệu nhỏ, bộ tối ưu có thể chọn một kế hoạch rất khác so với bảng lớn.

### SQL Server

```sql
-- SQL Server:
SELECT
    COALESCE(a.id, b.id) AS id,
    a.left_value,
    b.right_value
FROM dbo.source_a AS a
FULL OUTER JOIN dbo.source_b AS b
  ON a.id = b.id;
```

SQL Server hỗ trợ `FULL OUTER JOIN`, nhưng điều kiện so sánh chuỗi chịu ảnh hưởng collation; nếu ID dạng chuỗi giữa hai hệ có khác kiểu, padding hoặc quy tắc chữ hoa, kết quả khớp có thể khác kỳ vọng.

### Oracle Database

```sql
-- Oracle:
SELECT
    COALESCE(a.id, b.id) AS id,
    a.left_value,
    b.right_value
FROM source_a a
FULL OUTER JOIN source_b b
  ON a.id = b.id;
```

Oracle coi chuỗi rỗng là `NULL` trong nhiều ngữ cảnh chuỗi ký tự. Vì vậy nếu khóa liên kết có thể là `''`, quy tắc khớp/không khớp có thể khác PostgreSQL hoặc MySQL. Với khóa nghiệp vụ, nên có dữ liệu chuẩn hóa và ràng buộc thích hợp.

### SQLite

Kiểm tra phiên bản:

```sql
SELECT sqlite_version();
```

Trên **SQLite 3.39.0+**, có thể dùng `FULL OUTER JOIN`. Với bản SQLite cũ hoặc ứng dụng nhúng sử dụng thư viện SQLite khác bản đang cài trên máy, cần dùng cách thay thế bằng `LEFT JOIN`/`UNION ALL`.

### MySQL và MariaDB

Kiểm tra phiên bản:

```sql
SELECT VERSION();
```

Trong các bản MySQL/MariaDB phổ biến không hỗ trợ FULL JOIN trực tiếp, câu:

```sql
-- Không phải cú pháp được các phiên bản phổ biến MySQL/MariaDB hỗ trợ:
-- SELECT * FROM a FULL OUTER JOIN b ON a.id = b.id;
```

không thay bằng `INNER JOIN` hoặc `LEFT JOIN` nếu yêu cầu vẫn là giữ mọi dòng của **cả hai phía**. Hãy dùng phương án `UNION ALL` với nhánh anti-join ở mục 6. Nếu truy vấn có `ORDER BY`, `LIMIT` hoặc aggregate, đặt phép `UNION ALL` vào derived table/CTE và áp dụng bước sau **trên toàn bộ kết quả**, không chỉ một nhánh.

## 16. Hiệu năng: index, số lần quét và kích thước kết quả

Một FULL OUTER JOIN có thể phải xử lý lượng dữ liệu lớn vì nó bảo toàn những dòng không khớp ở cả hai phía. Hiệu năng phụ thuộc:

- Kích thước từng bảng và số lượng dòng khớp.
- Mức độ trùng của khóa JOIN (một khóa trùng nhiều lần có thể sinh **tích số dòng**).
- Kiểu dữ liệu, collation và khả năng dùng index trên cột khóa.
- Bộ lọc `WHERE`/subquery được áp dụng trước hay sau JOIN.
- Chiến lược thực thi của DBMS: hash join, merge join hoặc phương án khác nếu engine hỗ trợ.
- Số cột và độ rộng dữ liệu phải trả về, cùng yêu cầu `ORDER BY` cuối cùng.

### Tạo index phù hợp

Nếu hai bảng được nối bằng `customer_key` và các cột này đều là **PRIMARY KEY**, DBMS thường đã tạo hoặc quản lý cấu trúc hỗ trợ tìm kiếm theo khóa. Không cần thêm một index trùng y hệt chỉ để “tăng tốc FULL JOIN” mà chưa kiểm tra metadata.

Với bảng nguồn không có index:

```sql
-- PostgreSQL, ví dụ chung; chọn theo dữ liệu và workload thực tế:
CREATE INDEX ix_source_a_customer_key ON source_a(customer_key);
CREATE INDEX ix_source_b_customer_key ON source_b(customer_key);
```

Trong bài tập thực hành cụ thể, hai bảng có PK trên `customer_key` nên đã có index hỗ trợ khóa. Trên bảng rất nhỏ, planner có thể chọn quét tuần tự dù index tồn tại; điều đó bình thường.

### Hai nhánh UNION ALL có thể đọc bảng nhiều lần

Cách thay thế:

```text
A LEFT JOIN B
UNION ALL
B LEFT JOIN A WHERE A.id IS NULL
```

có thể phải đọc hoặc truy cập **cả hai bảng ở hai nhánh**. Nó không được bảo đảm có cùng execution plan/chi phí với một phép FULL JOIN native. Một số bộ tối ưu có thể tối ưu hóa tốt; một số tình huống có thể phát sinh chi phí lớn do hai phép nối và bước sắp xếp cuối.

Với tập dữ liệu lớn, dùng công cụ kế hoạch truy vấn đúng dialect: `EXPLAIN` trên PostgreSQL/MySQL/SQLite, execution plan của SQL Server hoặc Oracle. So sánh các phương án **trên dữ liệu thực tế**, không chỉ đo một bảng mười dòng.

### Tránh vô tình làm lớn tập JOIN bằng điều kiện thiếu

Nếu khóa thật là `(tenant_id, customer_key)` nhưng truy vấn chỉ nối theo `customer_key`, các bản ghi nhiều tenant có thể **nhân dòng sai**, khiến cả kết quả lẫn hiệu năng bị ảnh hưởng. Thiết kế khóa và `ON` đúng nghiệp vụ quan trọng hơn việc chỉnh chỉ mục sau khi đã JOIN sai.

### Không làm biến đổi khóa tùy tiện trong ON

Ví dụ:

```sql
ON LOWER(a.customer_key) = LOWER(b.customer_key)
```

có thể phù hợp nếu nghiệp vụ muốn so không phân biệt hoa thường, nhưng việc áp hàm lên cột có thể ảnh hưởng index thông thường và biến hai khóa vốn khác nhau thành một. Nếu cần chuẩn hóa mã, nên có quy tắc ở tầng dữ liệu hoặc index/column hỗ trợ, không mặc nhiên đặt `LOWER` trong mọi FULL JOIN.

## 17. Snapshot và tính nhất quán của báo cáo đối soát

Nếu CRM và Billing được cập nhật liên tục, kết quả đối soát thể hiện **trạng thái mà truy vấn nhìn thấy tại thời điểm chạy**, không nhất thiết là một “sự thật bất biến” của cả hai hệ.

Đặc biệt khi mô phỏng FULL JOIN bằng hai nhánh:

- Nên gộp chúng trong **một câu SQL `UNION ALL`**, thay vì chạy hai truy vấn ở hai thời điểm rồi ghép kết quả ở ứng dụng.
- Khi chạy hai câu `SELECT` độc lập và có INSERT/DELETE giữa chúng, tập dữ liệu hai nhánh có thể không còn tương ứng với cùng một thời điểm.
- Một câu truy vấn duy nhất trên DBMS dùng statement-level snapshot thích hợp giúp hai nhánh quan sát nhất quán hơn; chi tiết phụ thuộc engine và mức cô lập.
- Nếu đối soát giữa **hai cơ sở dữ liệu/hệ thống độc lập**, một `FULL JOIN` cũng không tự tạo được snapshot giao dịch phân tán nhất quán. Cần quy ước về thời điểm chốt, batch ID, dữ liệu staging hoặc đồng bộ dữ liệu.

Ví dụ, nếu dữ liệu Billing được nhập vào bảng staging lúc 08:00 còn CRM là bản chụp 09:00, những dòng “chỉ CRM” có thể đơn giản là **chưa kịp có trong ảnh Billing**, không nhất thiết là lỗi dữ liệu.

Khi báo cáo đối soát có giá trị kiểm toán, hãy ghi **thời điểm trích xuất nguồn**, điều kiện lọc, phiên bản dữ liệu, khóa ghép và tổng số dòng từng trạng thái. Không đồng nhất “FULL JOIN trả đúng SQL” với “hai nguồn đã được đối chiếu tại cùng một thời điểm nghiệp vụ”.

## 18. Thực hành trên PostgreSQL: từ dữ liệu đến báo cáo hoàn chỉnh

Các câu lệnh sau dành cho **PostgreSQL trong database thực hành**. Sử dụng tên `sql_full_...` để tránh trùng với bảng nghiệp vụ. Nếu bảng cùng tên đã tồn tại, không chạy `CREATE TABLE` đè; hãy chọn schema/bảng thực hành khác.

### 18.1. Tạo hai bảng độc lập

```sql
CREATE TABLE sql_full_crm (
    customer_key VARCHAR(12) PRIMARY KEY,
    crm_name     VARCHAR(100) NOT NULL,
    crm_segment  VARCHAR(30)
);

CREATE TABLE sql_full_billing (
    customer_key    VARCHAR(12) PRIMARY KEY,
    billing_name    VARCHAR(100) NOT NULL,
    billing_balance NUMERIC(12, 2) NOT NULL
);
```

Hai bảng **không khai báo FOREIGN KEY** qua lại, vì mục tiêu là mô phỏng hai nguồn có thể có khách hàng **không tồn tại ở nguồn kia**. Nếu bảng Billing bắt buộc tham chiếu đến CRM bằng FK không cho phép thiếu, ta không thể chèn một dòng chỉ Billing như C03 vào cùng một database có ràng buộc đó.

### 18.2. Chèn bộ dữ liệu thử

```sql
INSERT INTO sql_full_crm (customer_key, crm_name, crm_segment)
VALUES
    ('C01', 'An',   'VIP'),
    ('C02', 'Bình', 'STANDARD'),
    ('C04', 'Dũng', 'STANDARD'),
    ('C05', 'Hạnh', 'VIP');

INSERT INTO sql_full_billing
    (customer_key, billing_name, billing_balance)
VALUES
    ('C01', 'An',   50.00),
    ('C03', 'Chi',  70.00),
    ('C04', 'Dung', 90.00),
    ('C06', 'Khoa',  0.00);
```

Đếm từng nguồn:

```sql
SELECT COUNT(*) AS crm_count FROM sql_full_crm;
SELECT COUNT(*) AS billing_count FROM sql_full_billing;
```

Mỗi bảng có **4 dòng**.

### 18.3. INNER, LEFT và FULL: so sánh số lượng

```sql
-- Chỉ các khóa khớp: C01, C04.
SELECT
    c.customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
INNER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY c.customer_key;

-- Giữ toàn bộ CRM: C01, C02, C04, C05.
SELECT
    c.customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
LEFT JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY c.customer_key;

-- Giữ toàn bộ hai nguồn: C01 đến C06.
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

Kết quả số dòng lần lượt là **2**, **4** và **6**.

### 18.4. Thêm trạng thái đối soát

```sql
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    c.crm_name,
    b.billing_name,
    CASE
        WHEN c.customer_key IS NULL THEN 'ONLY_BILLING'
        WHEN b.customer_key IS NULL THEN 'ONLY_CRM'
        ELSE 'BOTH'
    END AS match_status
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

Chú ý: C04 là **BOTH** dù tên khác nhau, vì điều kiện `ON` chỉ so sánh khóa. Đây là bằng chứng quan trọng rằng **trạng thái có đối tác** khác với **trạng thái nội dung giống nhau**.

### 18.5. Chạy cách thay thế bằng UNION ALL

Trên chính hai bảng mẫu PostgreSQL, chạy câu SQL thay thế ở mục 6:

```sql
SELECT
    result.customer_key,
    result.crm_name,
    result.billing_name,
    result.match_status
FROM (
    SELECT
        c.customer_key AS customer_key,
        c.crm_name,
        b.billing_name,
        CASE WHEN b.customer_key IS NULL
             THEN 'ONLY_CRM' ELSE 'BOTH' END AS match_status
    FROM sql_full_crm AS c
    LEFT JOIN sql_full_billing AS b
      ON c.customer_key = b.customer_key

    UNION ALL

    SELECT
        b.customer_key AS customer_key,
        c.crm_name,
        b.billing_name,
        'ONLY_BILLING' AS match_status
    FROM sql_full_billing AS b
    LEFT JOIN sql_full_crm AS c
      ON c.customer_key = b.customer_key
    WHERE c.customer_key IS NULL
) AS result
ORDER BY result.customer_key;
```

Với khóa không NULL và duy nhất trong từng bảng, kết quả phải có cùng **sáu khóa và ba nhóm trạng thái** như FULL OUTER JOIN native. Câu này không đòi hỏi `FULL JOIN`, vì vậy có thể áp dụng ý tưởng tương tự trên MySQL/MariaDB hoặc SQLite cũ (với cấu trúc bảng phù hợp dialect).

### 18.6. Đối chiếu sự khác biệt về tên

```sql
-- PostgreSQL:
SELECT
    c.customer_key,
    c.crm_name,
    b.billing_name
FROM sql_full_crm AS c
INNER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE c.crm_name IS DISTINCT FROM b.billing_name
ORDER BY c.customer_key;
```

Kết quả kỳ vọng: **C04**, vì `'Dũng'` và `'Dung'` khác nhau. Nếu collation đang dùng có quy tắc không phân biệt dấu khiến hai giá trị được coi tương đương, cần xác định yêu cầu so sánh để chọn collation/toán tử phù hợp.

### 18.7. Đếm theo loại và phát hiện chỉ một nguồn

```sql
WITH compared AS (
    SELECT
        COALESCE(c.customer_key, b.customer_key) AS customer_key,
        CASE
            WHEN c.customer_key IS NULL THEN 'ONLY_BILLING'
            WHEN b.customer_key IS NULL THEN 'ONLY_CRM'
            ELSE 'BOTH'
        END AS match_status
    FROM sql_full_crm AS c
    FULL OUTER JOIN sql_full_billing AS b
      ON c.customer_key = b.customer_key
)
SELECT match_status, COUNT(*) AS row_count
FROM compared
GROUP BY match_status
ORDER BY match_status;
```

Mỗi nhóm có **2 dòng**. Nếu muốn chỉ liệt kê những khóa chưa được đồng bộ:

```sql
SELECT
    COALESCE(c.customer_key, b.customer_key) AS customer_key,
    CASE
        WHEN c.customer_key IS NULL THEN 'ONLY_BILLING'
        ELSE 'ONLY_CRM'
    END AS missing_side
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE c.customer_key IS NULL
   OR b.customer_key IS NULL
ORDER BY customer_key;
```

Kết quả gồm C02, C03, C05, C06.

### 18.8. Kiểm tra ảnh hưởng của bộ lọc

Chạy riêng ba truy vấn:

```sql
-- (A) Lọc SAU JOIN: chỉ giữ kết quả có balance > 60.
SELECT COALESCE(c.customer_key, b.customer_key) AS customer_key
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
WHERE b.billing_balance > 60
ORDER BY customer_key;

-- (B) Thêm điều kiện vào ON: khác về số dòng, vì vẫn giữ B và C.
SELECT
    c.customer_key AS crm_key,
    b.customer_key AS billing_key
FROM sql_full_crm AS c
FULL OUTER JOIN sql_full_billing AS b
  ON c.customer_key = b.customer_key
 AND b.billing_balance > 60
ORDER BY crm_key, billing_key;

-- (C) Lọc bảng Billing trước JOIN:
WITH b_filtered AS (
    SELECT *
    FROM sql_full_billing
    WHERE billing_balance > 60
)
SELECT COALESCE(c.customer_key, b.customer_key) AS customer_key
FROM sql_full_crm AS c
FULL OUTER JOIN b_filtered AS b
  ON c.customer_key = b.customer_key
ORDER BY customer_key;
```

Ở truy vấn A, các khóa kết quả là **C03, C04**. Ở truy vấn B, khóa C01 xuất hiện **hai dòng tách biệt** (một CRM và một Billing), vì điều kiện số dư khiến cặp C01 không khớp; đồng thời các dòng chỉ ở một bên vẫn được giữ. Ở truy vấn C, Billing chỉ đưa C03 và C04 vào JOIN; các khóa kết quả là **C01, C02, C03, C04, C05**. Ba truy vấn có ý nghĩa khác nhau dù cùng xuất hiện `billing_balance > 60`.

### 18.9. Dọn bảng học tập

Chỉ chạy khi hai bảng này do chính bạn tạo cho bài học:

```sql
DROP TABLE sql_full_billing;
DROP TABLE sql_full_crm;
```

Không sử dụng `DROP TABLE` trên cơ sở dữ liệu thật hoặc bảng đang được dùng chung.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| MySQL báo lỗi cú pháp tại `FULL OUTER JOIN` | Engine/phiên bản không hỗ trợ trực tiếp | Dùng hai `LEFT JOIN` + nhánh anti-join + `UNION ALL` |
| Chỉ thấy dòng có ở cả hai nguồn | Đã dùng `INNER JOIN` hoặc `WHERE` vô tình loại dòng ngoài | Dùng FULL JOIN hoặc cách thay thế đúng; kiểm tra WHERE |
| Chỉ có dòng CRM và dòng khớp | Đã dùng `LEFT JOIN` một nhánh | Bổ sung nhánh B-only hoặc dùng FULL |
| Kết quả `UNION ALL` lặp các dòng đã khớp | Nhánh thứ hai chưa lọc dòng chỉ B | Thêm `WHERE a.id IS NULL` trên cột định danh A không NULL |
| `UNION` cho thiếu số dòng | `UNION` loại các kết quả trùng toàn bộ cột SELECT | Dùng `UNION ALL` với hai nhánh không chồng lặp |
| Một mã khách hàng xuất hiện 6 lần | Khóa JOIN lặp hai phía, tạo tích cặp | Xem lại khóa nghiệp vụ, UNIQUE, deduplicate nguồn nếu cần |
| Mã có ở A và B nhưng không khớp | Khác kiểu, khoảng trắng, collation hoặc điều kiện ON không đúng | Đối chiếu dữ liệu khóa và quy tắc so sánh |
| Báo cáo chia nhầm BOTH/ONLY | Dùng cột dữ liệu cho phép NULL để xác định bên vắng | Dùng PK/ID chắc chắn NOT NULL của mỗi phía |
| Dòng có khóa NULL được xem là không khớp | `NULL = NULL` không trả TRUE | Xác định nghiệp vụ; dùng so sánh NULL-safe khi thật sự cần |
| Truy vấn nhiều tenant ghép nhầm khách | `ON` chỉ dùng customer_key, thiếu tenant_id | Ghép đủ khóa nhiều cột ở tất cả nhánh |
| Đưa điều kiện lọc vào ON tạo thêm dòng only | Trong FULL JOIN, điều kiện ON quyết định khớp, không loại dòng nguồn | Dùng CTE/subquery lọc nguồn nếu đúng mục tiêu |
| Báo cáo chỉ CRM/Billing khác thời điểm thực tế | Nguồn cập nhật lệch snapshot hoặc lịch đồng bộ | Ghi thời điểm trích xuất và quy ước đối soát |
| Đếm `COUNT(*)` lớn hơn số khách hàng | Nhiều cặp khớp do khóa trùng | Đếm theo đúng đơn vị nghiệp vụ, xử lý khóa trùng |
| FULL JOIN trên bảng lớn chạy chậm | Thiếu index, điều kiện JOIN phức tạp, nhân dòng, sort lớn | Xem execution plan, chỉ mục, bộ lọc và số dòng khớp |

## 20. Bài tập tự luyện

### Bài 1 — Dự đoán tập kết quả

Bảng A có khóa `1, 2, 4`; bảng B có khóa `2, 3, 4, 5`, mỗi khóa duy nhất và không `NULL`. Hãy liệt kê khóa của kết quả:

1. `INNER JOIN`.
2. `A LEFT JOIN B`.
3. `A RIGHT JOIN B`.
4. `A FULL OUTER JOIN B`.

Với FULL JOIN, xác định nhóm BOTH, ONLY_A và ONLY_B.

### Bài 2 — Viết FULL JOIN đối soát

Hai bảng `inventory_expected(sku, expected_qty)` và `inventory_actual(sku, actual_qty)` có khóa `sku` duy nhất, không `NULL`. Viết SQL trả `sku` chung, số lượng dự kiến, số lượng thực tế và nhãn `BOTH`/`ONLY_EXPECTED`/`ONLY_ACTUAL`.

### Bài 3 — Chuyển sang MySQL

Từ yêu cầu bài 2, viết một câu thay thế **không dùng `FULL OUTER JOIN`**, sử dụng `LEFT JOIN`, `UNION ALL` và lọc dòng chỉ có ở bảng thực tế. Giải thích vì sao nhánh thứ hai cần điều kiện anti-join.

### Bài 4 — Phát hiện UNION sai

Bảng A có hai dòng khác ID nhưng cùng `sku='X'`, `name='Áo'`; bảng B không có `X`. Nếu truy vấn chỉ SELECT `sku` và `name`, vì sao dùng `UNION` giữa hai nhánh có thể giảm hai dòng xuống một? Công thức thay FULL JOIN cần dùng từ khóa nào để giữ nguyên số dòng?

### Bài 5 — NULL và phát hiện dòng không khớp

Cột `external_key` của hai bảng có thể `NULL`, nhưng mỗi bảng có `row_id` là PK không `NULL`. Nếu dùng `ON a.external_key = b.external_key`, hai dòng có `external_key = NULL` có khớp nhau không? Vì sao khi lọc B-only nên dùng `WHERE a.row_id IS NULL` thay vì `WHERE a.external_key IS NULL`?

### Bài 6 — Điều kiện ON và lọc nguồn

Một bảng A có khóa 1; bảng B cũng có khóa 1 nhưng `b.active = FALSE`. So sánh:

```sql
A FULL JOIN B ON A.id = B.id AND B.active = TRUE
```

với một FULL JOIN giữa A và `(SELECT * FROM B WHERE active = TRUE)`. Truy vấn nào có thể tạo **hai dòng riêng** liên quan khóa 1? Vì sao?

### Bài 7 — Khóa nhiều cột

Hai bảng theo nhiều tenant có khóa nghiệp vụ `(tenant_id, sku)`. Viết điều kiện `ON` đúng và chỉ ra vì sao chỉ dùng `ON a.sku=b.sku` có thể ghép dòng giữa các tenant khác nhau.

### Bài 8 — Đếm trạng thái đối soát

Trên dữ liệu CRM/Billing của phần thực hành:

1. Có bao nhiêu dòng BOTH?
2. Có bao nhiêu dòng ONLY_CRM?
3. Có bao nhiêu dòng ONLY_BILLING?
4. Có bao nhiêu dòng chỉ xuất hiện một trong hai nguồn?
5. Khóa nào có mặt hai bên nhưng tên khác?

Viết SQL hoặc giải thích cách lấy từng kết quả.

### Bài 9 — Chọn cách triển khai theo DBMS

Một ứng dụng đang dùng SQLite 3.38, một ứng dụng khác dùng SQLite 3.40, còn báo cáo nội bộ chạy trên PostgreSQL. Những môi trường nào có thể dùng FULL JOIN trực tiếp? Môi trường nào cần dạng thay thế? Vì sao phải kiểm tra phiên bản SQLite **trong ứng dụng** thay vì chỉ xem phiên bản lệnh sqlite3 trên một máy khác?

### Bài 10 — Đối soát có độ tin cậy cao

Một batch đối soát chạy lúc 09:00; dữ liệu CRM được chốt 09:00 nhưng Billing chỉ đồng bộ đến 08:30. Nếu xuất hiện 200 dòng ONLY_CRM, có thể kết luận 200 lỗi dữ liệu hay chưa? Cần lưu những metadata nào để giải thích báo cáo?

### Gợi ý đáp án

**Bài 1:** INNER: `2,4`; LEFT: `1,2,4`; RIGHT: `2,3,4,5`; FULL: `1,2,3,4,5`. BOTH: `2,4`; ONLY_A: `1`; ONLY_B: `3,5`.

**Bài 2:**

```sql
SELECT
    COALESCE(e.sku, a.sku) AS sku,
    e.expected_qty,
    a.actual_qty,
    CASE
        WHEN e.sku IS NULL THEN 'ONLY_ACTUAL'
        WHEN a.sku IS NULL THEN 'ONLY_EXPECTED'
        ELSE 'BOTH'
    END AS match_status
FROM inventory_expected AS e
FULL OUTER JOIN inventory_actual AS a
  ON e.sku = a.sku;
```

**Bài 3:**

```sql
SELECT
    e.sku AS sku,
    e.expected_qty,
    a.actual_qty,
    CASE WHEN a.sku IS NULL
         THEN 'ONLY_EXPECTED' ELSE 'BOTH' END AS match_status
FROM inventory_expected AS e
LEFT JOIN inventory_actual AS a ON e.sku = a.sku

UNION ALL

SELECT
    a.sku AS sku,
    e.expected_qty,
    a.actual_qty,
    'ONLY_ACTUAL' AS match_status
FROM inventory_actual AS a
LEFT JOIN inventory_expected AS e ON e.sku = a.sku
WHERE e.sku IS NULL;
```

Nhánh 2 chỉ lấy `a` không có `e` tương ứng; nếu không lọc, mọi cặp đã khớp có thể xuất hiện thêm lần nữa. Giả định `sku` của `e` được khai báo không `NULL`.

**Bài 4:** `UNION` khử trùng theo cột đầu ra, nên hai dòng khác ID nhưng có cùng `sku`/`name` có thể bị gộp. Dùng `UNION ALL` và thiết kế nhánh B-only không trùng để giữ nguyên tính đa tập.

**Bài 5:** Hai khóa `NULL` không khớp bằng `=`. `a.external_key IS NULL` có thể đúng với một dòng A thật; `a.row_id IS NULL` chỉ xảy ra khi **không có dòng A** trong kết quả của LEFT JOIN, nếu `row_id` là PK không `NULL`.

**Bài 6:** Dùng `FULL JOIN ... ON A.id=B.id AND B.active=TRUE` có thể tạo hai dòng riêng khi B không active: A không khớp và B không khớp nhưng cả hai vẫn được bảo toàn. Lọc B trong subquery trước JOIN loại dòng B inactive khỏi tập đầu vào, chỉ còn A không có đối tác.

**Bài 7:** `ON a.tenant_id = b.tenant_id AND a.sku = b.sku`. Nếu chỉ so `sku`, dữ liệu cùng SKU thuộc tenant khác nhau có thể bị ghép sai hoặc sinh tích nhiều dòng.

**Bài 8:** BOTH = **2** (C01, C04); ONLY_CRM = **2** (C02, C05); ONLY_BILLING = **2** (C03, C06); chỉ một nguồn = **4**; khớp khóa nhưng khác tên = **C04**.

**Bài 9:** PostgreSQL và SQLite **3.40** dùng FULL JOIN trực tiếp; SQLite **3.38** cần cách thay thế bằng hai LEFT JOIN và UNION ALL. Ứng dụng có thể nhúng thư viện SQLite với phiên bản riêng, khác bản sqlite3 được cài trên hệ điều hành.

**Bài 10:** Chưa thể kết luận cả 200 dòng đều sai vì hai nguồn có **mốc dữ liệu khác nhau**. Cần ghi thời điểm chốt từng nguồn, batch/job ID, phạm vi lọc, khóa ghép, số bản ghi đầu vào, số dòng đối soát theo từng nhóm và phiên bản/định nghĩa truy vấn.

## 21. Kết luận

`FULL OUTER JOIN` giữ **ba nhóm**: khớp hai phía, chỉ trái và chỉ phải. Nó rất phù hợp để đối soát hệ thống, phát hiện dữ liệu chưa đồng bộ và so sánh hai nguồn độc lập. Khi DBMS không hỗ trợ trực tiếp, công thức thay thế đáng tin cậy là **`A LEFT JOIN B` kết hợp `B LEFT JOIN A` chỉ lấy dòng chưa có A, nối bằng `UNION ALL`**.

Để dùng đúng trong thực tế, cần nhớ thêm bốn điểm: **ghép theo đủ khóa**, **phân biệt `ON` với `WHERE`**, **dùng cột định danh không `NULL` để phát hiện phía vắng mặt**, và **không dùng `UNION`/`DISTINCT` để che sự trùng lặp của dữ liệu nguồn**. Một truy vấn FULL JOIN đúng cú pháp chỉ là bước đầu; chất lượng báo cáo còn phụ thuộc định nghĩa khóa, thời điểm chốt dữ liệu và tiêu chí so sánh nội dung giữa hai nguồn.
