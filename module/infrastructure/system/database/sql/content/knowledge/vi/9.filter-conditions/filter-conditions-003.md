# BETWEEN, biên bao gồm và khoảng nửa mở

Khi đặt điều kiện lọc trong SQL, nhiều câu hỏi được diễn đạt bằng một **khoảng giá trị**: đơn hàng từ 100.000 đến 500.000 đồng, sản phẩm có điểm từ 7 đến 9, hoặc sự kiện xảy ra trong tháng 6. Truy vấn có thể trông rất đơn giản, nhưng chỉ một dấu `<=` thay cho `<` cũng có thể đưa thêm bản ghi vào kết quả hoặc làm hai báo cáo theo ngày đếm trùng cùng một sự kiện.

Bài học này tập trung vào ba ý tưởng:

- `BETWEEN` kiểm tra một giá trị nằm **giữa hai biên, bao gồm cả hai biên**.
- Một khoảng có thể được viết bằng nhiều cặp toán tử so sánh; cách viết phải phản ánh chính xác **biên nào được lấy và biên nào bị loại**.
- **Khoảng nửa mở** (*half-open interval*), thường viết `>= lower_bound AND < upper_bound`, đặc biệt phù hợp để lọc thời gian, chia các khoảng liên tiếp và tránh trùng lặp ở ranh giới.

Các ví dụ dùng cú pháp SQL thông dụng và PostgreSQL để minh họa kiểu thời gian, `NULL` và múi giờ. Khi hệ quản trị khác có hành vi hoặc cú pháp riêng, bài học sẽ chỉ rõ.

## 1. Một khoảng dữ liệu có những thành phần gì?

Một khoảng gồm **biên dưới** (*lower bound*), **biên trên** (*upper bound*) và quy tắc về việc mỗi biên có thuộc khoảng hay không.

Với hai số `100` và `200`, ta có bốn cách biểu diễn:

| Ký hiệu toán học | Điều kiện SQL | Có lấy `100`? | Có lấy `200`? |
|---|---|---|---|
| `[100, 200]` | `value >= 100 AND value <= 200` | Có | Có |
| `[100, 200)` | `value >= 100 AND value < 200` | Có | Không |
| `(100, 200]` | `value > 100 AND value <= 200` | Không | Có |
| `(100, 200)` | `value > 100 AND value < 200` | Không | Không |

Ngoặc vuông `[` hoặc `]` nghĩa là **bao gồm biên**; ngoặc tròn `(` hoặc `)` nghĩa là **loại biên**. Trong SQL thông thường, ký hiệu toán học này được chuyển thành các toán tử so sánh.

```text
Khoảng đóng [100, 200]:
             ●================●
            100              200

Khoảng nửa mở [100, 200):
             ●================○
            100              200

● = giá trị tại biên thuộc khoảng
○ = giá trị tại biên không thuộc khoảng
```

Sự khác biệt chỉ xảy ra đúng tại biên, nhưng các điểm biên là nơi dễ gây lỗi nhất. Ví dụ hai nhóm `[0, 100]` và `[100, 200]` **đều chứa 100**, còn `[0, 100)` và `[100, 200)` thì **không giao nhau**.

## 2. `BETWEEN`: cú pháp và hai biên đều bao gồm

### 2.1. Cú pháp cơ bản

```sql
expression BETWEEN lower_bound AND upper_bound
```

Ý nghĩa logic tương đương:

```sql
expression >= lower_bound
AND expression <= upper_bound
```

Vì cả hai dấu đều có phần bằng (`=`), `BETWEEN` diễn đạt **khoảng đóng** `[lower_bound, upper_bound]`.

Ví dụ:

```sql
SELECT
    100 BETWEEN 100 AND 200 AS at_lower_bound,
    150 BETWEEN 100 AND 200 AS inside_range,
    200 BETWEEN 100 AND 200 AS at_upper_bound,
    201 BETWEEN 100 AND 200 AS outside_range;
```

Theo thứ tự các cột, kết quả là `TRUE`, `TRUE`, `TRUE`, `FALSE` trong PostgreSQL.

Các trường hợp ranh giới:

| Giá trị | `value BETWEEN 100 AND 200` | `value >= 100 AND value < 200` |
|---:|---|---|
| 99 | `FALSE` | `FALSE` |
| 100 | `TRUE` | `TRUE` |
| 150 | `TRUE` | `TRUE` |
| 199 | `TRUE` | `TRUE` |
| 200 | `TRUE` | `FALSE` |
| 201 | `FALSE` | `FALSE` |

Vì vậy, câu “đơn hàng từ 100.000 đến 200.000 đồng, **bao gồm cả hai mức**” phù hợp với `BETWEEN`. Câu “từ 100.000 nhưng **dưới 200.000**” cần dùng `< 200000` thay vì `BETWEEN`.

### 2.2. Ví dụ dữ liệu bán hàng

Xét bảng `orders` giả định:

| order_id | total_amount | placed_at | status |
|---:|---:|---|---|
| 101 | 99999.99 | 2026-05-31 23:59:59 | PAID |
| 102 | 100000.00 | 2026-06-01 00:00:00 | PAID |
| 103 | 150000.00 | 2026-06-01 09:15:00 | PAID |
| 104 | 200000.00 | 2026-06-15 12:30:00 | PENDING |
| 105 | 200000.01 | 2026-06-30 23:59:59.500000 | PAID |
| 106 | 180000.00 | 2026-07-01 00:00:00 | PAID |

`total_amount` được hiểu là kiểu `NUMERIC(12,2)` và `placed_at` là kiểu `TIMESTAMP WITHOUT TIME ZONE`; hai kiểu này được dùng xuyên suốt các ví dụ trước khi đến phần múi giờ.

Yêu cầu: “Lấy các đơn có tổng tiền từ **100.000 đến 200.000**, bao gồm hai mức.”

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000
ORDER BY total_amount, order_id;
```

Kết quả từ bảng mẫu: đơn `102` (`100000.00`), `103` (`150000.00`), `106` (`180000.00`) và `104` (`200000.00`). Điều kiện này **không kiểm tra trạng thái đơn**; muốn chỉ lấy đơn `PAID` thì cần thêm điều kiện `status`.

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000
  AND status = 'PAID'
ORDER BY total_amount, order_id;
```

Khi thêm trạng thái `PAID`, kết quả còn `102`, `103`, `106`. Điều kiện thời gian chưa xuất hiện trong truy vấn nên đơn tháng 7 vẫn có thể có mặt.

### 2.3. Tên `AND` trong `BETWEEN` không phải hai điều kiện rời

Trong câu:

```sql
WHERE total_amount BETWEEN 100000 AND 200000
  AND status = 'PAID'
```

`AND` đầu tiên là một phần của cú pháp `BETWEEN ... AND ...`; `AND` thứ hai nối thêm điều kiện về trạng thái. Có thể dùng ngoặc khi tổ hợp nhiều điều kiện phức tạp để diễn đạt ý định:

```sql
WHERE (total_amount BETWEEN 100000 AND 200000)
  AND (status = 'PAID' OR status = 'PENDING')
```

Nếu đảo ngoặc thành:

```sql
WHERE (total_amount BETWEEN 100000 AND 200000 AND status = 'PAID')
   OR status = 'PENDING'
```

thì **mọi** đơn `PENDING` đều vượt qua nhánh `OR` dù tổng tiền nằm ngoài khoảng. Khi có cả `AND` và `OR`, nên viết ngoặc để tránh diễn giải sai.

## 3. Hai biên của `BETWEEN` có thứ tự

Trong SQL thông thường, `BETWEEN` **không tự sắp xếp lại** hai biên. Biên đầu tiên là biên dưới, biên thứ hai là biên trên.

```sql
SELECT
    150 BETWEEN 100 AND 200 AS ascending_bounds,
    150 BETWEEN 200 AND 100 AS reversed_bounds;
-- TRUE và FALSE.
```

Với phép so sánh số thông thường, `x BETWEEN 200 AND 100` yêu cầu đồng thời `x >= 200` **và** `x <= 100`, nên không có giá trị số nào thỏa.

Nếu hai biên do người dùng nhập tự do, nên xác định rõ quy tắc xử lý:

1. **Từ chối khoảng không hợp lệ**: kiểm tra `lower_bound <= upper_bound` trước khi chạy.
2. **Chuẩn hóa hai biên** nếu nghiệp vụ cho phép người dùng nhập không theo thứ tự, ví dụ tính `LEAST(a,b)` và `GREATEST(a,b)` trên các kiểu phù hợp.
3. **Dùng `BETWEEN SYMMETRIC`** nếu đang làm việc trên PostgreSQL và thực sự muốn cho phép đảo biên.

Ví dụ PostgreSQL:

```sql
SELECT
    150 BETWEEN SYMMETRIC 200 AND 100 AS symmetrical_range;
-- TRUE.
```

`BETWEEN SYMMETRIC` không phải lựa chọn nên mặc định trong bài SQL cần chạy giống nhau trên mọi hệ quản trị. Với một API báo cáo, **kiểm tra dữ liệu đầu vào** thường dễ hiểu hơn việc tự đổi hai biên mà người dùng không biết.

Nếu hai biên bằng nhau:

```sql
SELECT
    150 BETWEEN 150 AND 150 AS closed_one_point,
    (150 >= 150 AND 150 < 150) AS half_open_empty;
-- TRUE và FALSE.
```

Khoảng đóng `[150,150]` chứa đúng một giá trị; khoảng nửa mở `[150,150)` rỗng. Đây là một đặc tính có ích khi xây dựng thuật toán chia các khoảng liên tiếp.

## 4. `NOT BETWEEN`: lấy các giá trị bên ngoài khoảng

`NOT BETWEEN` đảo điều kiện `BETWEEN`:

```sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount NOT BETWEEN 100000 AND 200000
ORDER BY total_amount, order_id;
```

Với dữ liệu mẫu, kết quả là đơn `101` (`99999.99`) và `105` (`200000.01`). Đơn đúng bằng `100000.00` hoặc `200000.00` **không** nằm ngoài khoảng đóng.

Với giá trị và hai biên không `NULL`, ý nghĩa tương đương:

```sql
WHERE total_amount < 100000
   OR total_amount > 200000
```

Việc phủ định khoảng cũng tuân theo logic ba giá trị của SQL khi có `NULL`; không được tự coi `NULL` là “ở ngoài khoảng”. Phần tiếp theo giải thích chi tiết.

## 5. `NULL`, kiểu dữ liệu và logic ba giá trị

### 5.1. `NULL` không tự trở thành giá trị trong hoặc ngoài khoảng

Trong SQL, các phép so sánh có thể cho `TRUE`, `FALSE` hoặc `UNKNOWN`. Điều kiện `WHERE` **chỉ giữ** những dòng mà điều kiện là `TRUE`; `FALSE` và `UNKNOWN` không được giữ.

```sql
SELECT
    CAST(NULL AS INTEGER) BETWEEN 100 AND 200 AS null_value,
    150 BETWEEN CAST(NULL AS INTEGER) AND 200 AS null_lower,
    150 NOT BETWEEN 100 AND CAST(NULL AS INTEGER) AS null_upper;
```

Cả ba biểu thức trên có kết quả `NULL` (đại diện cho `UNKNOWN`) trong PostgreSQL. Nhưng cần hiểu chính xác: một biên `NULL` **không bảo đảm mọi phép `BETWEEN` đều UNKNOWN**, vì một phía của phép `AND` có thể đã sai rõ ràng.

```sql
SELECT 300 BETWEEN CAST(NULL AS INTEGER) AND 200 AS result;
-- FALSE: 300 <= 200 đã FALSE dù 300 >= NULL là UNKNOWN.
```

Vì vậy, không nên học thuộc câu “cứ có `NULL` là `BETWEEN` trả về `NULL`”. Quy tắc đúng là đọc nó như hai phép so sánh kết hợp bằng logic ba giá trị.

Nếu yêu cầu nghiệp vụ có một quy tắc riêng cho hàng thiếu giá trị, hãy viết tường minh:

```sql
-- Ví dụ: chọn đơn có số tiền trong khoảng hoặc chưa biết số tiền.
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000
   OR total_amount IS NULL;
```

Chỉ thêm `OR ... IS NULL` khi đúng yêu cầu, vì **chưa biết số tiền** khác **số tiền nằm trong khoảng**.

### 5.2. Hai đầu khoảng phải so sánh được với giá trị

`BETWEEN` dựa vào phép so sánh `>=` và `<=`. Các toán hạng phải có kiểu tương thích theo quy tắc của hệ quản trị.

```sql
-- Kiểu số:
SELECT 10 BETWEEN 2 AND 20 AS numeric_range;

-- Kiểu ngày:
SELECT DATE '2026-06-15'
       BETWEEN DATE '2026-06-01' AND DATE '2026-06-30' AS date_range;
```

Không nên dựa vào chuyển đổi ngầm giữa `TEXT`, số và ngày ở mọi hệ quản trị:

```sql
-- PostgreSQL: ép giá trị có định dạng số đã được xác minh.
SELECT CAST('150000.00' AS NUMERIC(12,2))
       BETWEEN 100000 AND 200000 AS within_amount;
```

Nếu chuỗi đầu vào là `N/A` hoặc có dấu phân cách số không đúng quy tắc, cast có thể báo lỗi. Quy tắc nhập liệu cần được kiểm tra trước khi chuyển kiểu.

### 5.3. `BETWEEN` trên chuỗi không phải khoảng số

```sql
SELECT '10' BETWEEN '2' AND '9' AS lexical_test;
```

Các chuỗi được so sánh theo quy tắc chuỗi/collation của hệ quản trị, **không phải** theo giá trị số 10, 2, 9. Kết quả phụ thuộc kiểu và collation; ở nhiều thứ tự chữ thông dụng, `'10'` đứng trước `'2'`.

Các câu hỏi như “mã từ A đến M” có thể phù hợp với khoảng chuỗi **nếu** nghiệp vụ hiểu rõ collation và cách xử lý chữ hoa, dấu, ký tự đặc biệt. Với số lượng, số tiền hoặc điểm số, nên lưu ở kiểu số; với ngày/giờ nên lưu ở kiểu thời gian.

## 6. Vì sao `BETWEEN` thường là bẫy khi lọc `TIMESTAMP`?

### 6.1. `DATE` và `TIMESTAMP` không giống nhau

- `DATE` biểu diễn **một ngày trên lịch**, không có giờ.
- `TIMESTAMP` biểu diễn **ngày và giờ**, có thể có phần giây nhỏ hơn giây.
- PostgreSQL phân biệt `TIMESTAMP WITHOUT TIME ZONE` với `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`), trong đó `TIMESTAMPTZ` biểu diễn một thời điểm và hiển thị theo múi giờ phiên.

Với cột `DATE`, câu hỏi “từ ngày 1/6 đến **hết ngày** 30/6” có thể dùng:

```sql
SELECT *
FROM daily_reports
WHERE report_date BETWEEN DATE '2026-06-01' AND DATE '2026-06-30';
```

Hai biên là các **ngày**, nên ngày 30/6 được tính đầy đủ vì cột không có phần giờ.

Nhưng nếu cột là `TIMESTAMP`, điều kiện này:

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at BETWEEN TIMESTAMP '2026-06-01 00:00:00'
                    AND TIMESTAMP '2026-06-30 00:00:00';
```

chỉ lấy đến **đúng thời điểm bắt đầu ngày 30/6**. Các đơn lúc `2026-06-30 10:00:00`, `2026-06-30 23:59:59` hoặc `2026-06-30 23:59:59.500000` đều bị loại.

Lý do: `TIMESTAMP '2026-06-30 00:00:00'` là **một thời điểm cụ thể**, không đại diện cho “mọi thời điểm trong ngày 30/6”.

### 6.2. Khoảng nửa mở: bắt đầu có, kết thúc không

Viết:

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND placed_at <  TIMESTAMP '2026-07-01 00:00:00'
ORDER BY placed_at, order_id;
```

Đây là khoảng `[2026-06-01 00:00:00, 2026-07-01 00:00:00)`. Nó lấy:

- Đơn ngay lúc **00:00:00 ngày 1/6** (biên đầu được bao gồm).
- Tất cả đơn từ sau đó cho đến **trước** 00:00:00 ngày 1/7.
- Không lấy đơn ngay lúc **00:00:00 ngày 1/7** (biên cuối bị loại).

Trong dữ liệu mẫu, kết quả là các đơn `102`, `103`, `104`, `105`. Đơn `101` xảy ra trước tháng 6; đơn `106` xảy ra đúng lúc bắt đầu tháng 7 nên nằm ngoài khoảng.

Biểu diễn bằng trục thời gian:

```text
Tháng 6:
2026-06-01 00:00:00                   2026-07-01 00:00:00
          ●=====================================○
          │        MỌI THỜI ĐIỂM THÁNG 6       │
          └ được lấy                           └ không được lấy
```

### 6.3. Không nên đoán “giây cuối cùng” của ngày

Một cách viết hay gặp:

```sql
-- Không nên dùng làm quy tắc chung:
WHERE placed_at BETWEEN TIMESTAMP '2026-06-01 00:00:00'
                    AND TIMESTAMP '2026-06-30 23:59:59'
```

Điều kiện trên bỏ sót các sự kiện có phần giây như `23:59:59.500000`. Nếu sửa thành `23:59:59.999`, một hệ lưu microsecond hoặc nanosecond vẫn có thể chứa những thời điểm muộn hơn giới hạn đó.

Không nên phụ thuộc vào độ chính xác hiện tại của cột hoặc vào thao tác “lấy ngày cuối cộng 23 giờ 59 phút ...”. **Biên đầu của khoảng kế tiếp** là mốc rõ ràng hơn:

```sql
WHERE placed_at >= :start_of_month
  AND placed_at <  :start_of_next_month
```

Cú pháp `:start_of_month` ở đây minh họa **tham số có tên** của một số framework/SQL client, không phải literal có thể gửi nguyên văn đến mọi hệ quản trị. Khi lập trình, ứng dụng bind hai tham số đúng kiểu theo API của driver.

## 7. Khoảng nửa mở giúp ghép các kỳ liên tiếp mà không đếm trùng

Xét việc chia dữ liệu theo tháng:

```text
Tháng 5: [2026-05-01, 2026-06-01)
Tháng 6: [2026-06-01, 2026-07-01)
Tháng 7: [2026-07-01, 2026-08-01)
```

Hai khoảng cạnh nhau **dùng chung một giá trị mốc**, nhưng mốc đó chỉ thuộc khoảng **bắt đầu tại nó**. Sự kiện đúng `2026-06-01 00:00:00` thuộc tháng 6, không thuộc tháng 5. Vì vậy, dữ liệu có thể phân hoạch theo tháng mà không bị đếm hai lần ở biên.

Nếu dùng khoảng đóng cho từng tháng:

```text
Tháng 5: [2026-05-01, 2026-06-01]
Tháng 6: [2026-06-01, 2026-07-01]
```

sự kiện đúng mốc 1/6 được đếm **ở cả hai tháng**. Với các báo cáo theo kỳ, biên trên loại trừ giải quyết vấn đề này một cách tự nhiên.

### 7.1. Truy vấn đếm theo từng ngày

Với dữ liệu thời gian một ngày, có thể tính:

```sql
SELECT COUNT(*) AS orders_on_june_1
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND placed_at <  TIMESTAMP '2026-06-02 00:00:00';
```

Trong dữ liệu mẫu, đơn `102` và `103` nằm trong ngày 1/6; kết quả là 2.

### 7.2. Truy vấn đếm theo từng tháng từ dữ liệu mẫu

```sql
SELECT
    COUNT(*) FILTER (
        WHERE placed_at >= TIMESTAMP '2026-05-01'
          AND placed_at <  TIMESTAMP '2026-06-01'
    ) AS may_count,
    COUNT(*) FILTER (
        WHERE placed_at >= TIMESTAMP '2026-06-01'
          AND placed_at <  TIMESTAMP '2026-07-01'
    ) AS june_count,
    COUNT(*) FILTER (
        WHERE placed_at >= TIMESTAMP '2026-07-01'
          AND placed_at <  TIMESTAMP '2026-08-01'
    ) AS july_count
FROM orders;
```

Kết quả dự kiến là `1`, `4`, `1`. Cú pháp `COUNT(*) FILTER (WHERE ...)` được PostgreSQL hỗ trợ và cũng có mặt trong SQL chuẩn hiện đại, nhưng không phải hệ quản trị nào cũng hỗ trợ giống nhau. Có thể thay bằng `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` nếu hệ đích không hỗ trợ `FILTER`.

### 7.3. Khoảng nửa mở không chỉ dành cho thời gian

Nhiều hệ thống chia phạm vi số thành các nhóm liên tiếp:

| Nhóm | Khoảng số |
|---|---|
| Dưới 100 | `value < 100` |
| Từ 100 đến dưới 200 | `value >= 100 AND value < 200` |
| Từ 200 đến dưới 500 | `value >= 200 AND value < 500` |
| Từ 500 trở lên | `value >= 500` |

Các nhóm này không chồng nhau, kể cả khi giá trị đúng bằng 100, 200 hoặc 500. Khi định nghĩa bảng phân loại giá, tuổi, điểm đo hay vùng dữ liệu, khoảng nửa mở giúp tránh phải thêm ngoại lệ cho từng ranh giới.

Tuy nhiên, cách viết trên là **quy tắc phân nhóm do nghiệp vụ chọn**. Ví dụ “điểm tối đa 100” trong bài thi có thể cần `[0,100]` vì 100 phải được bao gồm. Không có nguyên tắc nào buộc mọi bài toán phải dùng khoảng nửa mở.

## 8. Lọc `TIMESTAMPTZ`: xác định múi giờ của ngày nghiệp vụ

Khi cột là `TIMESTAMPTZ` trong PostgreSQL, câu “các giao dịch ngày 1/6” chưa đủ rõ nếu người dùng có thể ở nhiều múi giờ. Một thời điểm có thể thuộc ngày 1/6 ở Việt Nam nhưng vẫn thuộc 31/5 ở UTC.

### 8.1. Khoảng theo UTC

Nếu báo cáo được định nghĩa theo UTC, có thể viết rõ hai thời điểm:

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= TIMESTAMPTZ '2026-06-01 00:00:00+00'
  AND occurred_at <  TIMESTAMPTZ '2026-06-02 00:00:00+00';
```

Hai biên có độ lệch `+00` nên ngữ nghĩa độc lập với múi giờ hiển thị của phiên. Ví dụ giả định bảng `events(event_id, occurred_at TIMESTAMPTZ)` tồn tại.

### 8.2. Khoảng theo ngày lịch tại Việt Nam

Nếu báo cáo dựa theo ngày Việt Nam, dùng **từng mốc nửa đêm tại `Asia/Ho_Chi_Minh`**:

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-06-02 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

Trong PostgreSQL, `TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'` diễn giải giờ địa phương thành một thời điểm kiểu `TIMESTAMPTZ`. Câu truy vấn trên có cùng ý nghĩa dù phiên SQL đang dùng UTC hay múi giờ khác.

Một cách kiểm tra giờ tương đương cho ngày này:

```text
2026-06-01 00:00 tại Việt Nam = 2026-05-31 17:00 UTC
2026-06-02 00:00 tại Việt Nam = 2026-06-01 17:00 UTC
```

Không nên lấy mốc UTC đầu rồi **mặc định cộng 24 giờ** để suy ra mốc cuối cho mọi khu vực và mọi ngày: những khu vực có giờ mùa hè có thể có ngày địa phương dài 23 hoặc 25 giờ. Hãy chuyển đổi **riêng từng mốc ngày địa phương** theo múi giờ nghiệp vụ như ví dụ ở trên.

### 8.3. Vì sao không chỉ `CAST(occurred_at AS DATE)`?

Truy vấn:

```sql
-- PostgreSQL: ngày suy ra phụ thuộc TimeZone của phiên.
SELECT event_id
FROM events
WHERE CAST(occurred_at AS DATE) = DATE '2026-06-01';
```

có thể trả kết quả khác nếu thay đổi `SET TIME ZONE`, bởi việc chuyển `TIMESTAMPTZ` sang `DATE` trước tiên xét ngày theo múi giờ phiên.

Nếu mục tiêu là **ngày tại Việt Nam**, điều kiện phải thể hiện khu vực đó:

```sql
SELECT event_id
FROM events
WHERE CAST(occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh' AS DATE)
      = DATE '2026-06-01';
```

Truy vấn trên rõ ý nghĩa nhưng đặt biểu thức tính trên cột. Khi lọc tập dữ liệu lớn bằng chỉ mục thông thường trên `occurred_at`, hai điều kiện biên với `>=` và `<` thường dễ tận dụng chỉ mục hơn. Phần sau giải thích.

## 9. Tác động đến chỉ mục và hiệu năng

Một điểm thực hành tốt: **làm rõ ranh giới của khoảng và giữ cột ở đúng kiểu gốc khi có thể**.

Giả sử bảng `orders` có chỉ mục B-tree trên cột `placed_at TIMESTAMP`:

```sql
CREATE INDEX idx_orders_placed_at ON orders(placed_at);
```

Hai điều kiện này có thể được bộ tối ưu xử lý khác nhau:

```sql
-- Cách 1: chuyển kiểu từng giá trị cột trước khi so sánh.
SELECT order_id
FROM orders
WHERE CAST(placed_at AS DATE) = DATE '2026-06-01';
```

```sql
-- Cách 2: dùng khoảng nửa mở với chính kiểu TIMESTAMP của cột.
SELECT order_id
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-01'
  AND placed_at <  TIMESTAMP '2026-06-02';
```

Trong nhiều trường hợp, cách thứ hai giúp chỉ mục B-tree trên `placed_at` hỗ trợ việc xác định phạm vi tìm kiếm trực tiếp hơn. Cách thứ nhất có thể cần chỉ mục trên biểu thức `CAST(placed_at AS DATE)` hoặc cơ chế tối ưu riêng; điều này tùy hệ quản trị.

`BETWEEN` trên một cột số đã có kiểu đúng cũng thường cho bộ tối ưu thấy được điều kiện biên:

```sql
SELECT order_id
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000;
```

Không nên kết luận “`BETWEEN` luôn nhanh hơn hai phép so sánh” hoặc “khoảng nửa mở luôn nhanh hơn `BETWEEN`”. **Khác biệt cốt lõi là ngữ nghĩa biên**, còn hiệu năng phụ thuộc kiểu cột, chỉ mục, phân bố dữ liệu, thống kê và kế hoạch thực thi. Khi tối ưu một truy vấn thực, hãy xem `EXPLAIN` hoặc công cụ tương đương.

### 9.1. Tránh chuyển cột sang văn bản để lọc ngày

Ví dụ PostgreSQL:

```sql
-- Thường không phù hợp làm điều kiện lọc trong hệ thống lớn:
SELECT order_id
FROM orders
WHERE TO_CHAR(placed_at, 'YYYY-MM-DD') = '2026-06-01';
```

`TO_CHAR` trả **chuỗi đã định dạng**, khiến phép so sánh trở thành so sánh văn bản trên giá trị tính từ mỗi dòng. Nếu có thể, nên lọc trực tiếp cột thời gian theo hai mốc đúng kiểu; để định dạng ngày dành cho đầu ra hoặc tầng hiển thị.

## 10. Bộ tham số lọc: kiểm soát giá trị đầu vào

Ứng dụng thường cho người dùng chọn **Từ ngày** và **Đến ngày**. Hai nhãn này dễ gây mơ hồ nếu cột lưu cả giờ.

Hãy quy định rõ hợp đồng:

1. Người dùng chọn **ngày lịch**, ví dụ bắt đầu `2026-06-01` và kết thúc `2026-06-30`, và “đến ngày” **bao gồm cả ngày đó**.
2. Ứng dụng đổi chúng thành **thời điểm đầu ngày bắt đầu** và **thời điểm đầu ngày sau ngày kết thúc**, theo múi giờ nghiệp vụ.
3. Truy vấn thực thi điều kiện `event_at >= start_instant AND event_at < end_exclusive_instant`.

```text
Input hiển thị:
  Từ ngày: 2026-06-01    Đến hết ngày: 2026-06-30
               │
               ▼
Khoảng để truy vấn:
  start_inclusive = 2026-06-01 00:00 theo múi giờ nghiệp vụ
  end_exclusive   = 2026-07-01 00:00 theo múi giờ nghiệp vụ
               │
               ▼
SQL: event_at >= start_inclusive AND event_at < end_exclusive
```

Nếu ứng dụng đã nhận **hai thời điểm chính xác** (không phải hai ngày lịch) thì không tự động cộng một ngày cho biên cuối; phải hỏi/định nghĩa rõ biên cuối **bao gồm** hay **loại trừ** ngay trong hợp đồng API.

### 10.1. Kiểm tra đầu vào

- Nếu biên dưới lớn hơn biên trên, thống nhất trả lỗi đầu vào hoặc chuẩn hóa có chủ đích; đừng âm thầm trả báo cáo rỗng khiến người dùng tưởng không có dữ liệu.
- Với khoảng nửa mở, `start = end` là **khoảng rỗng**, thường hợp lý với bộ lọc khoảng thời điểm.
- Nếu một biên được bỏ trống, quy định rõ có nghĩa là **không giới hạn bên đó** hay là lỗi. Không nên đưa `NULL` trực tiếp vào `BETWEEN` rồi mong nó có nghĩa “mọi giá trị”.
- Bind tham số đúng kiểu bằng driver hoặc thư viện truy cập dữ liệu; tránh ghép chuỗi SQL với giá trị người dùng nhập.
- Hiểu đơn vị của giá trị: 100.000 đồng khác 100.000 xu; khoảng “từ 1 đến 2” theo số nguyên khác khoảng trên số thập phân.

### 10.2. Các biên tùy chọn

Khi cần lọc một phía, viết đúng điều kiện một phía:

```sql
-- Chỉ có biên dưới:
SELECT order_id
FROM orders
WHERE total_amount >= 100000;

-- Chỉ có biên trên loại trừ:
SELECT order_id
FROM orders
WHERE total_amount < 200000;
```

Trong truy vấn dùng tham số tùy chọn, có thể gặp:

```sql
-- Ví dụ ý tưởng với placeholder theo framework:
WHERE (:min_amount IS NULL OR total_amount >= :min_amount)
  AND (:max_amount IS NULL OR total_amount < :max_amount)
```

Biểu thức này phù hợp khi `NULL` của **tham số** được quy ước nghĩa là “không đặt giới hạn”. Nó không có nghĩa `total_amount NULL` đương nhiên thỏa mọi khoảng; với cả hai biên được bỏ trống, biểu thức trên có thể giữ dòng `NULL`, còn với một biên có giá trị, phép so sánh với `NULL` vẫn không là `TRUE`. Nếu nghiệp vụ cần quy tắc riêng cho dòng thiếu số tiền, phải thêm điều kiện cho cột.

Tùy hệ quản trị và số lượng tham số, việc dùng `OR :param IS NULL` cũng có thể ảnh hưởng đến kế hoạch thực thi; có thể tạo câu SQL tương ứng với bộ lọc đã chọn bằng truy vấn tham số hóa của ứng dụng.

## 11. Ví dụ tổng hợp: lọc đúng khoảng tiền và thời gian

Yêu cầu: “Lấy những đơn `PAID`, có số tiền **từ 100.000 đến dưới 200.000 đồng**, được đặt **trong tháng 6/2026** theo cột `TIMESTAMP` không kèm múi giờ.”

Trước khi viết SQL, tách ý nghĩa thành ba điều kiện:

- `status = 'PAID'`.
- `total_amount >= 100000 AND total_amount < 200000`: biên dưới bao gồm, biên trên loại trừ.
- `placed_at >= '2026-06-01 00:00:00' AND placed_at < '2026-07-01 00:00:00'`: cả tháng 6, không lấy thời điểm bắt đầu tháng 7.

```sql
SELECT
    order_id,
    total_amount,
    placed_at,
    status
FROM orders
WHERE status = 'PAID'
  AND total_amount >= 100000
  AND total_amount < 200000
  AND placed_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND placed_at <  TIMESTAMP '2026-07-01 00:00:00'
ORDER BY placed_at, order_id;
```

Với bảng mẫu, kết quả là đơn `102` và `103`. Đơn `106` tuy có tiền `180000.00` và trạng thái `PAID` nhưng thuộc tháng 7; đơn `104` có giá `200000.00` và trạng thái `PENDING`; đơn `105` vượt biên trên giá; đơn `101` thấp hơn biên dưới.

Chỉ cần đổi một từ trong đề bài, cách viết có thể thay đổi. Nếu yêu cầu trở thành “từ 100.000 đến **bằng** 200.000”, đoạn lọc tiền phải là:

```sql
AND total_amount BETWEEN 100000 AND 200000
```

Nhưng hai điều kiện lọc thời gian theo tháng 6 vẫn nên là khoảng nửa mở để bao phủ đúng toàn bộ tháng mà không trùng biên tháng 7.

## 12. Các lỗi thường gặp

| Cách viết hoặc cách nghĩ | Rủi ro | Cách diễn đạt đúng |
|---|---|---|
| Nghĩ `BETWEEN a AND b` chỉ lấy giá trị ở giữa, không lấy `a`/`b` | Sai tại hai biên | Nhớ tương đương `>= a AND <= b` |
| `BETWEEN '2026-06-01' AND '2026-06-30'` với cột `TIMESTAMP` | Bỏ gần hết ngày 30/6 nếu biên trên được diễn giải là đầu ngày | Lấy `>= 01/06 00:00` và `< 01/07 00:00` |
| Kết thúc ngày bằng `23:59:59` | Bỏ sót mili/microsecond cuối ngày | Dùng đầu ngày kế tiếp làm biên loại trừ |
| Dùng `[ngày A, ngày B]` cho hai kỳ liền kề | Cùng một thời điểm biên được tính hai lần | Dùng `[A,B)` và `[B,C)` |
| Viết `BETWEEN 200 AND 100` | Khoảng ngược, thường không có giá trị thỏa | Kiểm tra biên; chuẩn hóa khi nghiệp vụ cho phép |
| Dùng `NOT BETWEEN` để lấy luôn `NULL` | Điều kiện với `NULL` có thể `UNKNOWN` | Thêm `IS NULL` nếu nghiệp vụ yêu cầu |
| Dùng `BETWEEN` với chuỗi số | So sánh chuỗi theo collation, không theo số | Lưu/cast dữ liệu đúng kiểu sau kiểm tra |
| `CAST(timestamp_col AS DATE)` cho mọi báo cáo lớn | Phụ thuộc múi giờ nếu là `TIMESTAMPTZ`; có thể khó dùng chỉ mục thường | Xác định múi giờ và lọc bằng hai mốc đúng kiểu |
| Dùng `BETWEEN` mọi lúc vì trông ngắn | Vô tình lấy biên cuối cần loại trừ | Chọn cú pháp dựa trên hợp đồng biên |
| Nghĩ `ORDER BY` tự xuất hiện khi lọc theo khoảng | SQL không bảo đảm thứ tự không được yêu cầu | Viết `ORDER BY` khi cần thứ tự ổn định |

## 13. Thực hành với PostgreSQL

Đoạn script sau tạo bảng **tạm** với dữ liệu mẫu của bài. Chạy trên database thử nghiệm có quyền tạo bảng tạm. Bảng tự biến mất khi phiên kết thúc.

```sql
CREATE TEMP TABLE orders (
    order_id INTEGER PRIMARY KEY,
    total_amount NUMERIC(12, 2) NOT NULL,
    placed_at TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO orders (order_id, total_amount, placed_at, status) VALUES
    (101,  99999.99, TIMESTAMP '2026-05-31 23:59:59',        'PAID'),
    (102, 100000.00, TIMESTAMP '2026-06-01 00:00:00',        'PAID'),
    (103, 150000.00, TIMESTAMP '2026-06-01 09:15:00',        'PAID'),
    (104, 200000.00, TIMESTAMP '2026-06-15 12:30:00',        'PENDING'),
    (105, 200000.01, TIMESTAMP '2026-06-30 23:59:59.500000', 'PAID'),
    (106, 180000.00, TIMESTAMP '2026-07-01 00:00:00',        'PAID');

-- Mọi đơn trong khoảng tiền đóng.
SELECT order_id, total_amount
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000
ORDER BY order_id;

-- Mọi đơn trong tháng 6 theo khoảng thời gian nửa mở.
SELECT order_id, placed_at
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-01 00:00:00'
  AND placed_at <  TIMESTAMP '2026-07-01 00:00:00'
ORDER BY placed_at, order_id;

-- Kiểm tra sự khác biệt ở biên tháng.
SELECT
    order_id,
    placed_at,
    placed_at BETWEEN TIMESTAMP '2026-06-01 00:00:00'
                  AND TIMESTAMP '2026-06-30 00:00:00' AS between_midnights,
    (
        placed_at >= TIMESTAMP '2026-06-01 00:00:00'
        AND placed_at < TIMESTAMP '2026-07-01 00:00:00'
    ) AS full_june
FROM orders
ORDER BY order_id;
```

Nếu dùng một bảng `orders` có sẵn trong môi trường của bạn, tên bảng tạm trùng tên có thể che bảng thật trong phiên PostgreSQL. Nên dùng một kết nối thực hành riêng hoặc đặt tên `range_lab_orders` và thay tương ứng trong truy vấn. Không cần chạy thao tác thay đổi bảng thật của dự án để hiểu bài này.

## 14. Bài tập tự luyện

Hãy dùng bảng mẫu ở mục 13. Trước mỗi câu truy vấn, xác định **biên nào bao gồm và biên nào loại trừ**.

### Bài 1 — Khoảng đóng

Lấy đơn có tổng tiền **từ 100.000 đến 200.000, bao gồm cả hai mức**, không xét trạng thái hoặc ngày đặt. Dự đoán danh sách mã đơn.

### Bài 2 — Khoảng nửa mở theo tiền

Lấy các đơn có `total_amount` thuộc `[100000, 200000)`. So sánh số đơn với bài 1 và giải thích vì sao đơn ở biên trên khác nhau.

### Bài 3 — Hai ngày liên tiếp

Viết truy vấn lấy đơn trong **ngày 1/6/2026** bằng cặp điều kiện `>=` và `<`. Viết truy vấn tương tự cho **ngày 2/6/2026**. Hai khoảng có giao nhau tại mốc 00:00 ngày 2/6 không?

### Bài 4 — Phát hiện lỗi ở cuối tháng

Xét điều kiện:

```sql
WHERE placed_at BETWEEN TIMESTAMP '2026-06-01'
                    AND TIMESTAMP '2026-06-30 23:59:59'
```

Trong dữ liệu mẫu, đơn nào thuộc tháng 6 mà điều kiện này bỏ sót? Viết lại cho đúng mà không cần đoán độ chính xác của phần giây.

### Bài 5 — `NOT BETWEEN` và giá trị thiếu

Nếu `total_amount` có thể là `NULL`, câu `WHERE total_amount NOT BETWEEN 100000 AND 200000` có tự lấy những dòng có `NULL` không? Nếu muốn lấy dòng bên ngoài khoảng **và** dòng thiếu số tiền thì phải viết sao?

### Bài 6 — Khoảng tại Việt Nam với `TIMESTAMPTZ`

Giả sử có `events(event_id, occurred_at TIMESTAMPTZ)`. Viết truy vấn cho sự kiện diễn ra trong ngày `2026-06-01` theo lịch tại `Asia/Ho_Chi_Minh`, độc lập với `TimeZone` của session SQL. Giải thích vì sao chuyển đổi hai mốc địa phương thành hai thời điểm phù hợp hơn cast mọi giá trị `occurred_at` thành `DATE` nếu muốn sử dụng chỉ mục trên cột.

### Bài 7 — Ranh giới nhóm giá

Định nghĩa ba nhóm giá không chồng nhau: **dưới 100.000**, **từ 100.000 đến dưới 200.000**, **từ 200.000 trở lên**. Viết truy vấn dùng `CASE` để gắn nhãn nhóm giá cho từng đơn, rồi dự đoán nhóm của đơn `102` và `104`.

<details>
<summary>Gợi ý đáp án và cách lập luận</summary>

**Bài 1:** `102`, `103`, `104`, `106`.

```sql
SELECT order_id
FROM orders
WHERE total_amount BETWEEN 100000 AND 200000
ORDER BY order_id;
```

**Bài 2:** `102`, `103`, `106`; đơn `104` bằng `200000.00` nên bị loại khi dùng `< 200000`.

```sql
SELECT order_id
FROM orders
WHERE total_amount >= 100000
  AND total_amount < 200000
ORDER BY order_id;
```

**Bài 3:** Ngày 1/6:

```sql
SELECT order_id
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-01'
  AND placed_at <  TIMESTAMP '2026-06-02';
```

Ngày 2/6:

```sql
SELECT order_id
FROM orders
WHERE placed_at >= TIMESTAMP '2026-06-02'
  AND placed_at <  TIMESTAMP '2026-06-03';
```

Mốc đúng 00:00 ngày 2/6 **không thuộc** ngày 1/6, nhưng **thuộc** ngày 2/6. Hai khoảng không giao nhau.

**Bài 4:** Đơn `105` tại `2026-06-30 23:59:59.500000` bị bỏ sót. Sửa thành:

```sql
WHERE placed_at >= TIMESTAMP '2026-06-01'
  AND placed_at <  TIMESTAMP '2026-07-01'
```

**Bài 5:** Không; điều kiện với số tiền `NULL` thường là `UNKNOWN`, nên `WHERE` không giữ. Nếu muốn lấy cả dòng thiếu:

```sql
WHERE total_amount NOT BETWEEN 100000 AND 200000
   OR total_amount IS NULL
```

**Bài 6:**

```sql
SELECT event_id, occurred_at
FROM events
WHERE occurred_at >= (
    TIMESTAMP '2026-06-01 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-06-02 00:00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
```

Mỗi mốc địa phương được chuyển sang thời điểm độc lập với múi giờ phiên; điều kiện so sánh trực tiếp trên `occurred_at` thuận lợi hơn cho chỉ mục B-tree thông thường.

**Bài 7:**

```sql
SELECT
    order_id,
    total_amount,
    CASE
        WHEN total_amount < 100000 THEN 'below_100k'
        WHEN total_amount < 200000 THEN '100k_to_under_200k'
        ELSE '200k_or_more'
    END AS price_group
FROM orders
ORDER BY order_id;
```

Vì các nhánh `CASE` được xét theo thứ tự, đơn `102` (`100000`) thuộc `100k_to_under_200k`; đơn `104` (`200000`) thuộc `200k_or_more`. Nếu cột có thể `NULL`, cần thêm nhánh `WHEN total_amount IS NULL` trước các nhánh số, vì `NULL` không tự thuộc nhóm “200k trở lên”.

</details>

## 15. Checklist tư duy khi dùng khoảng trong SQL

Trước khi viết `BETWEEN` hoặc một cặp phép so sánh, hãy tự hỏi:

1. **Kiểu dữ liệu là gì?** `INTEGER`, `NUMERIC`, `DATE`, `TIMESTAMP`, `TIMESTAMPTZ` hay chuỗi?
2. **Đề bài có thật sự bao gồm cả hai biên không?** Nếu có, `BETWEEN` là một cách viết rõ ràng.
3. **Biên cuối có cần loại trừ không?** Với các kỳ thời gian và các nhóm kế tiếp, cân nhắc `[start, end)`.
4. **“Đến hết ngày” là một ngày lịch hay một thời điểm cụ thể?** Với `TIMESTAMP`, dùng thời điểm bắt đầu ngày kế tiếp làm biên loại trừ.
5. **Nếu là `TIMESTAMPTZ`, ngày được tính theo múi giờ nào?** Nên nêu vùng nghiệp vụ rõ ràng và xây hai thời điểm biên phù hợp.
6. **Nếu có `NULL`, hai biên ngược nhau hoặc tham số bỏ trống, kết quả có đúng mong đợi không?** Phải có quy tắc đầu vào riêng.
7. **Có cần dùng chỉ mục và thứ tự hiển thị không?** Lọc bằng kiểu cột phù hợp; viết `ORDER BY` nếu thứ tự kết quả quan trọng.

`BETWEEN` không có vấn đề gì khi **khoảng đóng** là điều bạn thực sự muốn. Lỗi thường xuất phát từ việc người viết nghĩ “kết thúc ngày” là một giá trị thời gian duy nhất hoặc quên rằng `BETWEEN` lấy **cả biên trên**. Dùng khoảng nửa mở đúng chỗ giúp các bộ lọc thời gian và các nhóm dữ liệu liên tiếp có ranh giới rõ ràng, không bỏ sót giá trị ở cuối kỳ và không đếm trùng tại điểm chuyển kỳ.
