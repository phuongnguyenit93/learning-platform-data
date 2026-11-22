# Độ ưu tiên toán tử, dấu ngoặc và biểu thức lồng nhau

Trong SQL, một điều kiện không chỉ phụ thuộc vào **toán tử nào xuất hiện** mà còn phụ thuộc vào **các toán tử được kết hợp thành biểu thức như thế nào**. Hai câu lệnh gần như giống nhau có thể trả về những tập bản ghi khác nhau chỉ vì thiếu một cặp dấu ngoặc.

Ví dụ, điều kiện sau:

```sql
WHERE status = 'paid'
   OR status = 'pending' AND amount >= 100
```

không có nghĩa là “đơn đã thanh toán hoặc đang chờ **và** đều có số tiền từ 100 trở lên”. Vì `AND` có độ ưu tiên cao hơn `OR`, SQL hiểu nó như sau:

```sql
WHERE status = 'paid'
   OR (status = 'pending' AND amount >= 100)
```

Nếu yêu cầu là **đơn có trạng thái `paid` hoặc `pending`, đồng thời có số tiền từ 100 trở lên**, phải viết:

```sql
WHERE (status = 'paid' OR status = 'pending')
  AND amount >= 100
```

Bài học này tập trung vào ngữ nghĩa biểu thức SQL: **độ ưu tiên toán tử (*precedence*)**, **hướng kết hợp (*associativity*)**, **dấu ngoặc**, **biểu thức lồng nhau**, và tác động của giá trị `NULL`. Ví dụ chạy trên PostgreSQL; nhiều nguyên tắc áp dụng rộng rãi cho SQL, nhưng độ ưu tiên chi tiết của một số toán tử và quy tắc ép kiểu có thể khác giữa các hệ quản trị.

## 1. Chuẩn bị dữ liệu thực hành

Chạy phần sau trong một phiên PostgreSQL dùng để học tập. Bảng tạm chỉ tồn tại trong phiên làm việc hiện tại.

```sql
CREATE TEMP TABLE sql_operator_demo (
    order_id      INTEGER PRIMARY KEY,
    status        TEXT,
    amount        NUMERIC(10, 2) NOT NULL,
    discount_rate NUMERIC(4, 2)
        CHECK (discount_rate BETWEEN 0 AND 1),
    is_priority   BOOLEAN
);

INSERT INTO sql_operator_demo (
    order_id, status, amount, discount_rate, is_priority
) VALUES
    (1, 'paid',      120.00, 0.10, TRUE),
    (2, 'pending',    80.00, NULL, FALSE),
    (3, 'paid',       40.00, 0.00, FALSE),
    (4, 'cancelled', 200.00, NULL, TRUE),
    (5, 'pending',   150.00, 0.20, TRUE),
    (6, NULL,         60.00, NULL, FALSE),
    (7, 'paid',      200.00, NULL, NULL);
```

Có bảy đơn mẫu, với các giá trị có chủ đích: đơn `3` đã thanh toán nhưng dưới 100; đơn `5` đang chờ và trên 100; đơn `6` chưa có trạng thái; đơn `7` không xác định cờ ưu tiên. Chúng giúp phân biệt trường hợp **đúng**, **sai** và **không xác định**.

Trong phần dưới, tất cả câu truy vấn dùng bảng `sql_operator_demo`, trừ khi có ghi chú rõ là ví dụ độc lập.

## 2. Phân biệt bốn khái niệm dễ nhầm

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Độ ưu tiên** (*precedence*) | Khi không có dấu ngoặc, toán tử nào được gắn với toán hạng trước? | `a + b * c` được nhóm thành `a + (b * c)` |
| **Hướng kết hợp** (*associativity*) | Khi có nhiều toán tử cùng mức ưu tiên, chúng được nhóm theo hướng nào? | `20 - 6 - 2` được nhóm thành `(20 - 6) - 2` |
| **Dấu ngoặc** (*parentheses*) | Người viết muốn chỉ rõ một nhóm biểu thức nào? | `(a + b) * c` thay cách nhóm mặc định |
| **Thứ tự đánh giá/thực thi** (*evaluation/execution*) | Hệ quản trị tính toán, lọc và tối ưu các phần của truy vấn theo trình tự vật lý nào? | Bộ tối ưu hóa có thể đổi thứ tự xử lý điều kiện trong `WHERE` |

**Điểm mấu chốt:** Độ ưu tiên và dấu ngoặc xác định **cấu trúc logic** của biểu thức. Chúng **không** cam kết rằng SQL sẽ thực hiện các phép tính theo đúng thứ tự từ trái qua phải hoặc dừng khi một vế `AND`/`OR` đã đủ để quyết định kết quả.

Đừng nhầm hai việc:

- `(A OR B) AND C` xác định rõ **điều kiện nào phải cùng đúng**.
- “Đánh giá `A` trước, nếu sai thì không tính `B`” là giả định về **thứ tự tính toán**, và không nên dựa vào giả định đó để ngăn lỗi hay tác dụng phụ.

## 3. Bậc ưu tiên cần nhớ khi đọc truy vấn

Để đọc phần lớn điều kiện thực tế, có thể dùng bảng tư duy sau, từ mức ưu tiên cao xuống thấp:

| Mức trực quan | Nhóm toán tử/biểu thức | Ví dụ |
| --- | --- | --- |
| Nhóm tường minh | `(...)` | `(amount + 20) * 2` |
| Tính toán số học | Nhân, chia, chia dư; rồi cộng, trừ | `a + b * c` |
| Phép so sánh và vị từ | `=`, `<>`, `<`, `>=`, `IN`, `BETWEEN`, `LIKE`, `IS NULL`... | `amount >= 100` |
| Phủ định logic | `NOT` | `NOT (status = 'paid')` |
| Kết hợp logic | `AND` | `is_priority IS TRUE AND amount > 100` |
| Kết hợp lựa chọn | `OR` | `status = 'paid' OR status = 'pending'` |

Bảng trên là **mô hình học cơ bản**, không phải danh sách thứ bậc chính xác cho *mọi* loại toán tử trong *mọi* hệ quản trị. Chẳng hạn, PostgreSQL có các quy định riêng về ép kiểu `::`, toán tử do người dùng định nghĩa, phép lũy thừa `^`, `BETWEEN` và các vị từ. SQL Server, MySQL và Oracle cũng có những khác biệt về toán tử chuỗi, kiểu Boolean hoặc thứ tự ưu tiên chi tiết. Với biểu thức khó đọc hoặc có nhiều kiểu toán tử, **đặt dấu ngoặc theo ý nghĩa nghiệp vụ** là lựa chọn rõ ràng và dễ di chuyển giữa các hệ quản trị nhất.

Trong các điều kiện Boolean thông thường, hãy ghi nhớ chắc chắn:

```text
NOT  →  AND  →  OR
```

Do đó, với `A`, `B`, `C` là các điều kiện hợp lệ:

```sql
-- Cấu trúc logic mặc định:
A OR B AND C

-- Cấu trúc tương đương khi viết rõ:
A OR (B AND C)

-- Một điều kiện khác về nghĩa:
(A OR B) AND C
```

`A`, `B`, `C` trong khối trên là **ký hiệu điều kiện giả định**, không phải tên cột có thể chạy ngay.

## 4. Số học: ưu tiên, hướng kết hợp và dấu ngoặc

### 4.1. Nhân/chia trước cộng/trừ

```sql
SELECT
    10 - 2 * 3   AS default_result,
    (10 - 2) * 3 AS grouped_result;
```

Hai kết quả là:

| Biểu thức | Cách nhóm | Kết quả |
| --- | --- | ---: |
| `10 - 2 * 3` | `10 - (2 * 3)` | 4 |
| `(10 - 2) * 3` | `(10 - 2) * 3` | 24 |

Dấu ngoặc không đơn thuần giúp định dạng cho dễ đọc; nó có thể **thay đổi kết quả**.

### 4.2. Cùng mức ưu tiên: xét hướng kết hợp

Phép trừ, chia và các phép toán phổ biến khác thường được nhóm từ trái sang phải ở cùng mức ưu tiên:

```sql
SELECT
    20 - 6 - 2    AS subtraction_default,
    20 - (6 - 2)  AS subtraction_grouped,
    20 / 5 * 2    AS division_default,
    20 / (5 * 2)  AS division_grouped;
```

Trong PostgreSQL với các số nguyên ở ví dụ này, kết quả lần lượt là `12`, `16`, `8`, `2`.

Lưu ý rằng “kết hợp từ trái sang phải” là **quy tắc nhóm cú pháp**, không bảo đảm máy chủ thật sự phải thực thi từng thao tác đúng theo trình tự vật lý đó.

### 4.3. Kiểu dữ liệu cũng ảnh hưởng đến kết quả

Dấu ngoặc không thay thế được hiểu biết về kiểu dữ liệu. Trong PostgreSQL:

```sql
SELECT
    5 / 2       AS integer_division,
    5.0 / 2     AS numeric_division,
    (5::NUMERIC) / 2 AS explicit_numeric_division;
```

- `5 / 2` dùng toán hạng nguyên, trả `2` (phần lẻ bị cắt).
- `5.0 / 2` và `5::NUMERIC / 2` thực hiện phép chia theo kiểu số thập phân, trả giá trị bằng `2.5`.

Khi cần số tiền hoặc tỷ lệ chính xác, hãy chọn kiểu `NUMERIC` phù hợp và quy tắc làm tròn rõ ràng; đừng kỳ vọng một cặp ngoặc tự chuyển phép chia nguyên thành phép chia thập phân.

### 4.4. Lồng nhiều lớp để tính giá sau chiết khấu

Giả sử `discount_rate` nằm trong khoảng từ `0` đến `1`; giá trị `NULL` được **quy ước trong ví dụ** là không giảm giá:

```sql
SELECT
    order_id,
    amount,
    discount_rate,
    ROUND(
        amount * (1 - COALESCE(discount_rate, 0)),
        2
    ) AS amount_after_discount
FROM sql_operator_demo
ORDER BY order_id;
```

Đọc biểu thức từ trong ra ngoài:

1. `COALESCE(discount_rate, 0)` chọn tỷ lệ giảm giá, thay `NULL` bằng `0` theo quy ước đã nêu.
2. `(1 - ...)` tính tỷ lệ còn lại cần thanh toán.
3. `amount * (...)` nhân số tiền ban đầu với tỷ lệ còn lại.
4. `ROUND(..., 2)` làm tròn đến hai chữ số thập phân.

Đối với đơn `1`, số tiền sau giảm giá là `120.00 * (1 - 0.10) = 108.00`. Với đơn `5`, kết quả là `150.00 * (1 - 0.20) = 120.00`.

**Cần phân biệt:** Ngoặc quanh `1 - COALESCE(...)` thay đổi cách tính, còn ngoặc trong `COALESCE(...)` và `ROUND(...)` dùng để truyền đối số cho hàm. Chúng đều có hình thức `(...)` nhưng vai trò cú pháp khác nhau.

## 5. Boolean: vì sao `AND` và `OR` là nơi dễ sai nhất

### 5.1. Xem tập kết quả thay vì chỉ nhìn câu SQL

So sánh hai truy vấn sau:

```sql
-- Truy vấn A: tất cả đơn paid; cộng thêm đơn pending >= 100.
SELECT order_id, status, amount
FROM sql_operator_demo
WHERE status = 'paid'
   OR status = 'pending' AND amount >= 100
ORDER BY order_id;
```

```sql
-- Truy vấn B: cả paid lẫn pending đều phải có amount >= 100.
SELECT order_id, status, amount
FROM sql_operator_demo
WHERE (status = 'paid' OR status = 'pending')
  AND amount >= 100
ORDER BY order_id;
```

Kết quả với dữ liệu thực hành:

| Truy vấn | `order_id` được trả về | Vì sao? |
| --- | --- | --- |
| A | `1, 3, 5, 7` | `paid` được lấy bất kể số tiền; `pending` chỉ lấy khi `amount >= 100` |
| B | `1, 5, 7` | Trạng thái thuộc hai loại cho phép **và** số tiền phải từ 100 trở lên |

Đơn `3` chỉ có `40.00`: nó giúp phát hiện ngay sự khác nhau giữa hai điều kiện.

### 5.2. Phủ định `NOT` phải có phạm vi rõ

```sql
SELECT order_id, status
FROM sql_operator_demo
WHERE NOT (status = 'paid' OR status = 'pending')
ORDER BY order_id;
```

Truy vấn này chỉ lấy đơn `4` (`cancelled`). Cách nhóm này phủ định **toàn bộ lựa chọn trạng thái**.

Ngược lại:

```sql
WHERE NOT (status = 'paid') OR status = 'pending'
```

phủ định **chỉ** điều kiện `status = 'paid'` rồi kết hợp với `pending` bằng `OR`. Hai biểu thức có ý nghĩa khác nhau.

Quy tắc biến đổi De Morgan là công cụ hữu ích:

```text
NOT (A AND B)  ⇔  (NOT A) OR (NOT B)
NOT (A OR B)   ⇔  (NOT A) AND (NOT B)
```

Các đẳng thức này vẫn đúng theo logic ba giá trị của SQL. Tuy vậy, với các điều kiện có `NULL`, phải giữ đúng hành vi `UNKNOWN` khi phân tích kết quả; “không thỏa điều kiện” trong `WHERE` không luôn đồng nghĩa với phép phủ định trả `TRUE`.

### 5.3. Phân nhóm điều kiện truy cập

Dấu ngoặc không chỉ tác động đến báo cáo; nó còn có thể thay đổi phạm vi dữ liệu người dùng được xem. Giả sử một ứng dụng cho phép một tài khoản xem tài liệu **trong tổ chức 10**, nếu tài liệu do mình sở hữu hoặc được đánh dấu công khai.

```sql
-- Ví dụ sai ý nghĩa: tài liệu public của tổ chức khác vẫn lọt qua.
SELECT document_id
FROM documents
WHERE organization_id = 10
  AND owner_id = 20
   OR is_public = TRUE;
```

`AND` gắn chặt hơn `OR`, nên SQL hiểu `(organization_id = 10 AND owner_id = 20) OR is_public = TRUE`. Một tài liệu công khai từ tổ chức khác có thể vượt qua điều kiện này.

```sql
-- Ví dụ diễn đạt đúng yêu cầu:
SELECT document_id
FROM documents
WHERE organization_id = 10
  AND (owner_id = 20 OR is_public = TRUE);
```

Bảng `documents` là ví dụ tình huống độc lập, không nằm trong bộ dữ liệu tạm. Trong ứng dụng thực, các giá trị tổ chức/người dùng đến từ ngữ cảnh xác thực và nên được truyền bằng tham số truy vấn; dấu ngoặc chỉ giúp giữ đúng **ngữ nghĩa phân quyền** được thiết kế.

## 6. Giá trị `NULL`: logic ba giá trị và dấu ngoặc

SQL sử dụng ba trạng thái logic trong nhiều biểu thức: `TRUE`, `FALSE` và `UNKNOWN`. Phần lớn phép so sánh với `NULL` cho `UNKNOWN`, không phải `TRUE` hay `FALSE`.

Một số quy tắc quan trọng:

| Biểu thức | Kết quả |
| --- | --- |
| `TRUE AND UNKNOWN` | `UNKNOWN` |
| `FALSE AND UNKNOWN` | `FALSE` |
| `TRUE OR UNKNOWN` | `TRUE` |
| `FALSE OR UNKNOWN` | `UNKNOWN` |
| `NOT UNKNOWN` | `UNKNOWN` |

Ở đây `UNKNOWN` được dùng để diễn giải giá trị Boolean `NULL` trong SQL.

Thử ngay:

```sql
SELECT
    TRUE AND NULL::BOOLEAN    AS and_unknown,
    FALSE AND NULL::BOOLEAN   AS and_false,
    TRUE OR NULL::BOOLEAN     AS or_true,
    FALSE OR NULL::BOOLEAN    AS or_unknown,
    NOT NULL::BOOLEAN         AS not_unknown;
```

Các cột ở vị trí “unknown” trả về `NULL`. Dấu ngoặc **không** biến `UNKNOWN` thành `FALSE` hay `TRUE`.

### 6.1. Vì sao `NOT (status = 'paid')` không lấy dòng có `status IS NULL`?

```sql
SELECT order_id, status
FROM sql_operator_demo
WHERE NOT (status = 'paid')
ORDER BY order_id;
```

Truy vấn lấy các đơn `2`, `4`, `5`. Với đơn `6`:

```text
status = 'paid'        → UNKNOWN
NOT (status = 'paid')  → UNKNOWN
WHERE UNKNOWN          → hàng bị loại
```

`WHERE` chỉ giữ hàng có điều kiện bằng `TRUE`. Muốn bao gồm cả dòng chưa có trạng thái, cần nêu rõ:

```sql
SELECT order_id, status
FROM sql_operator_demo
WHERE status <> 'paid'
   OR status IS NULL
ORDER BY order_id;
```

Trong PostgreSQL còn có toán tử so sánh an toàn với `NULL`:

```sql
SELECT order_id
FROM sql_operator_demo
WHERE status IS DISTINCT FROM 'paid'
ORDER BY order_id;
```

Ở đây hai cách đều lấy `2, 4, 5, 6`. `IS DISTINCT FROM` là cú pháp có trong PostgreSQL và một số hệ quản trị khác, nhưng không nên mặc định rằng mọi hệ đều hỗ trợ giống nhau.

### 6.2. Ngoặc không chữa được lỗi `NOT IN` với `NULL`

```sql
SELECT
    1 IN (1, NULL)     AS value_found,
    2 IN (1, NULL)     AS value_unknown,
    2 NOT IN (1, NULL) AS negation_unknown;
```

Kết quả lần lượt là `TRUE`, `NULL`, `NULL`. Lý do: không tìm thấy `2` trong danh sách, nhưng phần tử `NULL` khiến câu “không bằng bất kỳ giá trị nào” chưa thể được xác định là đúng.

Ví dụ này đặc biệt quan trọng khi `NOT IN` nhận kết quả của một subquery có thể chứa `NULL`. Trong bài toán “không tồn tại bản ghi liên quan”, `NOT EXISTS` thường rõ nghĩa hơn và tránh được bẫy `NULL` nói trên.

## 7. Các vị từ `BETWEEN`, `IN`, `LIKE` và cách đặt ngoặc

Các vị từ (*predicates*) tạo ra điều kiện logic. Một số có hình thức giống toán tử kết hợp, nhưng là **một cấu trúc cú pháp** riêng.

### 7.1. `BETWEEN ... AND ...`: `AND` ở đây thuộc vị từ khoảng

```sql
SELECT order_id, amount
FROM sql_operator_demo
WHERE (amount BETWEEN 80 AND 150)
  AND (status = 'paid' OR status = 'pending')
ORDER BY order_id;
```

`BETWEEN 80 AND 150` bao gồm cả hai đầu `80` và `150`. Điều kiện nhóm ngoài là một `AND` **khác** để ghép hai vị từ. Truy vấn trả `1`, `2`, `5`.

Có thể diễn đạt thành:

```sql
WHERE (amount >= 80 AND amount <= 150)
  AND (status = 'paid' OR status = 'pending')
```

Với các giá trị số bình thường và không có tác dụng phụ, hai dạng nêu cùng yêu cầu khoảng. Viết ngoặc ở các vị từ lớn giúp người đọc không nhầm `AND` của `BETWEEN` với `AND` nối điều kiện. `NOT BETWEEN` có nghĩa phủ định điều kiện khoảng; nên viết rõ nếu biểu thức bên cạnh phức tạp.

### 7.2. `IN`: danh sách giá trị và các điều kiện đi kèm

```sql
SELECT order_id, status, amount
FROM sql_operator_demo
WHERE status IN ('paid', 'pending')
  AND amount >= 100
ORDER BY order_id;
```

Kết quả là `1`, `5`, `7`, tương đương với `(status = 'paid' OR status = 'pending') AND amount >= 100` trên dữ liệu mẫu.

Ngoặc trong `IN ('paid', 'pending')` dùng để đóng **danh sách giá trị**. Khi muốn nhóm một phần biểu thức Boolean, cần **ngoặc cho chính biểu thức**, ví dụ `(status IN (...) OR is_priority IS TRUE) AND amount >= 100`.

### 7.3. `LIKE`: kết hợp tìm mẫu với điều kiện khác

```sql
SELECT order_id, status
FROM sql_operator_demo
WHERE (status LIKE 'p%')
  AND amount >= 100
ORDER BY order_id;
```

Trong mẫu `LIKE 'p%'`, ký hiệu `%` khớp với chuỗi gồm không hoặc nhiều ký tự. Ví dụ có thể khớp `paid` hoặc `pending` và trả về `1, 5, 7` sau điều kiện tiền. Cách so sánh chữ hoa/chữ thường và toán tử tìm mẫu mở rộng có thể khác theo hệ quản trị hoặc cấu hình.

### 7.4. Tránh viết so sánh dây chuyền như toán học

Trong toán học, ta có thể viết `0 < x < 100`. Với SQL, nên viết thành hai phép so sánh liên kết bằng `AND`:

```sql
WHERE amount > 0
  AND amount < 100
```

Không dựa vào cú pháp so sánh dây chuyền; tùy hệ quản trị nó có thể bị từ chối hoặc cho ngữ nghĩa không mong muốn.

## 8. Biểu thức lồng nhau: `CASE`, `COALESCE`, hàm và subquery

Một biểu thức SQL có thể chứa nhiều biểu thức con. Mỗi lớp nên có **một nhiệm vụ rõ ràng**; điều này giúp kiểm tra cả kết quả lẫn ý nghĩa nghiệp vụ.

### 8.1. `CASE` kết hợp nhiều điều kiện

```sql
SELECT
    order_id,
    status,
    amount,
    CASE
        WHEN status = 'paid' AND amount >= 100
            THEN 'paid_large'
        WHEN status = 'paid'
            THEN 'paid_small'
        WHEN status = 'pending' AND amount >= 100
            THEN 'pending_large'
        ELSE 'other'
    END AS order_group
FROM sql_operator_demo
ORDER BY order_id;
```

Kết quả phân loại:

| `order_id` | `order_group` |
| --- | --- |
| 1 | `paid_large` |
| 2 | `other` |
| 3 | `paid_small` |
| 4 | `other` |
| 5 | `pending_large` |
| 6 | `other` |
| 7 | `paid_large` |

`CASE` xét các nhánh `WHEN` theo thứ tự để chọn nhánh phù hợp đầu tiên. Vì vậy nhánh `status = 'paid'` tổng quát phải đứng **sau** nhánh `status = 'paid' AND amount >= 100`; nếu đảo ngược, các đơn `paid_large` sẽ bị bắt ngay bởi nhánh tổng quát. Với điều kiện `UNKNOWN`, nhánh `WHEN` không được coi là đúng và sẽ chuyển sang nhánh tiếp theo hoặc `ELSE`.

### 8.2. Lồng `CASE`, `COALESCE` và phép toán số học

Giả sử chỉ đơn đã thanh toán được tính vào số tiền ghi nhận; với đơn `paid`, áp dụng tỷ lệ giảm giá nếu có:

```sql
SELECT
    order_id,
    CASE
        WHEN status = 'paid'
            THEN ROUND(
                amount * (1 - COALESCE(discount_rate, 0)),
                2
            )
        ELSE 0::NUMERIC
    END AS recognized_amount
FROM sql_operator_demo
ORDER BY order_id;
```

Đọc từ trong ra ngoài:

1. `COALESCE(discount_rate, 0)` xử lý tỷ lệ giảm giá thiếu.
2. `1 - ...` tính tỷ lệ còn lại.
3. `amount * ...` tính giá trị sau giảm.
4. `ROUND(..., 2)` làm tròn.
5. `CASE` chỉ trả giá trị đó khi trạng thái là `paid`; mọi trạng thái khác, kể cả `NULL`, trả `0` theo quy ước báo cáo.

Một cách tổng hợp trực tiếp:

```sql
SELECT SUM(
    CASE
        WHEN status = 'paid'
            THEN amount * (1 - COALESCE(discount_rate, 0))
        ELSE 0
    END
) AS total_recognized_amount
FROM sql_operator_demo;
```

Theo dữ liệu mẫu, kết quả là `348.00` (`108.00 + 40.00 + 200.00`). Đây là **định nghĩa số liệu của bài tập**; trong hệ thống thương mại thật, doanh thu có thể còn phụ thuộc hoàn tiền, thuế, phí, thời điểm ghi nhận và nhiều quy tắc khác.

### 8.3. Subquery trong ngoặc là một biểu thức con

Tìm đơn `paid` có số tiền **lớn hơn trung bình** của các đơn `paid`:

```sql
SELECT order_id, amount
FROM sql_operator_demo
WHERE status = 'paid'
  AND amount > (
      SELECT AVG(amount)
      FROM sql_operator_demo
      WHERE status = 'paid'
  )
ORDER BY order_id;
```

Subquery bên trong trả **một giá trị**: trung bình của `120`, `40` và `200` là `120`. Biểu thức ngoài so sánh từng đơn với giá trị đó, nên chỉ đơn `7` có `amount = 200` được lấy.

Ngoặc ở đây xác định phạm vi **subquery vô hướng** (scalar subquery), khác với ngoặc nhóm Boolean như `(A OR B)`. Nếu subquery dùng tại vị trí cần một giá trị mà lại trả nhiều hàng, PostgreSQL sẽ báo lỗi; nếu không có hàng, kết quả vô hướng là `NULL`, và phép so sánh bên ngoài có thể trở thành `UNKNOWN`.

### 8.4. Các loại ngoặc có cùng ký hiệu nhưng khác vai trò

| Mẫu | Vai trò |
| --- | --- |
| `(a + b) * c` | Nhóm phép tính |
| `(A OR B) AND C` | Nhóm điều kiện Boolean |
| `ROUND(value, 2)` | Danh sách đối số hàm |
| `status IN ('paid', 'pending')` | Tập giá trị của vị từ `IN` |
| `amount > (SELECT AVG(amount) ...)` | Bao một subquery vô hướng |
| `COUNT(*) OVER (PARTITION BY status)` | Khai báo cửa sổ cho window function |
| `FROM (SELECT ...) AS t` | Bao một bảng dẫn xuất (*derived table*) |

Không nên xóa hoặc chuyển dấu ngoặc theo thói quen. Trước hết cần biết nó đang **chỉ nhóm phép toán**, **định nghĩa cú pháp hàm**, hay **giới hạn phạm vi truy vấn con**.

## 9. Cấu trúc biểu thức không đồng nghĩa thứ tự thực thi

Một câu SQL mô tả tập kết quả cần có. Bộ tối ưu hóa được phép chọn kế hoạch thực thi phù hợp, bao gồm việc biến đổi hoặc thay đổi thứ tự xử lý một số biểu thức khi vẫn giữ ngữ nghĩa truy vấn.

### 9.1. Không dựa vào `AND` để tránh chia cho 0

Thoạt nhìn, điều kiện sau có vẻ an toàn vì “đã kiểm tra `denominator <> 0` trước”:

```sql
-- Không nên dựa vào điều kiện đầu để bảo đảm thứ tự tính toán.
WHERE denominator <> 0
  AND numerator / denominator > 10
```

SQL không cam kết phép chia chỉ diễn ra sau phép kiểm tra bên trái theo thứ tự viết. Khi cần phép chia an toàn, hãy mã hóa điều kiện trực tiếp vào mẫu số:

```sql
WITH measurements (numerator, denominator) AS (
    VALUES
        (100.0, 0.0),
        (100.0, 4.0)
)
SELECT
    numerator,
    denominator,
    numerator / NULLIF(denominator, 0) AS safe_ratio
FROM measurements;
```

`NULLIF(denominator, 0)` trả `NULL` khi mẫu số bằng 0, nên phép chia sẽ trả `NULL` thay vì chia cho 0. Dòng còn lại trả `25.0`. Nếu báo cáo muốn thay `NULL` bằng một giá trị mặc định, hãy dùng `COALESCE` **sau khi** đã xác định giá trị mặc định đó thực sự hợp lý.

Lưu ý thêm: `CASE` giúp diễn đạt nhánh điều kiện, nhưng không phải rào chắn tuyệt đối cho mọi biểu thức có thể gây lỗi trong mọi giai đoạn, đặc biệt với hằng số được bộ tối ưu hóa tính sớm. Với các thao tác nguy hiểm, cách viết an toàn như `NULLIF` thường rõ ràng hơn giả định về thứ tự đánh giá.

### 9.2. Dấu ngoặc cũng không thay thế quy tắc tổng hợp

```sql
SELECT status, SUM(amount) AS total_amount
FROM sql_operator_demo
WHERE amount >= 100
GROUP BY status
HAVING SUM(amount) >= 200;
```

`WHERE` lọc **hàng riêng lẻ** trước khi tổng hợp; `HAVING` lọc **nhóm** sau tổng hợp về mặt logic. Việc thêm ngoặc quanh `SUM(amount)` không làm `SUM` trở thành một điều kiện có thể dùng trong `WHERE` cùng cấp.

Một cách tư duy hữu ích về thứ tự xử lý logic của truy vấn là:

```text
FROM / JOIN → WHERE → GROUP BY → HAVING
            → SELECT → ORDER BY → LIMIT
```

Đây là mô hình hiểu ngữ nghĩa, **không phải thứ tự xử lý vật lý bắt buộc** của bộ máy SQL. Với truy vấn chứa window function, `DISTINCT` hoặc subquery, còn có các giai đoạn logic khác cần xét.

## 10. Cách viết biểu thức dễ đọc và ít lỗi

Khi một điều kiện có cả `AND` và `OR`, hãy **đặt ngoặc cho nhóm nghiệp vụ**, kể cả khi bạn biết thứ tự ưu tiên mặc định. Điều đó giúp người đọc xác nhận ngay ý định:

```sql
SELECT order_id, status, amount, is_priority
FROM sql_operator_demo
WHERE (status = 'paid' OR status = 'pending')
  AND (amount >= 100 OR is_priority IS TRUE)
ORDER BY order_id;
```

Câu trên có hai nhóm rõ ràng: trạng thái được chấp nhận và điều kiện về số tiền/ưu tiên. Đơn `1, 5, 7` đều thỏa; đơn `3` không thỏa vì tiền dưới 100 và không được ưu tiên.

Khi biểu thức dài, viết nhiều dòng theo cấp độ ngoặc:

```sql
WHERE
    (
        status = 'paid'
        OR status = 'pending'
    )
    AND (
        amount >= 100
        OR (
            is_priority IS TRUE
            AND amount >= 50
        )
    )
```

Ngoặc lồng nhau chỉ có ích khi làm rõ nhóm. Nếu một biểu thức vẫn quá dài để hiểu, có thể tách các phép tính thành cột trung gian trong CTE:

```sql
WITH classified AS (
    SELECT
        order_id,
        status,
        amount,
        (status IN ('paid', 'pending')) AS eligible_status,
        (amount >= 100 OR is_priority IS TRUE) AS eligible_value
    FROM sql_operator_demo
)
SELECT order_id, status, amount
FROM classified
WHERE eligible_status AND eligible_value
ORDER BY order_id;
```

Với những cột Boolean có thể mang `NULL`, đừng mặc định rằng mọi phép đánh giá trung gian chỉ có hai giá trị. Trong ví dụ trên, điều kiện cuối chỉ giữ các hàng mà **cả hai cờ đều là `TRUE`**.

Nên hình thành những thói quen sau:

- Viết yêu cầu bằng lời trước, như “thuộc trạng thái A hoặc B **và** tiền từ X trở lên”, rồi biến từng cụm thành một nhóm `(...)`.
- Dùng cùng một phong cách ngoặc trong mã nguồn và trong tài liệu, đặc biệt ở phần lọc quyền, tiền bạc và trạng thái.
- Đặt ngoặc rõ cho phép trừ/chia hoặc tỷ lệ phần trăm, vì hướng kết hợp và kiểu số có thể làm đổi kết quả.
- Khi có `NULL`, xác định rõ đó là “chưa biết”, “không áp dụng”, hay được phép thay bằng giá trị mặc định.
- Với biểu thức lồng nhiều lớp, xem riêng kết quả của phần trong trước, rồi ghép thành câu lệnh lớn.
- Viết truy vấn có tham số khi nhận dữ liệu đầu vào từ ứng dụng; việc thêm dấu ngoặc không thay thế biện pháp chống SQL injection.
- Xây dựng một bộ dữ liệu mẫu có trường hợp ở ranh giới (đúng ngưỡng, dưới ngưỡng, `NULL`, đồng hạng hoặc ngoại lệ) để đối chiếu ý nghĩa câu truy vấn.

## 11. Bài tập thực hành và đáp án gợi ý

Các bài tập đều dùng bảng `sql_operator_demo` đã tạo ở đầu bài. Nên dự đoán `order_id` được trả về **trước khi chạy**.

### Bài 1 — Dự đoán độ ưu tiên

```sql
SELECT order_id
FROM sql_operator_demo
WHERE status = 'paid'
   OR status = 'cancelled' AND amount < 100
ORDER BY order_id;
```

**Đáp án:** `1, 3, 7`. Không có đơn `cancelled` nào dưới 100, nhưng mọi đơn `paid` đều thỏa nhánh đầu. Biểu thức được hiểu là:

```sql
WHERE (status = 'paid')
   OR (status = 'cancelled' AND amount < 100)
```

### Bài 2 — Thay đổi yêu cầu bằng ngoặc

Yêu cầu: “Lấy đơn có trạng thái `paid` hoặc `cancelled` **và** số tiền dưới 100”. Sửa bài 1.

```sql
SELECT order_id
FROM sql_operator_demo
WHERE (status = 'paid' OR status = 'cancelled')
  AND amount < 100
ORDER BY order_id;
```

**Đáp án:** Chỉ có đơn `3`, vì nó là `paid` và có số tiền `40.00`.

### Bài 3 — Xử lý `NULL` khi phủ định

Dự đoán vì sao truy vấn sau không trả đơn `6`, và viết lại để lấy cả đơn `6`.

```sql
SELECT order_id
FROM sql_operator_demo
WHERE NOT (status = 'paid')
ORDER BY order_id;
```

**Giải thích:** `NULL = 'paid'` cho `UNKNOWN`, và `NOT UNKNOWN` vẫn là `UNKNOWN`. `WHERE` loại hàng này. Có thể sửa:

```sql
SELECT order_id
FROM sql_operator_demo
WHERE status <> 'paid'
   OR status IS NULL
ORDER BY order_id;
```

**Đáp án:** `2, 4, 5, 6`.

### Bài 4 — Kết hợp phân loại và biểu thức số học

Yêu cầu: chỉ tính giá trị sau giảm giá cho đơn `paid` có `amount >= 100`; các đơn khác nhận `0`. Mặc định `discount_rate = 0` nếu dữ liệu thiếu.

```sql
SELECT
    order_id,
    CASE
        WHEN status = 'paid' AND amount >= 100 THEN
            ROUND(
                amount * (1 - COALESCE(discount_rate, 0)),
                2
            )
        ELSE 0::NUMERIC
    END AS eligible_amount
FROM sql_operator_demo
ORDER BY order_id;
```

**Đáp án:** Đơn `1` có `108.00`, đơn `7` có `200.00`, các đơn còn lại có `0.00` (cách hiển thị chữ số thập phân có thể tùy công cụ). Tổng giá trị đủ điều kiện là `308.00`.

### Bài 5 — Lý giải một biểu thức dài

```sql
WHERE status = 'paid'
  AND amount >= 100
   OR status = 'pending'
  AND is_priority IS TRUE
```

**Yêu cầu:** Viết lại có ngoặc, giữ nguyên nghĩa; sau đó cho biết các đơn được chọn.

```sql
WHERE (status = 'paid' AND amount >= 100)
   OR (status = 'pending' AND is_priority IS TRUE)
```

**Đáp án:** `1, 5, 7`. Hai nhóm điều kiện được nối bằng `OR`. Mọi đơn trong mỗi nhóm phải thỏa cả hai điều kiện con.

## 12. Khi nào nên thêm dấu ngoặc?

Dấu ngoặc là cách thể hiện trực tiếp **ý định của người viết SQL**. Không cần ngoặc mọi cột hoặc mỗi phép so sánh đơn giản, nhưng nên dùng chúng khi có nhiều loại toán tử trong cùng một biểu thức, khi phối hợp `AND` với `OR`/`NOT`, khi tính tiền và tỷ lệ, hoặc khi lồng các biểu thức `CASE`, hàm và truy vấn con.

Muốn kiểm tra một biểu thức khó, hãy làm theo trình tự:

1. Xác định các biểu thức nguyên tử, như `status = 'paid'` hay `amount >= 100`.
2. Nhóm các biểu thức theo nghĩa nghiệp vụ, rồi thêm dấu ngoặc trước khi tối ưu câu SQL.
3. Xác định có thể xuất hiện `NULL` hay không; nếu có, kiểm tra thêm trường hợp `UNKNOWN`.
4. Kiểm tra kiểu dữ liệu và các phép tính không giao hoán như trừ, chia.
5. Chạy thử với dữ liệu có trường hợp ranh giới để xác nhận đúng tập kết quả.
6. Chỉ sau khi đúng nghĩa mới quan tâm kế hoạch thực thi và hiệu năng.

Khi nắm chắc sự khác biệt giữa **cấu trúc biểu thức**, **logic ba giá trị** và **thực thi truy vấn**, bạn sẽ đọc được SQL phức tạp chính xác hơn và viết điều kiện lọc, tính toán, phân quyền hoặc báo cáo đáng tin cậy hơn.

