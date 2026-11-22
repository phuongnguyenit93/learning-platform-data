# first_value, last_value, nth_value và ảnh hưởng của khung trong PostgreSQL

## 1. Vấn đề: “đầu tiên”, “cuối cùng” và “thứ n” là theo phạm vi nào?

Giả sử bảng bán hàng có các giao dịch của từng nhóm kinh doanh. Một báo cáo cần hiển thị, trên **mỗi dòng giao dịch**:

- Tên người thực hiện **giao dịch đầu tiên** của nhóm.
- Tên người thực hiện **giao dịch cuối cùng** của nhóm.
- Tên người thực hiện **giao dịch thứ hai** của nhóm.
- Giá trị của giao dịch **đầu tiên trong ba giao dịch gần nhất**, tính đến dòng hiện tại.

PostgreSQL có ba hàm cửa sổ phù hợp:

- `first_value(expression)`: lấy giá trị ở **hàng đầu tiên trong khung cửa sổ**.
- `last_value(expression)`: lấy giá trị ở **hàng cuối cùng trong khung cửa sổ**.
- `nth_value(expression, n)`: lấy giá trị ở **hàng thứ n, tính từ đầu khung cửa sổ**, với `n` là số thứ tự dương.

Những hàm này không đơn giản là lấy đầu, cuối hoặc thứ n **của toàn bảng**. Chúng hoạt động trong ngữ cảnh của một **window** gồm phân vùng, thứ tự và đặc biệt là **frame**.

Ví dụ:

```sql
SELECT
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_seller
FROM window_lab.sales;
```

Người mới học có thể kỳ vọng mọi dòng của mỗi nhóm đều hiển thị người bán ở giao dịch **cuối cùng trong nhóm**. Nhưng với thứ tự `ORDER BY` và khung mặc định của PostgreSQL, kết quả `last_value` thường chính là **người bán của dòng hiện tại** (khi thứ tự là duy nhất).

Muốn lấy cuối **toàn phân vùng**, cần chỉ định khung:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

**Điểm then chốt của bài:** tên hàm `first_value`, `last_value` và `nth_value` mô tả vị trí **bên trong frame**, không tự quy định frame đó trải dài đến đâu. Nếu không hiểu frame mặc định, bạn có thể viết SQL hợp lệ nhưng nhận kết quả không đúng nghiệp vụ.

## 2. Mục tiêu bài học

Sau khi học, bạn có thể:

1. Phân biệt `PARTITION BY`, `ORDER BY` và **window frame**.
2. Dùng `first_value`, `last_value`, `nth_value` với dữ liệu thực tế.
3. Giải thích mặc định `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` khi window có `ORDER BY`.
4. Hiểu **peer rows**: những hàng bằng nhau trên toàn bộ khóa `ORDER BY` của window.
5. Sử dụng `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` để lấy giá trị đầu/cuối của **toàn phân vùng**.
6. Sử dụng khung trượt như `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
7. Phân biệt `ROWS`, `RANGE` và `GROUPS` khi có nhiều hàng cùng khóa sắp xếp.
8. Xử lý `NULL`, thiếu hàng thứ n và thứ tự không xác định.
9. Nhận biết khi nên dùng `LAG`/`LEAD`, `ROW_NUMBER`, `DISTINCT ON` hoặc truy vấn con thay cho một hàm giá trị khung.
10. Viết báo cáo có kết quả ổn định, đúng phạm vi và không nhân hàng ngoài ý muốn.

## 3. Tạo dữ liệu PostgreSQL để thực hành

Bài dùng schema `window_lab` trong một database thử nghiệm, không động đến bảng nghiệp vụ thật.

### 3.1. Tạo bảng giao dịch

```sql
CREATE SCHEMA IF NOT EXISTS window_lab;

CREATE TABLE window_lab.sales (
    sale_id bigint PRIMARY KEY,
    team text NOT NULL,
    seller text NOT NULL,
    sold_on date NOT NULL,
    revenue numeric(12,2)
);
```

Trong ví dụ:

- `sale_id` là mã giao dịch duy nhất, dùng làm tiêu chí phá hòa khi nhiều giao dịch cùng ngày.
- `team` xác định nhóm.
- `seller` là giá trị text muốn lấy bằng window functions.
- `sold_on` là ngày phát sinh.
- `revenue` cho phép NULL để minh họa sự khác nhau giữa **không có giá trị** và **không có hàng**.

### 3.2. Nạp dữ liệu có chủ đích

```sql
INSERT INTO window_lab.sales
    (sale_id, team, seller, sold_on, revenue)
VALUES
    (1,  'North', 'An',    DATE '2026-01-03', 100.00),
    (2,  'North', 'Bình',  DATE '2026-01-05', 180.00),
    (3,  'North', 'Chi',   DATE '2026-01-05', NULL),
    (4,  'North', 'Dung',  DATE '2026-01-09',  90.00),
    (5,  'North', 'Em',    DATE '2026-01-12', 140.00),
    (6,  'South', 'Giang', DATE '2026-01-02', 200.00),
    (7,  'South', 'Hà',    DATE '2026-01-06', 120.00),
    (8,  'South', 'Huy',   DATE '2026-01-07', 120.00),
    (9,  'South', 'Khánh', DATE '2026-01-10', 300.00),
    (10, 'East',  'Lan',   DATE '2026-01-08', 250.00);
```

Bảng đã có **ba nhóm**:

| team | sale_id | seller | sold_on | revenue |
| --- | ---: | --- | --- | ---: |
| North | 1 | An | 2026-01-03 | 100.00 |
| North | 2 | Bình | 2026-01-05 | 180.00 |
| North | 3 | Chi | 2026-01-05 | NULL |
| North | 4 | Dung | 2026-01-09 | 90.00 |
| North | 5 | Em | 2026-01-12 | 140.00 |
| South | 6 | Giang | 2026-01-02 | 200.00 |
| South | 7 | Hà | 2026-01-06 | 120.00 |
| South | 8 | Huy | 2026-01-07 | 120.00 |
| South | 9 | Khánh | 2026-01-10 | 300.00 |
| East | 10 | Lan | 2026-01-08 | 250.00 |

Ta cố ý tạo:

1. Nhóm **North** có hai giao dịch cùng ngày `2026-01-05` (mã 2 và 3).
2. Một giao dịch có `revenue = NULL` (mã 3).
3. Nhóm **East** chỉ có **một giao dịch** (rất quan trọng cho `nth_value(..., 2)`).
4. Các nhóm có kích thước khác nhau.

Có thể xem dữ liệu theo thứ tự xác định:

```sql
SELECT sale_id, team, seller, sold_on, revenue
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Lưu ý:** nếu chạy lại `INSERT` trên dữ liệu đã nạp, PostgreSQL sẽ báo trùng khóa chính. Dùng một database/schema thực hành mới hoặc quản lý nạp lại có chủ đích.

## 4. Ôn lại `OVER`: phân vùng, thứ tự và khung

Window function sử dụng mệnh đề `OVER`:

```sql
function_name(...) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ... AND ...
)
```

Ba khái niệm ở đây **khác nhau**:

| Thành phần | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `PARTITION BY` | Chia hàng thành những phân vùng độc lập | Mỗi `team` |
| `ORDER BY` bên trong `OVER` | Sắp thứ tự logic các hàng trong phân vùng | Ngày giao dịch, rồi ID |
| **Frame** | Chọn những hàng, trong phân vùng và theo thứ tự đã chọn, nằm trong phạm vi hàm được phép nhìn thấy | Từ đầu nhóm đến hiện tại, hoặc toàn nhóm |

Một sơ đồ:

```text
Tất cả giao dịch
       |
       | PARTITION BY team
       v
+--------------------+------------------+-------------+
| North              | South            | East        |
| 1, 2, 3, 4, 5      | 6, 7, 8, 9       | 10          |
+--------------------+------------------+-------------+
       |
       | ORDER BY sold_on, sale_id
       v
Thứ tự ổn định bên trong từng nhóm
       |
       | ROWS BETWEEN ...
       v
Frame tương ứng với mỗi hàng hiện tại
       |
       v
first_value / last_value / nth_value
```

### 4.1. `PARTITION BY` không giống `GROUP BY`

`GROUP BY` thường **gộp** nhiều hàng thành một hàng tổng hợp cho mỗi nhóm.

```sql
SELECT team, COUNT(*) AS sales_count
FROM window_lab.sales
GROUP BY team
ORDER BY team;
```

Kết quả gồm ba hàng: East 1, North 5, South 4.

Ngược lại:

```sql
SELECT
    sale_id,
    team,
    seller,
    COUNT(*) OVER (PARTITION BY team) AS team_sales_count
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

kết quả **vẫn có 10 hàng**, nhưng mỗi hàng được bổ sung số giao dịch trong nhóm.

Các hàm `first_value`, `last_value`, `nth_value` cũng thường giữ nguyên từng hàng đầu vào và thêm giá trị được tính theo cửa sổ.

### 4.2. `ORDER BY` trong `OVER` không sắp xếp kết quả trả về

```sql
SELECT
    sale_id,
    team,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales;
```

Thứ tự `ORDER BY sold_on, sale_id` ở **trong `OVER`** là thứ tự dùng để tính window. Nó **không đảm bảo thứ tự các hàng được trả ra**.

Muốn kết quả dễ đọc và ổn định:

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Câu `ORDER BY` ở **cuối SELECT** mới quy định thứ tự kết quả hiển thị.

## 5. `first_value`: giá trị ở đầu frame

Cú pháp:

```sql
first_value(expression) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

Hàm trả về giá trị của `expression` tại **hàng đầu tiên trong frame hiện tại**, với kiểu dữ liệu tương ứng của expression.

### 5.1. Người bán đầu tiên của từng nhóm

```sql
SELECT
    team,
    sale_id,
    seller,
    sold_on,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Kết quả khái quát:

| team | sale_id | seller | first_seller |
| --- | ---: | --- | --- |
| East | 10 | Lan | Lan |
| North | 1 | An | An |
| North | 2 | Bình | An |
| North | 3 | Chi | An |
| North | 4 | Dung | An |
| North | 5 | Em | An |
| South | 6 | Giang | Giang |
| South | 7 | Hà | Giang |
| South | 8 | Huy | Giang |
| South | 9 | Khánh | Giang |

Vì frame mặc định bắt đầu từ **đầu phân vùng**, `first_value` ở đây cho cùng một người trên mọi hàng của nhóm.

Tuy nhiên, kết luận đó chỉ đúng với **frame đang dùng**. Nếu giới hạn frame thành ba giao dịch gần nhất, “hàng đầu frame” sẽ trượt theo dòng hiện tại.

### 5.2. Đầu tiên không nhất thiết là giá trị nhỏ nhất

```sql
SELECT
    sale_id,
    seller,
    revenue,
    first_value(revenue) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_revenue,
    MIN(revenue) OVER (
        PARTITION BY team
    ) AS smallest_nonnull_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Ở North:

- `first_revenue` là **100.00**: doanh thu ở **giao dịch đầu tiên theo thời gian**.
- `smallest_nonnull_revenue` là **90.00**: giá trị tiền nhỏ nhất, bỏ qua NULL theo quy tắc `MIN`.

Do đó:

- `first_value(revenue ORDER BY sold_on)` có ý nghĩa **vị trí theo thời gian**.
- `MIN(revenue)` có ý nghĩa **giá trị số nhỏ nhất**.

Không được thay `first_value` bằng `MIN` chỉ vì cả hai có chữ “first/minimum”.

### 5.3. Đầu tiên theo tiêu chí nào?

Nếu muốn người bán có doanh thu lớn nhất:

```sql
SELECT
    team,
    sale_id,
    seller,
    revenue,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY revenue DESC NULLS LAST, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS seller_with_highest_revenue
FROM window_lab.sales
ORDER BY team, sale_id;
```

Lúc này **“đầu tiên” là hàng đứng đầu khi sắp theo doanh thu giảm dần**, không phải người bán sớm nhất theo ngày.

Với North, người có doanh thu lớn nhất là **Bình (180.00)**, không phải An. Dùng `NULLS LAST` để doanh thu NULL không vô tình đứng trước các giá trị số khi sắp giảm dần.

## 6. `last_value`: hàm dễ bị hiểu nhầm nhất

Cú pháp:

```sql
last_value(expression) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

Hàm lấy giá trị tại **hàng cuối cùng của frame**.

### 6.1. Ví dụ tưởng lấy cuối nhóm nhưng thực ra lấy cuối frame mặc định

```sql
SELECT
    sale_id,
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_seller_default
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | last_seller_default |
| ---: | --- | --- |
| 1 | An | An |
| 2 | Bình | Bình |
| 3 | Chi | Chi |
| 4 | Dung | Dung |
| 5 | Em | Em |

Tại sao người bán cuối nhóm **Em** không lặp trên cả năm hàng?

Vì khi window có `ORDER BY` và không chỉ định frame, PostgreSQL mặc định dùng một frame chạy từ **đầu phân vùng đến hàng hiện tại và những peer row tương ứng**. Với `ORDER BY sold_on, sale_id`, cặp khóa là duy nhất, nên mỗi hàng là peer duy nhất của nó.

Với hàng mã 2, frame đang là:

```text
North theo (sold_on, sale_id)

[An, Bình] | Chi, Dung, Em
 ^-------^
 frame của hàng Bình

last_value(seller) = 'Bình'
```

Hàm không nhìn thấy Dung hay Em vì họ nằm **sau frame hiện tại**.

### 6.2. Đúng: mở rộng frame đến cuối phân vùng

```sql
SELECT
    sale_id,
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller_in_team
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | last_seller_in_team |
| ---: | --- | --- |
| 1 | An | Em |
| 2 | Bình | Em |
| 3 | Chi | Em |
| 4 | Dung | Em |
| 5 | Em | Em |

Cụm:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
```

mở rộng frame đến **đầu và cuối toàn phân vùng**, bất kể đang tính cho hàng nào.

Đây là mẫu quan trọng nhất khi yêu cầu nghiệp vụ là **giá trị cuối cùng của toàn nhóm**.

### 6.3. So trực tiếp kết quả mặc định và full frame

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_in_running_frame,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_in_partition
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Với nhóm South:

| sale_id | seller | last_in_running_frame | last_in_partition |
| ---: | --- | --- | --- |
| 6 | Giang | Giang | Khánh |
| 7 | Hà | Hà | Khánh |
| 8 | Huy | Huy | Khánh |
| 9 | Khánh | Khánh | Khánh |

Truy vấn không sai cú pháp trong cả hai trường hợp; khác biệt nằm ở **frame**, nên bài toán nghiệp vụ phải xác định trước **“cuối của gì?”**.

## 7. `nth_value`: giá trị ở vị trí n trong frame

Cú pháp:

```sql
nth_value(expression, n) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

Trong PostgreSQL, `n` được hiểu theo thứ tự **bắt đầu từ 1**, không phải chỉ số mảng từ 0.

- `nth_value(value, 1)`: giá trị của hàng thứ nhất trong frame.
- `nth_value(value, 2)`: giá trị của hàng thứ hai.
- `nth_value(value, 3)`: giá trị của hàng thứ ba.

`n` phải là số nguyên dương hợp lệ theo cú pháp/hàm. Nếu frame có **ít hơn n hàng**, hàm trả **NULL**.

### 7.1. Giao dịch thứ hai của mỗi nhóm

```sql
SELECT
    team,
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Kết quả:

| team | sale_id | seller | second_seller |
| --- | ---: | --- | --- |
| East | 10 | Lan | NULL |
| North | 1 | An | Bình |
| North | 2 | Bình | Bình |
| North | 3 | Chi | Bình |
| North | 4 | Dung | Bình |
| North | 5 | Em | Bình |
| South | 6 | Giang | Hà |
| South | 7 | Hà | Hà |
| South | 8 | Huy | Hà |
| South | 9 | Khánh | Hà |

Nhóm East chỉ có một hàng nên **không tồn tại hàng thứ hai**; kết quả NULL là đúng.

### 7.2. Khi không chỉ định frame: thứ hai có thể chưa “xuất hiện”

```sql
SELECT
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS second_in_running_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | second_in_running_frame |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | Bình |
| 3 | Chi | Bình |
| 4 | Dung | Bình |
| 5 | Em | Bình |

Ở hàng đầu tiên, frame mặc định mới có **một hàng**, nên chưa có giá trị thứ hai. Từ hàng 2 trở đi, frame đã chứa giao dịch của Bình ở vị trí thứ hai.

Khi dùng full frame, `second_seller` là Bình **ngay trên hàng đầu tiên** của North. Khác biệt nằm ở **khung chạy tăng dần so với toàn phân vùng**.

### 7.3. Hàng thứ n tồn tại nhưng giá trị NULL

Dữ liệu North có `sale_id = 3`, ở vị trí thứ ba theo thứ tự, và `revenue = NULL`.

```sql
SELECT
    sale_id,
    seller,
    nth_value(revenue, 3) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả `third_revenue` là **NULL trên cả năm hàng** North, **dù hàng thứ ba thực sự tồn tại**.

Đối chiếu:

- Nhóm East: `nth_value(seller, 2)` NULL vì **không có hàng thứ hai**.
- Nhóm North: `nth_value(revenue, 3)` NULL vì **hàng thứ ba có giá trị revenue NULL**.

Muốn phân biệt, phải biết **số hàng trong frame** hoặc kiểm tra giá trị/hàng nguồn. Không kết luận “không có hàng thứ ba” chỉ từ việc hàm trả NULL.

### 7.4. Dùng n là một tham số nghiệp vụ

Ví dụ một báo cáo muốn người bán ở vị trí `n` do API truyền vào:

```sql
PREPARE nth_seller(integer) AS
SELECT
    team,
    sale_id,
    nth_value(seller, $1) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS requested_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;

EXECUTE nth_seller(3);

DEALLOCATE nth_seller;
```

Ứng dụng phải **kiểm tra n là số nguyên dương** và giới hạn hợp lý trước khi gửi. Nếu muốn trích giá trị ở một vị trí **tính từ cuối**, `nth_value` theo chuẩn PostgreSQL hiện hành không hỗ trợ tham số `FROM LAST`; xem giải pháp ở phần sau.

## 8. Khung mặc định trong PostgreSQL: nguồn gốc của nhiều hiểu nhầm

Với một window có `ORDER BY` nhưng **không chỉ định frame**, PostgreSQL dùng frame mặc định tương đương:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND CURRENT ROW
```

Điều cần hiểu là `CURRENT ROW` trong chế độ **`RANGE`** không luôn có nghĩa “chỉ kết thúc đúng tại hàng hiện tại”. Nó bao gồm **các hàng ngang hàng (*peers*)** có cùng giá trị trên tất cả biểu thức `ORDER BY`.

### 8.1. Mặc định không phải toàn phân vùng

Ví dụ:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
)
```

có nghĩa ngữ nghĩa như:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    RANGE BETWEEN UNBOUNDED PRECEDING
              AND CURRENT ROW
)
```

Do `sale_id` phá hòa, không có cặp hàng nào trong cùng nhóm cùng cả hai khóa. Frame ở hàng thứ ba North gồm An, Bình, Chi; **không bao gồm Dung và Em**.

### 8.2. Nếu bỏ hẳn `ORDER BY` trong `OVER`

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
    ) AS last_without_order
FROM window_lab.sales
ORDER BY team, sale_id;
```

Khi không có window `ORDER BY`, mọi hàng trong phân vùng là peers; frame mặc định có thể bao gồm **toàn phân vùng**. Nhưng **“hàng cuối” là ai không được xác định về mặt nghiệp vụ** nếu không có thứ tự logic.

Bạn không nên coi `ORDER BY team, sale_id` ở cuối query là đã thiết lập thứ tự cho `last_value`. Nó chỉ sắp xếp kết quả sau khi các giá trị window được tính.

**Quy tắc:** khi muốn “đầu tiên”, “cuối cùng”, “thứ n”, phải định nghĩa **ORDER BY trong OVER**. Khi muốn phạm vi toàn nhóm, còn phải định nghĩa **frame đầy đủ**.

## 9. Peer rows: hai hàng có thể đứng ngang nhau

Hai hàng được gọi là **peers** nếu chúng có **cùng giá trị cho tất cả biểu thức trong `ORDER BY` của window**.

Trong nhóm North:

| sale_id | seller | sold_on |
| ---: | --- | --- |
| 1 | An | 2026-01-03 |
| 2 | Bình | 2026-01-05 |
| 3 | Chi | 2026-01-05 |
| 4 | Dung | 2026-01-09 |
| 5 | Em | 2026-01-12 |

Với:

```sql
ORDER BY sold_on
```

Bình và Chi là peers vì cùng ngày `2026-01-05`.

Với:

```sql
ORDER BY sold_on, sale_id
```

họ **không còn là peers**, vì `sale_id` khác nhau.

### 9.1. Quan sát frame mặc định bao gồm cả peers

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS default_range_count,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS exact_row_count
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | default_range_count | exact_row_count |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 1 |
| 2 | Bình | 3 | 2 |
| 3 | Chi | 3 | 3 |
| 4 | Dung | 4 | 4 |
| 5 | Em | 5 | 5 |

Tại hàng Bình (mã 2), frame `RANGE` mặc định chứa **cả Chi** vì Chi có cùng ngày. Vì vậy, `default_range_count = 3`, dù Bình mới là hàng thứ hai theo `sale_id`.

### 9.2. Peer rows ảnh hưởng thế nào đến `last_value`?

Nếu viết:

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS last_in_default_range
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

ở ngày `2026-01-05`, frame kết thúc ở **peer cuối của cả nhóm ngày 05**, không đơn giản là chính dòng Bình hoặc Chi.

Do chỉ sắp xếp theo `sold_on`, thứ tự tương đối giữa Bình và Chi **không được xác định**. Kết quả của `last_value(seller)` ở nhóm peers có thể phụ thuộc hàng nào được coi cuối trong thứ tự xử lý; không nên xây quy tắc nghiệp vụ dựa vào sự ngẫu nhiên này.

**Cách khắc phục:** thêm một khóa phá hòa có nghĩa, chẳng hạn:

```sql
ORDER BY sold_on, sale_id
```

Nếu `sale_id` là duy nhất, thứ tự window trở nên ổn định.

### 9.3. Vì sao “cùng ngày” chưa đủ cho “giao dịch cuối cùng”?

Trong thực tế, `sold_on` là `date`, nên nó không cho biết giao dịch nào xảy ra **muộn hơn trong cùng ngày**. `sale_id` trong bài chỉ được dùng làm quy ước **phá hòa**.

Nếu nghiệp vụ yêu cầu **thời điểm phát sinh thực**, thiết kế nên có `occurred_at timestamptz` và sắp:

```sql
ORDER BY occurred_at, sale_id
```

Đừng mặc định ID luôn đồng nghĩa thứ tự thời gian. Nếu ID do hệ thống phân tán, import lại hay sinh theo lô, thứ tự ID có thể khác thời điểm.

## 10. `ROWS`, `RANGE` và `GROUPS`: ba cách hiểu frame

PostgreSQL hỗ trợ ba đơn vị frame chính:

| Đơn vị | Đếm/diễn giải biên theo | Ý nghĩa chính |
| --- | --- | --- |
| `ROWS` | Số **hàng vật lý trong thứ tự window** | “Hai giao dịch trước” |
| `RANGE` | **Giá trị khóa ORDER BY** và nhóm peers | “Các giao dịch trong khoảng giá trị” |
| `GROUPS` | Số **nhóm peers** | “Một nhóm ngày trước” |

Ba cách có thể cho kết quả khác nhau trên cùng dữ liệu.

### 10.1. `ROWS`: đếm hàng

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 1 PRECEDING
                 AND CURRENT ROW
    ) AS current_and_previous_row
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | current_and_previous_row |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 2 |
| 3 | Chi | 2 |
| 4 | Dung | 2 |
| 5 | Em | 2 |

Đây là một frame gồm tối đa **hai hàng**: hiện tại và một hàng đứng trước theo `(sold_on, sale_id)`. Nó không quan tâm hai hàng đó cách nhau một hay nhiều ngày.

### 10.2. `RANGE`: theo khoảng giá trị

Với kiểu `date`, có thể trình bày ví dụ trên cột timestamp đã chuyển kiểu để frame có offset `INTERVAL` rõ ràng:

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on::timestamp
        RANGE BETWEEN INTERVAL '4 days' PRECEDING
                  AND CURRENT ROW
    ) AS rows_within_four_days
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả trên bộ mẫu:

| sale_id | seller | rows_within_four_days |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 3 |
| 3 | Chi | 3 |
| 4 | Dung | 3 |
| 5 | Em | 2 |

Giải thích:

- Tại ngày 05/01: khoảng từ 01/01 đến 05/01 bao gồm An, Bình, Chi → 3 hàng.
- Tại ngày 09/01: khoảng từ 05/01 đến 09/01 bao gồm Bình, Chi, Dung → 3 hàng.
- Tại ngày 12/01: khoảng từ 08/01 đến 12/01 bao gồm Dung, Em → 2 hàng.

**Quan trọng:** khi `RANGE` có offset `PRECEDING`/`FOLLOWING`, PostgreSQL yêu cầu một khóa `ORDER BY` có kiểu và phép cộng/trừ offset tương thích. Đừng viết hai khóa `ORDER BY sold_on, sale_id` rồi thêm offset RANGE tùy ý.

### 10.3. `GROUPS`: đếm các nhóm peers

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING
                   AND CURRENT ROW
    ) AS current_and_previous_date_group
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Các nhóm peers theo ngày ở North:

```text
Nhóm 1: 2026-01-03 -> An             (1 hàng)
Nhóm 2: 2026-01-05 -> Bình, Chi      (2 hàng)
Nhóm 3: 2026-01-09 -> Dung           (1 hàng)
Nhóm 4: 2026-01-12 -> Em             (1 hàng)
```

Kết quả:

| sale_id | seller | current_and_previous_date_group |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 3 |
| 3 | Chi | 3 |
| 4 | Dung | 3 |
| 5 | Em | 2 |

`GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` gồm **nhóm ngày hiện tại và nhóm ngày trước đó**, không phải đúng hai hàng.

Nếu các ngày có số lượng giao dịch khác nhau, số hàng thực tế trong frame cũng khác nhau.

### 10.4. Khi nào chọn đơn vị nào?

| Câu hỏi nghiệp vụ | Frame phù hợp để cân nhắc |
| --- | --- |
| “Ba giao dịch gần nhất” | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| “Bảy ngày tính đến ngày giao dịch” | `RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW` trên timestamp phù hợp, hoặc tạo trục ngày riêng |
| “Ngày giao dịch này và ngày giao dịch trước đó có dữ liệu” | `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` với `ORDER BY sold_on` |
| “Đầu và cuối toàn nhóm” | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |
| “Tích lũy từ đầu nhóm đến hiện tại” | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` với thứ tự xác định |

Không chọn `ROWS` chỉ vì tên “hàng” quen thuộc: nếu báo cáo nói “ngày”, cần xác định có muốn đếm **ngày lịch** hay **giao dịch**.

## 11. Frame trượt và ảnh hưởng lên cả ba hàm

Một frame trượt phổ biến:

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

Tại mỗi hàng, frame gồm tối đa **ba hàng gần nhất** theo thứ tự window.

### 11.1. Minh họa trực quan trên nhóm North

```text
Hàng hiện tại     Frame                  Đầu frame    Cuối frame
An              [An]                    An           An
Bình            [An, Bình]              An           Bình
Chi             [An, Bình, Chi]         An           Chi
Dung            [Bình, Chi, Dung]       Bình         Dung
Em              [Chi, Dung, Em]         Chi          Em
```

Khi window trượt:

- `first_value` không còn luôn là An.
- `last_value` vẫn là hàng hiện tại với frame kết thúc ở `CURRENT ROW` và thứ tự duy nhất.
- `nth_value(..., 2)` là hàng thứ hai **trong frame ba hàng**, không phải hàng thứ hai **của cả nhóm**.

### 11.2. Truy vấn hoàn chỉnh

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    first_value(seller) OVER w AS first_in_last_three,
    last_value(seller) OVER w AS last_in_last_three,
    nth_value(seller, 2) OVER w AS second_in_last_three
FROM window_lab.sales
WHERE team = 'North'
WINDOW w AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | seller | first_in_last_three | last_in_last_three | second_in_last_three |
| ---: | --- | --- | --- | --- |
| 1 | An | An | An | NULL |
| 2 | Bình | An | Bình | Bình |
| 3 | Chi | An | Chi | Bình |
| 4 | Dung | Bình | Dung | Chi |
| 5 | Em | Chi | Em | Dung |

Hàng đầu tiên có frame một hàng nên không có vị trí thứ hai. Tại Dung, frame là `[Bình, Chi, Dung]`, nên **thứ hai trong frame** là Chi.

### 11.3. Nhìn về tương lai bằng frame khác

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS last_from_current_forward,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_current_forward
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Với North:

- `last_from_current_forward` là **Em** trên cả năm hàng.
- `second_from_current_forward` lần lượt là **Bình, Chi, Dung, Em, NULL**.

`nth_value(..., 2)` trong frame bắt đầu từ hàng hiện tại trông giống giá trị ở **hàng kế tiếp**. Nhưng nếu mục tiêu thật là “hàng trước/hàng sau theo số bước”, `LAG`/`LEAD` thường diễn đạt rõ hơn.

## 12. `CURRENT ROW` có hai ý nghĩa cần phân biệt

Trong frame `ROWS`:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

`CURRENT ROW` nghĩa là **hàng hiện tại** trong thứ tự các hàng.

Trong frame `RANGE` hoặc `GROUPS`:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

hoặc:

```sql
GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

khi xét cận kết thúc, `CURRENT ROW` có thể bao gồm **peer cuối** của hàng hiện tại; khi xét cận bắt đầu, nó có thể đại diện **peer đầu**.

Do đó, đừng chỉ nhìn cụm `CURRENT ROW` và suy ra frame có đúng số hàng bạn thấy trong một lần chạy. Phải nhìn **đơn vị frame** và **các khóa ORDER BY**.

### 12.1. Tác động đến `last_value` trong nhóm peers

Với:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on
)
```

các hàng cùng `sold_on` là peers, và `last_value` thường hướng đến **peer cuối** của frame. Nếu thứ tự giữa peers không xác định, kết quả có thể không ổn định theo nghĩa nghiệp vụ.

Với:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

mỗi hàng có vị trí rõ ràng, và cuối frame là chính hàng hiện tại.

### 12.2. Tránh thử nghiệm chỉ với dữ liệu không có tie

Nếu mọi ngày chỉ có một giao dịch, `ROWS` và `RANGE` thường cho cảm giác giống nhau ở nhiều câu truy vấn. Khi xuất hiện hai giao dịch cùng ngày, các khung có thể khác rất rõ.

Vì vậy, khi xây báo cáo dựa trên window function, hãy chuẩn bị ít nhất một ca:

- Hai hàng có cùng khóa `ORDER BY`.
- Hàng đầu và hàng cuối phân vùng.
- Một phân vùng chỉ có một hàng.
- Giá trị biểu thức NULL.
- Trường hợp `n` lớn hơn số hàng.

## 13. Toàn phân vùng: viết rõ thay vì dựa vào mặc định

Nếu yêu cầu là “người đầu, người cuối và người thứ ba của toàn nhóm”, mẫu rõ ràng là:

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER w_full AS first_seller,
    last_value(seller)  OVER w_full AS last_seller,
    nth_value(seller, 3) OVER w_full AS third_seller
FROM window_lab.sales
WINDOW w_full AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

Những giá trị mong đợi:

| team | first_seller | last_seller | third_seller |
| --- | --- | --- | --- |
| East | Lan | Lan | NULL |
| North | An | Em | Chi |
| South | Giang | Khánh | Huy |

Mỗi bộ ba được **lặp lại trên mọi hàng thuộc cùng team**.

### 13.1. Vì sao dùng `ROWS` nếu `RANGE` full cũng có thể bao phủ toàn nhóm?

Có thể viết:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND UNBOUNDED FOLLOWING
```

và toàn bộ peers đều nằm trong frame. Nhưng khi mục tiêu là **mọi hàng của phân vùng**, dạng `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` thường dễ đọc và truyền tải ý định “toàn bộ hàng” rõ ràng.

Dù vậy, **ORDER BY vẫn phải đủ xác định**: mở rộng frame không giải quyết tình trạng không biết hàng cuối cùng nào nếu khóa sắp xếp bị trùng.

### 13.2. Có cần viết full frame cho `first_value` không?

Với frame mặc định chạy từ đầu nhóm đến hiện tại, `first_value` thường đã lấy đúng người đầu tiên theo thứ tự xác định. Tuy nhiên, khi cần hiển thị **cùng lúc đầu/cuối/thứ n của toàn nhóm**, viết chung full frame cho cả ba hàm giúp:

- Hợp đồng ngữ nghĩa được nhìn thấy ngay.
- Không phụ thuộc vào việc người đọc nhớ frame mặc định.
- Dễ dùng chung một named window.
- Giảm rủi ro khi chỉnh sửa frame ở một phần query.

## 14. Named window: tái sử dụng định nghĩa nhất quán

PostgreSQL hỗ trợ mệnh đề `WINDOW` để đặt tên cấu hình window.

### 14.1. Một window cho toàn phân vùng

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER whole_team AS team_first,
    last_value(seller)  OVER whole_team AS team_last,
    nth_value(seller, 2) OVER whole_team AS team_second
FROM window_lab.sales
WINDOW whole_team AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

Mọi hàm dùng **cùng phân vùng, thứ tự và frame**.

### 14.2. Hai window cho hai mục đích khác nhau

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER w_full AS team_first,
    last_value(seller) OVER w_full AS team_last,
    first_value(seller) OVER w_recent AS earliest_in_last_three
FROM window_lab.sales
WINDOW
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ),
    w_recent AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    )
ORDER BY team, sold_on, sale_id;
```

Lúc này tên `w_full` và `w_recent` mô tả rõ mục đích. Chúng không phải hai hàm khác nhau: chúng là **hai cấu hình frame**.

### 14.3. Tránh dùng một tên window gây hiểu nhầm

Tên `w1`, `w2` có thể khó đọc trong báo cáo dài. Những tên như `whole_team`, `running_history`, `recent_three` giúp người sửa SQL nhận ra khi nào một hàm đang lấy giá trị toàn nhóm, khi nào đang lấy trong cửa sổ trượt.

**Chú ý:** không thể tùy ý sao chép/chỉnh một named window đã định nghĩa frame bằng mọi cú pháp `OVER (w ... )`. Để tránh lỗi khai báo/copy frame, dùng những named window tường minh như ví dụ trên khi hai mục đích có frame khác nhau.

## 15. Frame ảnh hưởng đến `nth_value` khi có peer groups

Giả sử muốn người bán **thứ hai của mỗi nhóm** theo ngày.

### 15.1. Nếu chỉ ORDER BY ngày

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller_by_date_only
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Bình và Chi cùng ngày 05/01. Nếu chỉ `ORDER BY sold_on`, **không có tiêu chí chọn ai là thứ hai, ai là thứ ba**. Vì thế, kết quả `second_seller_by_date_only` có thể không được xác định ổn định về mặt nghiệp vụ.

Việc dùng full frame không sửa lỗi thiếu khóa phá hòa.

### 15.2. Thêm `sale_id` khi cần vị trí chính xác

```sql
nth_value(seller, 2) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

Với khóa duy nhất `(sold_on, sale_id)`, người thứ hai của North là Bình theo **quy ước thứ tự đã định**.

### 15.3. “Thứ hai” là hàng thứ hai hay ngày thứ hai?

Hai yêu cầu sau **khác nhau**:

1. “Người thực hiện **giao dịch thứ hai**” → xét **hàng thứ hai**; `nth_value(seller, 2)` theo thứ tự đã xác định.
2. “Người thực hiện giao dịch trong **ngày phát sinh thứ hai**” → xét **nhóm ngày thứ hai**, có thể có **nhiều người** (Bình và Chi).

`nth_value` lấy **một hàng**, không tự lấy toàn bộ một peer group.

Nếu cần tất cả người ở ngày phát sinh thứ hai, có thể dùng `DENSE_RANK` theo ngày:

```sql
WITH ranked AS (
    SELECT
        team,
        sale_id,
        seller,
        sold_on,
        DENSE_RANK() OVER (
            PARTITION BY team
            ORDER BY sold_on
        ) AS day_rank
    FROM window_lab.sales
)
SELECT team, sale_id, seller, sold_on
FROM ranked
WHERE day_rank = 2
ORDER BY team, sold_on, sale_id;
```

Với North, ngày phát sinh thứ hai là 05/01 và có **cả Bình lẫn Chi**. Với South, ngày thứ hai là 06/01 và có Hà. Với East, không tồn tại ngày thứ hai.

**Bài học:** xác định “nth **row**” hay “nth **distinct key group**” trước khi chọn hàm.

## 16. `NULL` và giới hạn `RESPECT NULLS` trong PostgreSQL

Theo mô hình SQL, một số hệ thống có các tùy chọn như `RESPECT NULLS` và `IGNORE NULLS` cho các hàm điều hướng giá trị.

Trong PostgreSQL hiện hành, những hàm `first_value`, `last_value`, `nth_value` **không hỗ trợ tùy chọn `IGNORE NULLS`**. Hành vi mặc định tương đương **tôn trọng NULL** (*RESPECT NULLS*).

### 16.1. Giá trị tại vị trí được chọn là NULL thì kết quả NULL

```sql
SELECT
    sale_id,
    seller,
    nth_value(revenue, 3) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Hàng thứ ba là Chi với `revenue NULL` nên giá trị trả về là NULL. PostgreSQL **không tự bỏ qua Chi** để lấy doanh thu của Dung làm giá trị thứ ba.

### 16.2. Không dùng `IGNORE NULLS` theo cú pháp của hệ quản trị khác

Một số đoạn SQL đọc trên mạng có thể viết:

```sql
-- Không phải cú pháp được PostgreSQL hỗ trợ:
first_value(revenue) IGNORE NULLS OVER (...)
```

Đừng copy nguyên một đoạn như vậy từ sản phẩm cơ sở dữ liệu khác. Cần thiết kế cách giải phù hợp với PostgreSQL.

### 16.3. Lấy doanh thu đầu tiên khác NULL trong mỗi nhóm

Một cách rõ ràng là lọc các bản ghi khác NULL trước khi xác định vị trí:

```sql
WITH first_nonnull AS (
    SELECT DISTINCT ON (team)
        team,
        revenue AS first_nonnull_revenue,
        sale_id AS source_sale_id
    FROM window_lab.sales
    WHERE revenue IS NOT NULL
    ORDER BY team, sold_on, sale_id
)
SELECT
    s.team,
    s.sale_id,
    s.seller,
    n.first_nonnull_revenue,
    n.source_sale_id
FROM window_lab.sales AS s
LEFT JOIN first_nonnull AS n
    ON n.team = s.team
ORDER BY s.team, s.sold_on, s.sale_id;
```

Giải thích:

- `WHERE revenue IS NOT NULL` chủ động bỏ những hàng không có doanh thu trước khi chọn hàng đầu.
- `DISTINCT ON (team)` chọn một hàng đầu tiên của mỗi nhóm theo `ORDER BY team, sold_on, sale_id`.
- `LEFT JOIN` mang giá trị về tất cả giao dịch của nhóm.

Với dữ liệu hiện tại, doanh thu đầu khác NULL của North vẫn là 100. Nhưng cách viết này còn đúng nếu **hàng đầu tiên thực tế có revenue NULL**.

### 16.4. Lấy doanh thu cuối cùng khác NULL

```sql
WITH last_nonnull AS (
    SELECT DISTINCT ON (team)
        team,
        revenue AS last_nonnull_revenue,
        sale_id AS source_sale_id
    FROM window_lab.sales
    WHERE revenue IS NOT NULL
    ORDER BY team, sold_on DESC, sale_id DESC
)
SELECT
    s.sale_id,
    s.team,
    s.seller,
    n.last_nonnull_revenue,
    n.source_sale_id
FROM window_lab.sales AS s
LEFT JOIN last_nonnull AS n
    ON n.team = s.team
ORDER BY s.team, s.sold_on, s.sale_id;
```

Ở North, giao dịch cuối có doanh thu khác NULL là Em (140.00). Nếu giao dịch cuối nhóm có revenue NULL, cách này vẫn tìm **hàng gần cuối nhất có giá trị** theo quy ước sắp xếp.

### 16.5. Có thể dùng `LATERAL` khi cần theo từng hàng

Ví dụ tìm doanh thu khác NULL gần nhất **tính đến thời điểm mỗi giao dịch**:

```sql
SELECT
    s.sale_id,
    s.team,
    s.seller,
    s.revenue,
    prev.revenue AS latest_nonnull_so_far
FROM window_lab.sales AS s
LEFT JOIN LATERAL (
    SELECT s2.revenue
    FROM window_lab.sales AS s2
    WHERE s2.team = s.team
      AND s2.revenue IS NOT NULL
      AND (
          s2.sold_on < s.sold_on
          OR (
              s2.sold_on = s.sold_on
              AND s2.sale_id <= s.sale_id
          )
      )
    ORDER BY s2.sold_on DESC, s2.sale_id DESC
    LIMIT 1
) AS prev ON TRUE
ORDER BY s.team, s.sold_on, s.sale_id;
```

Với Chi (mã 3), `revenue` là NULL nhưng `latest_nonnull_so_far` là **180.00** từ Bình. Đây là một bài toán “last non-null so far”, **khác** với `last_value(revenue)` mặc định.

Cách này có thể tốn chi phí nếu chạy truy vấn tương quan trên bảng lớn; hãy cân nhắc index `(team, sold_on, sale_id)` và các chiến lược phù hợp với workload.

## 17. “Thứ n từ cuối”: đổi chiều sắp xếp có chủ đích

PostgreSQL không cung cấp cú pháp `FROM LAST` cho `nth_value` theo chuẩn mở rộng của một số hệ quản trị.

Nếu muốn **người thứ hai tính từ cuối** theo thời gian, có thể **đảo chiều ORDER BY**:

```sql
SELECT
    team,
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_last
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Kết quả theo nhóm:

| team | second_from_last |
| --- | --- |
| East | NULL |
| North | Dung |
| South | Huy |

Giải thích North:

```text
Tăng dần: An, Bình, Chi, Dung, Em
Giảm dần: Em, Dung, Chi, Bình, An
                       ^
     vị trí thứ hai của chiều giảm = Dung
```

Trong dòng sơ đồ trên, vị trí thứ hai là **Dung**; đừng nhầm khoảng cách căn lề của dấu đánh dấu với thứ tự danh sách.

**Điều kiện bắt buộc:** khi đảo chiều sắp xếp, phải đảo **cả tiêu chí phá hòa**. Nếu thứ tự ban đầu `ORDER BY sold_on, sale_id` thì thứ tự ngược chính xác là `ORDER BY sold_on DESC, sale_id DESC`.

### 17.1. Lấy người cuối nhóm bằng `first_value` trên thứ tự giảm dần

Một cách khác để lấy người mới nhất:

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS latest_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Kết quả tương ứng:

- East → Lan.
- North → Em.
- South → Khánh.

Với `first_value` và thứ tự giảm dần ổn định, hàng đầu frame là giao dịch cuối theo thứ tự tăng dần.

### 17.2. Có nên luôn thay `last_value` bằng `first_value DESC`?

Không bắt buộc. Cả hai đều có thể đúng khi:

- Thứ tự được định nghĩa nhất quán.
- Frame được cấu hình phù hợp.
- Giá trị NULL và tie được xử lý theo yêu cầu.
- Cùng một tập hàng được dùng.

Trong báo cáo có nhiều hàm dùng chung thứ tự tăng dần, **`last_value` + full frame** có thể rõ ràng hơn. Trong query chỉ tìm một hàng mới nhất, **`ORDER BY ... DESC LIMIT 1`** hoặc `DISTINCT ON` có thể đơn giản hơn.

## 18. So sánh với `LAG` và `LEAD`

Các hàm này đều thuộc nhóm window functions nhưng có cách chọn giá trị khác nhau.

| Hàm | Đọc dữ liệu từ đâu? | Phụ thuộc frame của `OVER`? |
| --- | --- | --- |
| `first_value` | Hàng đầu **frame hiện tại** | **Có** |
| `last_value` | Hàng cuối **frame hiện tại** | **Có** |
| `nth_value` | Hàng thứ n **trong frame** | **Có** |
| `lag` | Hàng đứng trước với offset được chọn **trong phân vùng** | Không bị giới hạn bởi frame theo cùng cách |
| `lead` | Hàng đứng sau với offset được chọn **trong phân vùng** | Không bị giới hạn bởi frame theo cùng cách |

### 18.1. So trực tiếp `LEAD` với `nth_value`

```sql
SELECT
    sale_id,
    seller,
    LEAD(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS next_seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS next_by_forward_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Với ví dụ này, hai cột thường cho cùng chuỗi:

```text
Bình, Chi, Dung, Em, NULL
```

Nhưng `LEAD(seller)` diễn đạt trực tiếp “người ở hàng sau”, không cần tạo frame bắt đầu từ current row. Khi muốn một giá trị cách hàng hiện tại **n bước**, `LAG` hoặc `LEAD` thường là lựa chọn tự nhiên.

### 18.2. Khác biệt nổi bật khi frame chạy tích lũy

```sql
SELECT
    sale_id,
    seller,
    LEAD(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS next_seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_in_default_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

`LEAD` vẫn nhìn tới người tiếp theo theo thứ tự phân vùng, trong khi `last_value` với frame mặc định thường trả chính seller hiện tại nếu sort key duy nhất.

Không thay thế hai hàm này cho nhau nếu chưa xác định ngữ nghĩa của “cuối khung” và “hàng kế tiếp”.

## 19. Khi muốn lấy đúng một hàng cho mỗi nhóm

`first_value` hoặc `last_value` thường **trả một giá trị lặp trên nhiều hàng**, chứ không thu nhỏ kết quả thành một hàng trên mỗi nhóm.

Nếu mục tiêu chỉ là **mỗi nhóm một giao dịch gần nhất**, dùng query chọn hàng trực tiếp có thể phù hợp hơn.

### 19.1. `DISTINCT ON` của PostgreSQL

```sql
SELECT DISTINCT ON (team)
    team,
    sale_id,
    seller,
    sold_on,
    revenue
FROM window_lab.sales
ORDER BY team, sold_on DESC, sale_id DESC;
```

Kết quả gồm ba hàng:

| team | sale_id | seller |
| --- | ---: | --- |
| East | 10 | Lan |
| North | 5 | Em |
| South | 9 | Khánh |

`DISTINCT ON (team)` giữ hàng đầu tiên **theo thứ tự ORDER BY đã chỉ định** cho mỗi team.

Điểm khác biệt:

- `last_value` full frame: vẫn trả **tất cả giao dịch**, kèm seller cuối nhóm.
- `DISTINCT ON`: chỉ trả **một giao dịch mỗi team**.

### 19.2. `ROW_NUMBER` khi cần chọn top 1

```sql
WITH ranked AS (
    SELECT
        team,
        sale_id,
        seller,
        sold_on,
        revenue,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY sold_on DESC, sale_id DESC
        ) AS rn
    FROM window_lab.sales
)
SELECT team, sale_id, seller, sold_on, revenue
FROM ranked
WHERE rn = 1
ORDER BY team;
```

Cũng tìm giao dịch cuối theo mỗi nhóm.

Lợi điểm của `ROW_NUMBER` là có thể dùng `rn <= 3` để lấy top 3 **hàng**. Nếu muốn giữ tất cả hàng ngang hạng, có thể cân nhắc `RANK` hoặc `DENSE_RANK` theo yêu cầu.

### 19.3. Không thể lọc alias của window trong `WHERE` cùng SELECT

Sai:

```sql
-- Không hợp lệ: rn chưa sẵn có ở WHERE cùng query level.
SELECT
    team,
    seller,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
    ) AS rn
FROM window_lab.sales
WHERE rn = 1;
```

Đúng: dùng CTE hoặc subquery bên ngoài để lọc kết quả window như ví dụ trên.

PostgreSQL tính window functions ở tầng xử lý thích hợp của SELECT, **sau bước lọc WHERE của cùng query level**. Muốn dùng giá trị window làm điều kiện lọc, cần một mức truy vấn ngoài.

## 20. `PARTITION BY` thay đổi cả cách hiểu first/last/nth

### 20.1. Không `PARTITION BY`: toàn bộ kết quả là một phân vùng

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_over_all_sales
FROM window_lab.sales
ORDER BY sold_on, sale_id;
```

Lúc này `first_over_all_sales` là người bán sớm nhất **trong toàn bộ tập hàng đã qua WHERE** (ở dữ liệu mẫu: Giang, ngày 02/01), không phải sớm nhất của từng team.

### 20.2. Thêm `PARTITION BY team`

```sql
first_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

Kết quả theo từng nhóm:

- North → An.
- South → Giang.
- East → Lan.

### 20.3. `WHERE` lọc trước khi tính window

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_seller_in_filtered_set
FROM window_lab.sales
WHERE sold_on >= DATE '2026-01-06'
ORDER BY team, sold_on, sale_id;
```

Vì `WHERE sold_on >= '2026-01-06'` loại các giao dịch trước ngày đó **trước khi tính window**, người đầu tiên trong tập đã lọc **không còn** là An cho North hay Giang cho South.

Trong tập đã lọc:

- North bắt đầu ở Dung (09/01).
- South bắt đầu ở Hà (06/01).
- East bắt đầu ở Lan (08/01).

**Đây là khác biệt nghiệp vụ rất quan trọng.**

### 20.4. Nếu muốn lọc phần hiển thị nhưng vẫn tính trên toàn bộ lịch sử

Đưa tính toán window vào CTE trước, lọc ngoài:

```sql
WITH with_team_bounds AS (
    SELECT
        sale_id,
        team,
        seller,
        sold_on,
        first_value(seller) OVER (
            PARTITION BY team
            ORDER BY sold_on, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS first_seller_ever
    FROM window_lab.sales
)
SELECT
    team,
    sale_id,
    seller,
    sold_on,
    first_seller_ever
FROM with_team_bounds
WHERE sold_on >= DATE '2026-01-06'
ORDER BY team, sold_on, sale_id;
```

Bây giờ báo cáo chỉ hiển thị những giao dịch từ 06/01 trở đi, nhưng `first_seller_ever` vẫn là:

- North → An.
- South → Giang.
- East → Lan.

**Phải phân biệt:** “giá trị đầu tiên **trong kỳ báo cáo**” với “giá trị đầu tiên **trong toàn bộ lịch sử**, hiển thị trên các hàng của kỳ báo cáo”.

## 21. Khung và tác động của `UNBOUNDED`, `PRECEDING`, `FOLLOWING`

Các mốc frame thường gặp:

| Từ khóa | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Từ đầu phân vùng |
| `n PRECEDING` | Lùi n đơn vị frame trước hàng/nhóm/giá trị hiện tại |
| `CURRENT ROW` | Hàng hoặc nhóm peers hiện tại tùy đơn vị |
| `n FOLLOWING` | Tiến n đơn vị frame sau hàng/nhóm/giá trị hiện tại |
| `UNBOUNDED FOLLOWING` | Đến cuối phân vùng |

### 21.1. Một số frame thông dụng

**Từ đầu đến hiện tại:**

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND CURRENT ROW
```

Hợp với lũy kế, lịch sử tính đến hiện tại, `first_value` từ đầu nhóm.

**Toàn phân vùng:**

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
```

Hợp với first/last/nth trên toàn nhóm.

**Ba hàng gần nhất, bao gồm hiện tại:**

```sql
ROWS BETWEEN 2 PRECEDING
         AND CURRENT ROW
```

Hợp với giá trị đầu/cuối của cửa sổ ba giao dịch.

**Hàng hiện tại và hàng kế tiếp:**

```sql
ROWS BETWEEN CURRENT ROW
         AND 1 FOLLOWING
```

Hợp với các phép so sánh cục bộ và những bài toán “next event” đơn giản.

**Năm hàng quanh hàng hiện tại:**

```sql
ROWS BETWEEN 2 PRECEDING
         AND 2 FOLLOWING
```

Hợp với phân tích lân cận nhưng lưu ý frame ở đầu/cuối phân vùng sẽ có ít hàng hơn.

### 21.2. Không phải mọi tổ hợp biên đều hợp lệ

Cú pháp frame có quy tắc thứ tự: biên bắt đầu không thể đứng sau biên kết thúc theo thứ tự cho phép, và không thể dùng mọi loại offset/kết hợp tùy ý.

Ngoài ra, nếu biểu thức frame có giá trị không hợp lệ như offset âm, PostgreSQL có thể báo lỗi khi thực thi. Những tham số từ ứng dụng cần được kiểm soát, không chỉ dựa vào chuỗi SQL tự ghép.

### 21.3. Frame rỗng và `nth_value`

Khi frame không chứa đủ hàng cho vị trí n, `nth_value` trả NULL. Điều này cũng có thể xảy ra khi frame ở ranh giới đầu/cuối phân vùng bị thu hẹp.

Đừng coi mọi frame đều luôn có đúng số hàng chỉ vì đã viết `2 PRECEDING` hoặc `2 FOLLOWING`. Các hàng nằm ngoài phân vùng không được lấy vào.

## 22. Khung có thể loại trừ một số hàng bằng `EXCLUDE`

PostgreSQL hỗ trợ cú pháp frame exclusion như:

- `EXCLUDE CURRENT ROW`.
- `EXCLUDE GROUP`.
- `EXCLUDE TIES`.
- `EXCLUDE NO OTHERS`.

Chúng thay đổi những hàng **thực sự nằm trong frame** sau khi các biên đã được xác định.

### 22.1. Loại chính hàng hiện tại

```sql
SELECT
    sale_id,
    seller,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS earlier_row_count
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả `earlier_row_count` lần lượt **0, 1, 2, 3, 4**.

Đây không phải ví dụ bắt buộc cho ba hàm giá trị, nhưng nó cho thấy **frame còn có thể bị loại trừ** sau khi chọn giới hạn bắt đầu/kết thúc.

### 22.2. Ảnh hưởng lên `last_value`

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS previous_seller_by_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Với thứ tự duy nhất, đây là người bán cuối trong **những hàng đứng trước**, nên:

| sale_id | seller | previous_seller_by_frame |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | An |
| 3 | Chi | Bình |
| 4 | Dung | Chi |
| 5 | Em | Dung |

Nó có vẻ giống `LAG(seller)`, nhưng đây là một cách mô tả khác bằng frame và exclusion. Nếu chỉ cần hàng đứng trước, `LAG` vẫn thường rõ ràng hơn.

### 22.3. `EXCLUDE GROUP` và `EXCLUDE TIES`

Với `ORDER BY sold_on` và hai giao dịch cùng ngày:

- `EXCLUDE GROUP` loại toàn bộ **peer group** hiện tại khỏi frame, kể cả hàng hiện tại.
- `EXCLUDE TIES` loại các **peer khác** với hàng hiện tại nhưng vẫn giữ hàng hiện tại (nếu nó nằm trong frame).

Những tùy chọn này có ích khi phân tích “những nhóm ngày trước đó nhưng không tính ngày hiện tại” hoặc cần kiểm soát hàng ngang hạng.

Tuy nhiên, trước khi dùng, hãy hỏi liệu nghiệp vụ cần đếm **giao dịch** hay **ngày có giao dịch**. Đôi khi viết CTE tổng hợp theo ngày trước sẽ đơn giản hơn nhiều so với một frame nhiều tầng.

## 23. So sánh nhanh: running frame và full frame

Cùng một hàm có thể tạo câu trả lời khác nhau:

| Hàm | Running frame: từ đầu đến hiện tại | Full frame: toàn phân vùng |
| --- | --- | --- |
| `first_value(seller)` | Người đầu tiên từ đầu nhóm (thường cố định) | Người đầu tiên toàn nhóm |
| `last_value(seller)` | Người cuối **đến hiện tại**; có thể là hàng hiện tại | Người cuối **toàn nhóm** |
| `nth_value(seller, 2)` | NULL cho đến khi frame có hai hàng; sau đó người thứ hai | Người thứ hai toàn nhóm, kể cả ở hàng đầu |
| `nth_value(revenue, 3)` | NULL khi chưa đủ ba hàng; cũng NULL nếu giá trị hàng thứ ba NULL | Giá trị hàng thứ ba toàn nhóm, có thể NULL |

Một truy vấn minh họa:

```sql
SELECT
    sale_id,
    seller,
    first_value(seller) OVER w_running AS first_running,
    last_value(seller)  OVER w_running AS last_running,
    nth_value(seller, 2) OVER w_running AS second_running,
    first_value(seller) OVER w_full AS first_full,
    last_value(seller)  OVER w_full AS last_full,
    nth_value(seller, 2) OVER w_full AS second_full
FROM window_lab.sales
WHERE team = 'North'
WINDOW
    w_running AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY sold_on, sale_id;
```

Với North, những cột *full* lần lượt luôn là:

```text
first_full  = An
last_full   = Em
second_full = Bình
```

Còn *running* thay đổi tùy hàng; đặc biệt `last_running` đi theo seller hiện tại.

## 24. Ví dụ thực tế: giá đầu kỳ, cuối kỳ và giá trị thứ ba

Giả sử một bảng giá có lịch sử theo ngày:

```sql
CREATE TABLE window_lab.product_prices (
    price_id bigint PRIMARY KEY,
    product_id text NOT NULL,
    effective_on date NOT NULL,
    price numeric(12,2) NOT NULL
);

INSERT INTO window_lab.product_prices
    (price_id, product_id, effective_on, price)
VALUES
    (11, 'P-A', DATE '2026-01-01', 100.00),
    (12, 'P-A', DATE '2026-01-10', 120.00),
    (13, 'P-A', DATE '2026-01-20', 110.00),
    (14, 'P-B', DATE '2026-01-05',  50.00),
    (15, 'P-B', DATE '2026-01-15',  60.00);
```

### 24.1. Giá đầu và cuối lịch sử mỗi sản phẩm

```sql
SELECT
    product_id,
    effective_on,
    price,
    first_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_price,
    last_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_price,
    nth_value(price, 3) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_price
FROM window_lab.product_prices
ORDER BY product_id, effective_on, price_id;
```

Kết quả theo sản phẩm:

| product_id | first_price | last_price | third_price |
| --- | ---: | ---: | ---: |
| P-A | 100.00 | 110.00 | 110.00 |
| P-B | 50.00 | 60.00 | NULL |

**Không nhầm last price với MAX(price):** với sản phẩm P-A, giá cuối lịch sử là **110**, nhưng giá cao nhất từng ghi là **120**.

### 24.2. Hiệu số so với giá đầu kỳ

```sql
SELECT
    product_id,
    effective_on,
    price,
    price - first_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS change_from_initial_price
FROM window_lab.product_prices
ORDER BY product_id, effective_on, price_id;
```

Với P-A:

- Ngày 01/01: 100 − 100 = 0.
- Ngày 10/01: 120 − 100 = 20.
- Ngày 20/01: 110 − 100 = 10.

Đây là ví dụ phù hợp với `first_value`: giá đầu tiên là **baseline** để so sánh mọi hàng sau đó.

### 24.3. Đầu kỳ và cuối kỳ phải xác định tập lọc

Nếu chỉ phân tích giá trong tháng 2 nhưng không có bản ghi tháng 2, việc `WHERE effective_on` giới hạn vào tháng 2 sẽ tạo **tập rỗng**, không có giá đầu/cuối dù sản phẩm có giá hiệu lực từ tháng 1.

Với nghiệp vụ **giá đang có hiệu lực tại ngày X**, cần logic chọn bản ghi mới nhất `effective_on <= X`, không đơn giản dùng `last_value` trên những hàng phát sinh **trong** ngày X.

Window functions rất hữu ích nhưng không thay thế việc xác định đúng ngữ nghĩa “sự kiện xảy ra trong kỳ” và “trạng thái có hiệu lực tại kỳ”.

## 25. Ví dụ thực tế: báo cáo cohort và sự kiện đầu/cuối của người dùng

Giả sử bảng sự kiện người dùng có:

```text
user_id
event_id
event_time
event_type
```

Muốn mỗi sự kiện kèm loại sự kiện **đầu tiên** và **cuối cùng** của người dùng:

```sql
-- Lược đồ minh họa, không thuộc bảng demo đã tạo:
SELECT
    user_id,
    event_id,
    event_time,
    event_type,
    first_value(event_type) OVER (
        PARTITION BY user_id
        ORDER BY event_time, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_event_type,
    last_value(event_type) OVER (
        PARTITION BY user_id
        ORDER BY event_time, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_event_type
FROM user_events;
```

Điểm quan trọng:

- `event_time` cần có ngữ nghĩa thời gian rõ, thường là `timestamptz`.
- `event_id` giúp phá hòa nếu hai sự kiện cùng thời điểm.
- Nếu chỉ xét một giai đoạn bằng `WHERE` ở cùng SELECT, “đầu/cuối” là trong **giai đoạn đã lọc**.
- Nếu cần loại sự kiện đầu tiên của **cả lịch sử**, tính ở một lớp truy vấn đầy đủ trước rồi mới lọc hiển thị.

### 25.1. Đầu và cuối không đồng nghĩa phiên người dùng

Nếu muốn biết phiên (*session*) đầu hoặc cuối, cần có `session_id` và quy tắc phiên được xác định. Một chuỗi sự kiện không tự chia thành session chỉ vì được sắp theo thời gian.

Tương tự, `nth_value(event_type, 3)` trả **sự kiện thứ ba theo thứ tự**, không tự trả “sự kiện thứ ba thuộc một phiên” nếu bạn chưa `PARTITION BY user_id, session_id`.

## 26. `ORDER BY` với giá trị NULL và collation

Không chỉ `expression` có thể NULL; **khóa sắp xếp** cũng có thể NULL trong những bộ dữ liệu khác.

Trong bảng `window_lab.sales`, `sold_on NOT NULL` nên thứ tự đơn giản. Nhưng nếu một cột ngày cho phép NULL, bạn phải xác định:

- NULL có đứng trước ngày hợp lệ không?
- NULL đại diện “chưa biết ngày” hay “không áp dụng”?
- Những hàng NULL có cần bị loại trước khi tính first/last không?

### 26.1. Dùng `NULLS FIRST` hoặc `NULLS LAST`

Ví dụ sắp doanh thu giảm dần:

```sql
SELECT
    sale_id,
    seller,
    revenue,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY revenue DESC NULLS LAST, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS highest_recorded_seller
FROM window_lab.sales
ORDER BY team, sale_id;
```

`NULLS LAST` đảm bảo dòng có `revenue NULL` không bị chọn là đầu chỉ vì quy tắc sắp NULL của chiều giảm dần.

Nếu muốn “giao dịch đầu tiên” theo thời gian, đừng sắp theo doanh thu; chọn đúng khóa nghiệp vụ.

### 26.2. Text ORDER BY và collation

Nếu sắp theo tên:

```sql
ORDER BY seller
```

thứ tự phụ thuộc collation của biểu thức. Tên có dấu tiếng Việt có thể được so sánh khác nhau giữa các locale/collation.

Nếu nghiệp vụ yêu cầu “đầu tiên theo tên từ điển”, hãy xác định collation và cách xử lý hoa/thường, dấu. Nếu cần một lựa chọn ổn định khi nhiều tên ngang hàng, thêm khóa duy nhất:

```sql
ORDER BY seller, sale_id
```

Việc chọn collation là một **quyết định ngữ nghĩa dữ liệu**; không phải mọi hệ thống nên ép `COLLATE "C"` chỉ để có thứ tự byte.

## 27. Window frame và các hàm tổng hợp: cùng cú pháp, khác tác động

Frame không chỉ ảnh hưởng `first_value`, `last_value`, `nth_value`. Các aggregate được dùng dưới dạng window cũng có thể phụ thuộc frame.

### 27.1. Tổng lũy kế

```sql
SELECT
    sale_id,
    seller,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Với North, `SUM` bỏ qua NULL và lũy kế sẽ là:

| sale_id | revenue | running_revenue |
| ---: | ---: | ---: |
| 1 | 100.00 | 100.00 |
| 2 | 180.00 | 280.00 |
| 3 | NULL | 280.00 |
| 4 | 90.00 | 370.00 |
| 5 | 140.00 | 510.00 |

Khác với `last_value(revenue)` ở hàng 3 trả **NULL**, `SUM(revenue)` vẫn là 280 vì aggregate **bỏ qua giá trị NULL**.

### 27.2. Tổng toàn phân vùng

```sql
SUM(revenue) OVER (
    PARTITION BY team
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

hoặc đơn giản:

```sql
SUM(revenue) OVER (PARTITION BY team)
```

thường cho tổng toàn nhóm. Khi không có `ORDER BY`, frame mặc định bao phủ toàn phân vùng.

Điểm thực hành: với aggregate muốn tổng toàn nhóm, việc **bỏ ORDER BY trong OVER** thường rõ ràng. Với `first_value` và `last_value`, bỏ ORDER BY lại khiến “đầu/cuối” thiếu ý nghĩa xác định.

### 27.3. Không phải window function nào cũng dùng frame giống nhau

Hàm `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD` có ngữ nghĩa riêng về thứ tự/phân vùng; frame không quyết định kết quả của chúng theo cùng cách với `first_value`, `last_value`, `nth_value` hoặc aggregate chạy trên frame.

Nếu đã hiểu frame cho `SUM`, vẫn cần nhớ **hàm giá trị lấy vị trí** cụ thể; không suy luận một cách máy móc từ một loại hàm sang mọi loại window function.

## 28. Hiệu năng: sắp xếp, phân vùng và số hàng

Window functions mạnh vì tránh tự JOIN lại bảng nhiều lần, nhưng với dữ liệu lớn chúng có chi phí.

### 28.1. PostgreSQL phải tổ chức thứ tự phù hợp

Một câu:

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales;
```

có thể cần sắp xếp theo `(team, sold_on, sale_id)` hoặc tận dụng thứ tự dữ liệu từ đường đọc/index phù hợp.

Với bảng vài hàng, sort không đáng kể. Với nhiều triệu bản ghi, việc sắp xếp có thể tiêu tốn CPU, bộ nhớ và I/O.

### 28.2. Index ứng viên

```sql
CREATE INDEX idx_sales_team_date_id
ON window_lab.sales (team, sold_on, sale_id);
```

Đây là **một ứng viên** vì khóa index tương ứng phân vùng và thứ tự window thường dùng.

Nhưng không phải cứ tạo index là mọi truy vấn window dùng được hiệu quả. PostgreSQL có thể chọn sequential scan + sort, đặc biệt nếu đọc hầu hết bảng hoặc cần thêm nhiều cột không nằm trong index.

Đánh giá index phải dựa trên:

- Quy mô bảng.
- Điều kiện `WHERE`.
- Độ phân bố của `team`.
- Số hàng và kích thước mỗi partition.
- Chi phí đọc heap so với index.
- Nhu cầu ghi dữ liệu và bảo trì index.

### 28.3. Xem `EXPLAIN`

```sql
EXPLAIN
SELECT
    sale_id,
    team,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Bạn có thể gặp:

- `WindowAgg`: xử lý window functions.
- `Sort` hoặc `Incremental Sort`: chuẩn bị thứ tự.
- `Seq Scan` / `Index Scan`: đọc bảng.
- Các node khác tùy kế hoạch.

`EXPLAIN (ANALYZE, BUFFERS)` thực thi truy vấn để đo số hàng, thời gian và buffer. Không cần chạy trên production nếu chưa đánh giá tải; với những câu SQL có tác dụng ghi, EXPLAIN ANALYZE vẫn có thể thực thi tác dụng đó.

### 28.4. Full frame có thể cần nhiều dữ liệu hơn running frame

Khi hàm cần giá trị cuối **toàn phân vùng**, engine phải có cách xác định hàng cuối; tùy kế hoạch, điều này có thể liên quan đến buffering/spooling của các partition lớn. Khung `ROWS ... UNBOUNDED FOLLOWING` vì thế không phải lúc nào có cùng đặc điểm tiêu thụ tài nguyên như một phép cộng lũy kế chỉ cần lịch sử.

Nhưng không khẳng định full frame luôn chậm hơn: chi phí thực tế phụ thuộc hàm, độ rộng hàng, số partition, index, bộ nhớ và cách planner thực thi.

Nếu chỉ cần **một hàng cuối mỗi nhóm**, `DISTINCT ON` hoặc `ROW_NUMBER() ... WHERE rn=1` ở mức query ngoài có thể đơn giản hơn so với việc tính giá trị cuối rồi lặp lại trên mọi giao dịch.

### 28.5. Nhiều định nghĩa window có thể tạo thêm sort

Nếu một báo cáo tính đồng thời:

- First theo ngày tăng.
- First theo doanh thu giảm.
- Second từ cuối theo ngày giảm.

thì các cửa sổ có **thứ tự khác nhau**. PostgreSQL có thể cần thêm bước sort/WindowAgg. Dùng một quy ước thứ tự chung khi nghiệp vụ cho phép, và chỉ đảo chiều thật sự cần thiết.

Không thay đổi ý nghĩa báo cáo chỉ để gom các hàm vào một `WINDOW`: tính đúng phải được ưu tiên trước hiệu năng.

## 29. Lỗi thường gặp với ba hàm giá trị

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| `last_value` không ghi frame | Thường trả hàng hiện tại/peer cuối, không phải cuối nhóm | Full frame khi cần cuối phân vùng |
| Coi `CURRENT ROW` ở RANGE chỉ là hàng hiện tại | Bỏ qua peer rows | Hiểu peer group hoặc dùng ROWS phù hợp |
| `ORDER BY sold_on` có nhiều tie | First/last/nth có thể không ổn định | Thêm `sale_id` hoặc tiêu chí phá hòa |
| Bỏ `ORDER BY` trong OVER | “Đầu/cuối” không có thứ tự nghiệp vụ | Viết ORDER BY trong OVER |
| Chỉ có ORDER BY cuối SELECT | Không xác định thứ tự window | ORDER BY phải ở trong OVER |
| Dùng `nth_value(..., 2)` và mong mọi hàng có giá trị | Running frame đầu kỳ chưa đủ hai hàng | Mở full frame nếu cần thứ hai toàn nhóm |
| `nth_value` trả NULL và kết luận không có hàng | Có thể hàng tồn tại nhưng expression NULL | Kiểm tra vị trí, số hàng và NULL |
| Coi `nth_value` là “nth từ cuối” | PostgreSQL mặc định tính từ đầu frame | Đảo chiều ORDER BY phù hợp |
| Dùng `MIN` thay `first_value` | Lấy giá trị nhỏ nhất thay vì sớm nhất | Xác định tiêu chí sắp xếp |
| Dùng `MAX` thay `last_value` | Lấy giá trị lớn nhất thay vì cuối thời gian | Dùng last_value/full frame |
| Dùng `first_value` để lấy một hàng mỗi nhóm | Vẫn còn mọi hàng nguồn | `DISTINCT ON` hoặc ROW_NUMBER |
| Dùng `WHERE` trước window nhưng cần lịch sử toàn kỳ | Giá trị đầu/cuối bị tính trên dữ liệu đã lọc | Tính window ở CTE trước khi lọc hiển thị |
| Coi `ROWS 2 PRECEDING` là “2 ngày trước” | Nó đếm hàng, không đếm ngày | RANGE theo thời gian hoặc calendar |
| Coi GROUPS là số hàng | Peer group có thể chứa nhiều hàng | Nhớ GROUPS đếm nhóm peers |
| Viết RANGE offset có nhiều ORDER BY keys | Không phù hợp yêu cầu cú pháp offset RANGE | Dùng một khóa ORDER BY thích hợp |
| Muốn IGNORE NULLS như hệ quản trị khác | PostgreSQL không hỗ trợ lựa chọn đó | Lọc non-null với query riêng |
| Sắp doanh thu DESC không chỉ định NULLS LAST | NULL có thể được chọn làm đầu | Đặt NULLS LAST khi đúng nghiệp vụ |
| Chỉ dựa vào kết quả trên bộ dữ liệu không có tie | Lỗi peer group không lộ | Test nhiều hàng cùng khóa |
| Dùng ID như thời gian mà không xác minh | “Cuối” có thể sai nghiệp vụ | Dùng timestamp + khóa phá hòa |
| Dùng window trên nhiều triệu hàng không kiểm soát | Sort/buffer tốn tài nguyên | EXPLAIN, index phù hợp, giới hạn workload |
| Dùng SQL có alias window ở WHERE cùng SELECT | Lỗi truy vấn | CTE hoặc subquery ngoài |

## 30. Bài tập thực hành có đáp án

Tất cả bài tập dưới đây dùng bảng `window_lab.sales`, trừ những bài ghi rõ bảng `product_prices`.

### Bài 1. Người bán đầu tiên mỗi nhóm

Yêu cầu: thêm cột tên người đầu tiên theo `(sold_on, sale_id)` trên **mọi hàng giao dịch**.

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Đáp án:** East → Lan; North → An; South → Giang.

### Bài 2. Người bán cuối cùng mỗi nhóm

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Đáp án:** East → Lan; North → Em; South → Khánh.

### Bài 3. Vì sao câu sau không lặp Em cho mọi hàng North?

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS result
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** frame mặc định là `RANGE UNBOUNDED PRECEDING ... CURRENT ROW`, và thứ tự duy nhất khiến khung kết thúc ở hàng hiện tại. `last_value` trả seller của hàng hiện tại, không phải Em cho mọi hàng.

### Bài 4. Giao dịch thứ hai của mỗi nhóm

```sql
SELECT
    team,
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Đáp án:** East NULL; North Bình; South Hà.

### Bài 5. Vì sao nhóm East cho `nth_value(seller, 2) = NULL`?

**Đáp án:** East chỉ có một hàng, nên trong full frame không có hàng thứ hai.

### Bài 6. Vì sao nhóm North cho `nth_value(revenue, 3) = NULL` dù có năm hàng?

**Đáp án:** hàng thứ ba là Chi, và `Chi.revenue` là NULL. Không phải thiếu hàng thứ ba.

### Bài 7. Chạy `nth_value(seller, 2)` trên frame mặc định

```sql
SELECT
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS second_so_far
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** lần lượt `NULL, Bình, Bình, Bình, Bình`.

### Bài 8. Hai giao dịch cùng ngày tạo peer group nào?

Với North:

```sql
ORDER BY sold_on
```

**Đáp án:** Bình (mã 2) và Chi (mã 3) là peers, vì cùng ngày 05/01.

Nếu thêm `sale_id` vào ORDER BY, họ không còn peers.

### Bài 9. Default RANGE count tại Bình bằng mấy?

```sql
SELECT
    sale_id,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS cnt
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** tại Bình, `cnt = 3`, vì frame mặc định bao gồm An và cả hai hàng peers của ngày 05/01.

### Bài 10. Lấy seller đầu trong ba giao dịch gần nhất

```sql
SELECT
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    ) AS oldest_in_last_three
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** An, An, An, Bình, Chi.

### Bài 11. Lấy seller thứ hai trong ba giao dịch gần nhất

**Đáp án:**

```sql
SELECT
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS second_in_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Kết quả: NULL, Bình, Bình, Chi, Dung.

### Bài 12. Tại sao `ROWS 2 PRECEDING` không phải hai ngày trước?

**Đáp án:** `ROWS` đếm **hàng**, không đo khoảng thời gian. Nếu một ngày có 100 giao dịch, hai hàng trước có thể nằm cùng ngày hiện tại.

### Bài 13. Khác biệt giữa `ROWS` và `GROUPS`

```sql
SELECT
    sale_id,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS cnt
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** số hàng trong frame theo ngày là 1, 3, 3, 3, 2. `GROUPS` đếm nhóm ngày, không phải một hàng trước.

### Bài 14. Lấy giao dịch thứ hai tính từ cuối mỗi nhóm

```sql
SELECT
    team,
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_end
FROM window_lab.sales
ORDER BY team, sale_id;
```

**Đáp án:** East NULL; North Dung; South Huy.

### Bài 15. Lấy người cuối nhóm bằng `first_value`

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS newest_seller
FROM window_lab.sales
ORDER BY team, sale_id;
```

**Đáp án:** East Lan; North Em; South Khánh.

### Bài 16. Hai cách lấy hàng mới nhất khác nhau thế nào?

So sánh:

- `last_value(seller)` full frame.
- `SELECT DISTINCT ON (team) ... ORDER BY team, sold_on DESC, sale_id DESC`.

**Đáp án:** cách đầu bổ sung seller cuối cho **mọi hàng của team**; cách thứ hai **chỉ giữ một hàng** đại diện mới nhất của team.

### Bài 17. Lấy toàn bộ người trong ngày giao dịch thứ hai của North

```sql
WITH by_day AS (
    SELECT
        sale_id,
        team,
        seller,
        sold_on,
        DENSE_RANK() OVER (
            PARTITION BY team
            ORDER BY sold_on
        ) AS day_rank
    FROM window_lab.sales
)
SELECT sale_id, seller, sold_on
FROM by_day
WHERE team = 'North' AND day_rank = 2
ORDER BY sale_id;
```

**Đáp án:** Bình và Chi, cùng ngày 05/01. `nth_value(...,2)` chỉ lấy **một hàng**, không lấy tất cả peers.

### Bài 18. Nếu chỉ lấy giao dịch từ 06/01 rồi tính `first_value`, North còn An không?

**Đáp án:** không. `WHERE sold_on >= '2026-01-06'` loại An, Bình, Chi trước khi window chạy. First trong tập đã lọc của North là Dung.

Nếu cần **first của toàn lịch sử** trong báo cáo hiện tại, tính window trong CTE trước rồi lọc bên ngoài.

### Bài 19. Giá cuối lịch sử có luôn là `MAX(price)`?

Dùng bảng `window_lab.product_prices`.

**Đáp án:** không. P-A có giá cuối 110, nhưng max price là 120 ở ngày 10/01. Một hàm dựa trên **thứ tự thời gian**, hàm kia dựa trên **giá trị lớn nhất**.

### Bài 20. Tìm doanh thu khác NULL gần nhất của Chi

**Đáp án:** `180.00` từ Bình. `last_value(revenue)` với running frame tại Chi trả NULL vì Chi.revenue NULL; PostgreSQL không hỗ trợ `IGNORE NULLS` cho hàm này. Có thể dùng LATERAL/query riêng lọc `revenue IS NOT NULL` và chọn hàng gần nhất.

### Bài 21. Dùng `EXCLUDE CURRENT ROW` làm gì?

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS previous_seller
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Đáp án:** NULL, An, Bình, Chi, Dung. Với yêu cầu đơn giản này, `LAG(seller)` thường ngắn hơn.

### Bài 22. Tại sao cần `NULLS LAST` khi ORDER BY revenue DESC?

**Đáp án:** nếu bỏ quy tắc NULL, một hàng không có doanh thu có thể đứng trước các hàng có giá trị thật theo thứ tự giảm dần của PostgreSQL. Điều đó có thể làm `first_value(seller)` chọn seller có doanh thu chưa biết thay vì seller có doanh thu lớn nhất.

### Bài 23. Khi nào dùng `RANGE INTERVAL '4 days' PRECEDING`?

**Đáp án:** khi muốn lấy các giao dịch trong **bốn ngày trước đến hiện tại**, thay vì một số **hàng** cố định. Cần một khóa ORDER BY thời gian và offset tương thích.

### Bài 24. Muốn biết hàng trước mà không quan tâm frame nên dùng gì?

**Đáp án:** `LAG`; cho hàng sau dùng `LEAD`. `first_value`, `last_value`, `nth_value` phù hợp khi cần vị trí trong **frame**.

### Bài 25. Phân biệt ORDER BY trong OVER và ngoài SELECT

```sql
SELECT
    sale_id,
    team,
    first_value(seller) OVER (
        PARTITION BY team ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY sale_id DESC;
```

**Đáp án:** thứ tự window vẫn theo `sold_on, sale_id` trong mỗi team. `ORDER BY sale_id DESC` ở cuối chỉ sắp các hàng kết quả giảm theo mã.

### Bài 26. `first_value` có thể đổi giá trị trên các hàng cùng team không?

**Đáp án:** có. Nếu dùng **khung trượt** như `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`, hàng đầu frame có thể tiến dần từ An đến Bình, Chi khi giao dịch mới xuất hiện.

### Bài 27. Tại sao full frame không giải quyết thứ tự tie?

**Đáp án:** full frame xác định **phạm vi các hàng**, nhưng nếu `ORDER BY sold_on` có nhiều hàng cùng ngày, chưa xác định ai đứng trước/đứng sau trong peer group. Cần tiêu chí phá hòa có ý nghĩa nghiệp vụ.

### Bài 28. Viết hai named windows: full và recent

```sql
SELECT
    sale_id,
    team,
    seller,
    last_value(seller) OVER w_full AS last_of_team,
    first_value(seller) OVER w_recent AS first_in_recent_three
FROM window_lab.sales
WINDOW
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ),
    w_recent AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    )
ORDER BY team, sold_on, sale_id;
```

**Đáp án:** câu SQL vừa lấy last toàn nhóm, vừa lấy first trong ba giao dịch gần nhất mà không lặp dài phần định nghĩa frame.

## 31. Checklist trước khi dùng `first_value`, `last_value`, `nth_value` trong ứng dụng

| Câu hỏi | Điều cần xác định |
| --- | --- |
| “Đầu”, “cuối” theo tiêu chí nào? | Ngày, timestamp, giá, ID hay ưu tiên |
| Có phân vùng không? | `PARTITION BY` đúng khóa nghiệp vụ |
| Thứ tự có xác định duy nhất? | Thêm khóa phá hòa nếu có tie |
| Chỉ cần giá trị trong kỳ hay toàn lịch sử? | Vị trí của `WHERE` và lớp CTE |
| Muốn full partition hay running frame? | Chỉ định frame tường minh |
| Đang dùng mặc định `RANGE`? | Nhớ nó bao gồm peers ở cận CURRENT ROW |
| Mẫu có nhiều hàng cùng ngày? | Thử cả ROWS, RANGE, GROUPS khi phù hợp |
| Muốn n hàng hay n ngày? | ROWS khác RANGE và GROUPS |
| `nth_value` có thể không đủ hàng? | Xử lý NULL ở đầu kỳ hoặc nhóm nhỏ |
| Giá trị tại vị trí được chọn có thể NULL? | NULL không luôn đồng nghĩa thiếu hàng |
| Muốn bỏ qua NULL? | PostgreSQL không có `IGNORE NULLS`; dùng query riêng |
| Muốn nth từ cuối? | Đảo chiều sắp xếp đúng, kể cả tie breaker |
| Chỉ cần một hàng mỗi nhóm? | Cân nhắc `DISTINCT ON`/`ROW_NUMBER` |
| Muốn hàng trước/sau? | `LAG`/`LEAD` thường diễn đạt tốt hơn |
| ORDER BY ngoài SELECT đã đủ chưa? | Không: window cần ORDER BY riêng |
| Có nhiều frame trong một SELECT? | Đặt named windows có nghĩa |
| Có khung trượt ở biên phân vùng? | Số hàng thực có thể nhỏ hơn n |
| Có dùng collation/NULLS ordering? | Xác định thứ tự text và NULL |
| Có index đáp ứng partition + order? | Quan sát EXPLAIN, không đoán |
| Có chi phí sort/buffer lớn? | Đo trên dữ liệu và workload thực |
| Đã thử nhóm một hàng và nhóm có tie? | Những trường hợp này dễ lộ lỗi |
| Đã so output với yêu cầu nghiệp vụ? | Câu SQL chạy được chưa đủ chứng minh đúng |

## 32. Tổng kết

Ba hàm giá trị cửa sổ trong PostgreSQL có cùng nền tảng: **chọn giá trị từ một vị trí trong window frame**.

1. **`first_value(expression)`** đọc **hàng đầu frame**.
2. **`last_value(expression)`** đọc **hàng cuối frame**. Mặc định khi có `ORDER BY`, nó **không nhất thiết** là cuối của toàn phân vùng.
3. **`nth_value(expression, n)`** đọc **hàng thứ n từ đầu frame**, bắt đầu tại n = 1; trả NULL nếu không có đủ hàng hoặc giá trị tại vị trí đó là NULL.
4. **`PARTITION BY`** quyết định nhóm; **`ORDER BY` trong `OVER`** quyết định thứ tự; **frame** quyết định những hàng mà hàm nhìn thấy.
5. **Khung mặc định khi có `ORDER BY`** tương đương `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` và tính tới các **peer rows**.
6. Muốn **đầu/cuối/thứ n của toàn nhóm**, thường nên viết rõ `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`.
7. Muốn **giá trị trong ba giao dịch gần nhất**, dùng một khung `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`; khi đó first/nth trượt theo vị trí hiện tại.
8. **`ROWS`, `RANGE` và `GROUPS` không đồng nghĩa**: chúng đếm hàng, khoảng giá trị và nhóm peers khác nhau.
9. **ORDER BY phải đủ xác định** nếu muốn một hàng thứ n hay một hàng cuối ổn định. Khi có tie, thêm tiêu chí phá hòa có ý nghĩa.
10. PostgreSQL **không hỗ trợ `IGNORE NULLS`** cho các hàm này. Muốn giá trị đầu/cuối khác NULL, cần chọn hàng non-null theo cách khác.
11. Window functions **không tự giảm một nhóm thành một hàng**. Nếu cần top 1 per group, cân nhắc `DISTINCT ON` hoặc `ROW_NUMBER`.
12. **`WHERE` lọc trước khi window được tính** ở cùng query level. Nếu cần giá trị toàn lịch sử trên tập hàng hiển thị đã lọc, hãy tính ở CTE/subquery trước rồi lọc ngoài.

Mẫu an toàn dễ nhớ khi cần báo cáo đầu/cuối/thứ n của mỗi nhóm:

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER whole_group AS first_seller,
    last_value(seller)  OVER whole_group AS last_seller,
    nth_value(seller, 2) OVER whole_group AS second_seller
FROM window_lab.sales
WINDOW whole_group AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

**Quy tắc cốt lõi:** trước khi chọn `first_value`, `last_value` hoặc `nth_value`, hãy trả lời ba câu hỏi: **phân vùng nào, thứ tự nào và khung nào?** Chính câu trả lời thứ ba thường quyết định truy vấn trả đúng “đầu/cuối/thứ n” mà người dùng đang mong đợi.
