# GROUP BY một cột, nhiều cột và biểu thức

Trong cơ sở dữ liệu, mỗi dòng thường mô tả **một sự kiện hoặc một đối tượng cụ thể**: một đơn hàng, một lượt đăng nhập, một lần thanh toán. Nhưng câu hỏi nghiệp vụ thường cần nhìn dữ liệu ở một mức tổng quát hơn: **mỗi khu vực có bao nhiêu đơn**, **doanh thu theo khu vực và kênh bán**, hoặc **tổng giá trị giao dịch theo tháng**.

`GROUP BY` giúp chuyển từ các dòng chi tiết sang **những nhóm dòng có chung một khóa nhóm**, sau đó kết hợp với các hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN` và `MAX` để tạo ra kết quả **một dòng cho mỗi nhóm**.

Bài học thuộc chương **Tổng hợp dữ liệu** của Database SQL và tập trung vào ba cách định nghĩa nhóm:

1. **Một cột:** ví dụ `GROUP BY region`.
2. **Nhiều cột:** ví dụ `GROUP BY region, sales_channel`.
3. **Một hoặc nhiều biểu thức:** ví dụ nhóm theo tháng được tính từ `ordered_at`, hoặc theo giá trị đã chuẩn hóa của một cột.

Điểm quan trọng không chỉ là nhớ cú pháp. Bạn cần xác định đúng **một dòng kết quả đại diện cho gì**, biết cột nào được phép đặt trong `SELECT`, và tránh nhân bản dữ liệu trước khi tính tổng. Các ví dụ chủ yếu dùng **PostgreSQL**; những khác biệt đáng chú ý giữa hệ quản trị sẽ được ghi rõ.

## 1. Dữ liệu mẫu xuyên suốt

Giả sử cửa hàng có bảng `sales_orders`. **Mỗi dòng trong bảng là một đơn hàng**, xác định duy nhất bởi `order_id`.

| order_id | customer_id | region | sales_channel | ordered_at | status | amount (VND) |
|---:|---:|---|---|---|---|---:|
| 1001 | 1 | Hà Nội | Online | 2026-06-01 | PAID | 120000 |
| 1002 | 2 | Hà Nội | Store | 2026-06-01 | PAID | 80000 |
| 1003 | 3 | TP.HCM | Online | 2026-06-02 | PAID | 200000 |
| 1004 | 1 | Hà Nội | Online | 2026-06-02 | CANCELLED | 50000 |
| 1005 | 4 | TP.HCM | Store | 2026-06-03 | PAID | 150000 |
| 1006 | 5 | Đà Nẵng | Online | 2026-06-04 | PAID | 90000 |
| 1007 | 1 | Hà Nội | Online | 2026-07-01 | PAID | 220000 |
| 1008 | 3 | TP.HCM | Online | 2026-07-02 | PENDING | 70000 |
| 1009 | 5 | Đà Nẵng | Store | 2026-07-03 | PAID | 110000 |
| 1010 | 3 | TP.HCM | Online | 2026-07-04 | PAID | 300000 |
| 1011 | 2 | Hà Nội | Store | 2026-07-04 | PAID | 60000 |
| 1012 | 3 | TP.HCM | Online | 2026-07-05 | PAID | 200000 |

Từ bảng này:

- Có **12 đơn** tất cả.
- Có **10 đơn** mang trạng thái `PAID`; đơn `1004` bị hủy, `1008` đang chờ.
- Tổng `amount` của các đơn `PAID` là **1.530.000 VND**.
- Có ba vùng `region`, hai kênh `sales_channel` và hai tháng trong dữ liệu.

Nếu câu hỏi là “doanh thu đã thanh toán”, ví dụ quy ước chỉ tính đơn `PAID`. Trong hệ thống thực, doanh thu có thể còn phụ thuộc hoàn tiền, giảm giá và các quy tắc kế toán; bài học dùng mô hình nhỏ để tập trung vào `GROUP BY`.

## 2. Tư duy về độ hạt của kết quả

**Độ hạt** (*grain*) trả lời câu hỏi: **mỗi dòng đang biểu diễn một đối tượng hoặc một nhóm nào?**

```text
Bảng nguồn: mỗi dòng = một đơn hàng
                  │
                  ├── GROUP BY region
                  │      mỗi dòng kết quả = một vùng
                  │
                  ├── GROUP BY region, sales_channel
                  │      mỗi dòng kết quả = một cặp (vùng, kênh)
                  │
                  └── GROUP BY tháng(ordered_at)
                         mỗi dòng kết quả = một tháng
```

Khi không có `GROUP BY`, câu lệnh:

```sql
SELECT order_id, region, sales_channel, amount
FROM sales_orders
WHERE status = 'PAID'
ORDER BY order_id;
```

trả **10 dòng**, mỗi dòng là một đơn đã thanh toán.

Ngược lại:

```sql
SELECT region, COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY region;
```

trả **3 dòng**, mỗi dòng là một vùng. Các dòng chi tiết của từng vùng đã được gộp thành một nhóm để đếm.

> `GROUP BY` làm thay đổi độ hạt của kết quả. Trước khi viết `SELECT`, hãy nói thành lời: “Một dòng kết quả phải đại diện cho **một vùng**, **một vùng–kênh**, hay **một tháng**?”

## 3. Cú pháp tổng quát và thứ tự xử lý logic

Cú pháp phổ biến:

```sql
SELECT
    group_expression_1,
    group_expression_2,
    AGGREGATE_FUNCTION(measure_column) AS measure
FROM source_table
WHERE row_condition
GROUP BY group_expression_1, group_expression_2
HAVING group_condition
ORDER BY sort_expression;
```

Trong đó:

| Thành phần | Vai trò |
|---|---|
| `FROM` | Xác định nguồn dữ liệu |
| `WHERE` | Giữ lại những **dòng nguồn** thỏa điều kiện |
| `GROUP BY` | Tạo nhóm theo giá trị của một hay nhiều biểu thức |
| `COUNT`/`SUM`/`AVG`/`MIN`/`MAX` | Tính giá trị tổng hợp **bên trong từng nhóm** |
| `HAVING` | Lọc **nhóm** sau khi tính tổng hợp |
| `SELECT` | Chọn các khóa nhóm và các đại lượng tổng hợp để hiển thị |
| `ORDER BY` | Quy định thứ tự **dòng kết quả** |

Có thể đọc theo dòng xử lý logic gần đúng:

```text
FROM / JOIN
      ↓
WHERE                   lọc từng dòng
      ↓
GROUP BY                phân chia thành nhóm
      ↓
Tính các hàm tổng hợp   COUNT, SUM, AVG...
      ↓
HAVING                  lọc từng nhóm
      ↓
SELECT                  tạo cột đầu ra
      ↓
ORDER BY                sắp xếp các nhóm trả về
```

Đây là **mô hình hiểu ngữ nghĩa**, không phải thứ tự vật lý cố định. Bộ tối ưu của database có thể chọn nhiều thuật toán thực thi khác nhau mà vẫn phải bảo toàn kết quả theo yêu cầu truy vấn.

## 4. `GROUP BY` một cột

### 4.1. Đếm số đơn theo vùng

Yêu cầu: “Có bao nhiêu **đơn đã thanh toán** ở từng vùng?”

```sql
SELECT
    region,
    COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY region;
```

Kết quả (thứ tự chữ có thể thay đổi tùy collation):

| region | paid_order_count |
|---|---:|
| Hà Nội | 4 |
| TP.HCM | 4 |
| Đà Nẵng | 2 |

Một nhóm được tạo từ **mọi đơn `PAID` có cùng `region`**. Trong nhóm Hà Nội có các đơn `1001`, `1002`, `1007`, `1011`, nên `COUNT(*) = 4`.

Không cần và không nên viết vòng lặp để đếm từng vùng trong ứng dụng nếu cơ sở dữ liệu có thể thực hiện phép tổng hợp theo nhóm.

### 4.2. Tính tổng số tiền theo vùng

```sql
SELECT
    region,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY total_paid DESC, region ASC;
```

| region | paid_order_count | total_paid (VND) |
|---|---:|---:|
| TP.HCM | 4 | 850000 |
| Hà Nội | 4 | 480000 |
| Đà Nẵng | 2 | 200000 |

Điều kiện `WHERE status = 'PAID'` được áp dụng **trước khi nhóm**. Vì vậy, đơn hủy và đơn chờ **không được cộng** vào tổng tiền.

`SUM(amount)` không “cộng cột của toàn bảng” một cách mặc định: trong truy vấn có `GROUP BY region`, nó cộng **những dòng còn lại trong mỗi nhóm vùng**.

### 4.3. Các hàm tổng hợp thường dùng

```sql
SELECT
    region,
    COUNT(*) AS number_of_orders,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS smallest_order,
    MAX(amount) AS largest_order
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY region;
```

Với vùng TP.HCM: bốn số tiền là `200000`, `150000`, `300000`, `200000`, nên tổng là `850000`, trung bình là `212500`, nhỏ nhất `150000`, lớn nhất `300000`.

Các hàm trong một câu `SELECT` đều chạy trên **cùng tập dòng sau `WHERE` và cùng cấu trúc nhóm**, nhưng mỗi hàm có quy tắc tính riêng.

## 5. `GROUP BY` nhiều cột: mỗi tổ hợp giá trị là một nhóm

Giờ yêu cầu thay đổi: “Doanh thu đã thanh toán theo **từng vùng và từng kênh bán**.”

```sql
SELECT
    region,
    sales_channel,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, sales_channel
ORDER BY region, sales_channel;
```

Kết quả có sáu nhóm:

| region | sales_channel | paid_order_count | total_paid (VND) |
|---|---|---:|---:|
| Hà Nội | Online | 2 | 340000 |
| Hà Nội | Store | 2 | 140000 |
| TP.HCM | Online | 3 | 700000 |
| TP.HCM | Store | 1 | 150000 |
| Đà Nẵng | Online | 1 | 90000 |
| Đà Nẵng | Store | 1 | 110000 |

**Khóa nhóm ở đây là một cặp `(region, sales_channel)`**, không phải “gom riêng theo vùng rồi gom riêng theo kênh”. Chẳng hạn `(Hà Nội, Online)` gồm đơn `1001` và `1007`, khác với nhóm `(Hà Nội, Store)` gồm đơn `1002` và `1011`.

```text
Dòng PAID
├── Hà Nội
│   ├── Online → 1001, 1007
│   └── Store  → 1002, 1011
├── TP.HCM
│   ├── Online → 1003, 1010, 1012
│   └── Store  → 1005
└── Đà Nẵng
    ├── Online → 1006
    └── Store  → 1009
```

### 5.1. Thêm cột nhóm làm thay đổi độ hạt

So sánh:

```sql
-- Một nhóm trên mỗi vùng.
GROUP BY region

-- Một nhóm trên mỗi cặp (vùng, kênh).
GROUP BY region, sales_channel

-- Một nhóm trên mỗi bộ ba (vùng, kênh, trạng thái).
GROUP BY region, sales_channel, status
```

Về tổng thể, việc thêm cột vào khóa nhóm làm nhóm **cụ thể hơn**. Với cùng tập dòng đầu vào, số nhóm không giảm khi thêm một biểu thức phân nhóm, vì nhóm cũ có thể được chia nhỏ thành các nhóm con.

Tuy nhiên, **không nhất thiết xuất hiện mọi tổ hợp có thể có**. Nếu không có đơn `Store` tại một vùng, `GROUP BY` không tự tạo một nhóm `Store` có `COUNT = 0`. Nó chỉ tạo các nhóm tương ứng với giá trị **thực sự xuất hiện** sau khi lọc.

### 5.2. `GROUP BY a, b` không tạo tổng phụ theo từng `a`

```sql
SELECT region, sales_channel, SUM(amount)
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, sales_channel;
```

Truy vấn trên chỉ tạo số liệu cho từng cặp. Nó **không tự thêm** dòng “Tổng Hà Nội” hoặc “Tổng tất cả”.

Nếu cần tổng theo vùng, viết truy vấn riêng:

```sql
SELECT region, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region;
```

Hoặc cân nhắc `ROLLUP`/`GROUPING SETS` khi học đến tổng phụ và báo cáo nhiều cấp. Không nên suy diễn rằng `GROUP BY region, sales_channel` là một lệnh tổng hợp phân cấp tự động.

### 5.3. Thứ tự nhóm không được đảm bảo nếu không có `ORDER BY`

`GROUP BY region, sales_channel` **không hứa** sẽ trả các dòng theo đúng hai cột đó. Hệ quản trị có thể dùng bảng băm (*hash aggregation*), sắp xếp hoặc một kế hoạch khác.

Nếu báo cáo cần thứ tự:

```sql
ORDER BY region ASC, sales_channel ASC
```

Nếu muốn vùng có doanh thu cao nhất xuất hiện trước, cần sắp theo đại lượng tổng hợp:

```sql
ORDER BY SUM(amount) DESC, region ASC, sales_channel ASC
```

Các cột cuối giúp phân xử nếu hai nhóm có tổng bằng nhau. Trong nhiều hệ quản trị, cũng có thể dùng alias của biểu thức tổng hợp trong `ORDER BY`, như `ORDER BY total_paid DESC`.

## 6. `GROUP BY` biểu thức: định nghĩa nhóm theo giá trị tính được

Khóa nhóm không nhất thiết là một cột nguyên gốc. Nó có thể là **biểu thức** được tính từ dữ liệu đầu vào, ví dụ:

- Trích tháng/năm từ ngày đặt hàng.
- Chuẩn hóa mã khu vực bằng `LOWER` và `TRIM`.
- Chia số tiền thành nhóm nhỏ/vừa/lớn bằng `CASE`.
- Phân loại theo độ dài, tiền tố hoặc miền giá trị.

Điểm chung: **những dòng cho cùng giá trị biểu thức nhóm sẽ nằm cùng nhóm**.

### 6.1. Nhóm theo tháng với `DATE_TRUNC` trong PostgreSQL

Yêu cầu: “Tổng số tiền đã thanh toán theo từng tháng.”

```sql
SELECT
    DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY DATE_TRUNC('month', ordered_at::timestamp)::date
ORDER BY month_start;
```

Kết quả:

| month_start | paid_order_count | total_paid (VND) |
|---|---:|---:|
| 2026-06-01 | 5 | 640000 |
| 2026-07-01 | 5 | 890000 |

`DATE_TRUNC('month', ordered_at::timestamp)` đưa các ngày trong cùng tháng về **thời điểm đầu tháng**. Cast tiếp `::date` giúp hiển thị một ngày đại diện như `2026-06-01`; tất cả ngày trong tháng 6 có cùng khóa nhóm.

Trong ví dụ, cột `ordered_at` là `DATE`, nên cách viết tương đối đơn giản. Nếu dùng cột `TIMESTAMPTZ`, việc xác định “tháng nào” cần chỉ rõ **múi giờ của báo cáo**, bởi một thời điểm gần nửa đêm có thể rơi vào hai tháng khác nhau ở UTC và Việt Nam.

### 6.2. Nhóm theo năm và tháng bằng `EXTRACT`

Một cách khác là tách năm và tháng:

```sql
SELECT
    EXTRACT(YEAR FROM ordered_at) AS order_year,
    EXTRACT(MONTH FROM ordered_at) AS order_month,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY
    EXTRACT(YEAR FROM ordered_at),
    EXTRACT(MONTH FROM ordered_at)
ORDER BY order_year, order_month;
```

**Đừng chỉ nhóm theo tháng số 1–12** nếu dữ liệu có nhiều năm:

```sql
-- Sai nếu mục tiêu là mỗi tháng của mỗi năm:
SELECT EXTRACT(MONTH FROM ordered_at), COUNT(*)
FROM sales_orders
GROUP BY EXTRACT(MONTH FROM ordered_at);
```

Truy vấn trên sẽ trộn **tháng 6/2025** với **tháng 6/2026** vào cùng một nhóm số 6 nếu dữ liệu trải qua nhiều năm. Cần nhóm theo cả **năm + tháng**, hoặc dùng một khóa “ngày đầu tháng” bao gồm năm.

### 6.3. Nhóm theo thứ trong tuần

Ví dụ muốn đếm số đơn theo thứ trong tuần:

```sql
-- PostgreSQL: ISODOW trả 1=thứ Hai ... 7=Chủ nhật.
SELECT
    EXTRACT(ISODOW FROM ordered_at) AS weekday_number,
    COUNT(*) AS order_count
FROM sales_orders
GROUP BY EXTRACT(ISODOW FROM ordered_at)
ORDER BY weekday_number;
```

Đây là nhóm theo **thứ trong tuần**, không phải nhóm theo **mỗi ngày cụ thể**. Tất cả thứ Hai của nhiều tuần sẽ được gộp vào một nhóm. Chọn khóa nhóm nào tùy vào câu hỏi “số đơn theo thứ” hay “số đơn theo từng ngày”.

### 6.4. Nhóm theo biểu thức chuẩn hóa chuỗi

Giả sử hệ thống nhận tên kênh bán từ nhiều nguồn, có các giá trị `Online`, ` online `, `ONLINE`. Nếu nghiệp vụ coi chúng là cùng một kênh:

```sql
SELECT
    LOWER(BTRIM(sales_channel)) AS normalized_channel,
    COUNT(*) AS order_count
FROM sales_orders
GROUP BY LOWER(BTRIM(sales_channel))
ORDER BY normalized_channel;
```

`BTRIM` bỏ khoảng trắng ở hai đầu trong PostgreSQL; `LOWER` đổi thành chữ thường theo quy tắc văn bản của môi trường. Các bản ghi có **cùng kết quả sau chuẩn hóa** sẽ vào một nhóm.

Lưu ý: tên kênh mẫu hiện tại đã thống nhất, nên truy vấn trên chỉ minh họa kỹ thuật. Với dữ liệu thực, tốt hơn là chuẩn hóa/kiểm tra tại đầu vào và lưu **mã kênh ổn định**, thay vì mỗi báo cáo tự đoán quy tắc tương đương của chuỗi.

### 6.5. Nhóm theo `CASE`: tạo dải giá trị

Yêu cầu: “Đếm đơn đã thanh toán theo ba nhóm số tiền: dưới 100.000, từ 100.000 đến dưới 200.000, và từ 200.000 trở lên.”

```sql
SELECT
    CASE
        WHEN amount < 100000 THEN 'under_100k'
        WHEN amount < 200000 THEN '100k_to_under_200k'
        ELSE '200k_or_more'
    END AS amount_band,
    COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY
    CASE
        WHEN amount < 100000 THEN 'under_100k'
        WHEN amount < 200000 THEN '100k_to_under_200k'
        ELSE '200k_or_more'
    END
ORDER BY amount_band;
```

Theo dữ liệu mẫu:

| amount_band | paid_order_count |
|---|---:|
| `under_100k` | 3 |
| `100k_to_under_200k` | 3 |
| `200k_or_more` | 4 |

Các nhóm không chồng nhau: giá trị đúng bằng 100.000 thuộc nhóm thứ hai; đúng bằng 200.000 thuộc nhóm thứ ba.

Trong bài, `amount` được khai báo `NOT NULL`. Nếu cột có thể là `NULL`, `ELSE '200k_or_more'` sẽ vô tình đưa giá trị thiếu vào nhóm lớn nhất. Khi đó nên thêm nhánh `WHEN amount IS NULL THEN 'unknown'` **trước** các điều kiện so sánh.

### 6.6. Tránh lặp biểu thức dài bằng CTE

Lặp lại cùng biểu thức `CASE` ở `SELECT` và `GROUP BY` có thể khó bảo trì. Ta có thể tạo cột dẫn xuất trước bằng CTE (`WITH`):

```sql
WITH classified AS (
    SELECT
        order_id,
        CASE
            WHEN amount < 100000 THEN 'under_100k'
            WHEN amount < 200000 THEN '100k_to_under_200k'
            ELSE '200k_or_more'
        END AS amount_band
    FROM sales_orders
    WHERE status = 'PAID'
)
SELECT amount_band, COUNT(*) AS paid_order_count
FROM classified
GROUP BY amount_band
ORDER BY amount_band;
```

CTE ở đây tạo một tên biểu thức rõ nghĩa để câu tổng hợp dễ đọc. Nó **không tự bảo đảm** truy vấn nhanh hơn: cách tối ưu hóa CTE tùy hệ quản trị, phiên bản và cấu trúc truy vấn.

## 7. Kết hợp nhiều cột và biểu thức

Câu hỏi: “Trong mỗi vùng, doanh thu từng tháng là bao nhiêu?”

```sql
SELECT
    region,
    DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY
    region,
    DATE_TRUNC('month', ordered_at::timestamp)::date
ORDER BY region, month_start;
```

Kết quả:

| region | month_start | paid_order_count | total_paid |
|---|---|---:|---:|
| Hà Nội | 2026-06-01 | 2 | 200000 |
| Hà Nội | 2026-07-01 | 2 | 280000 |
| TP.HCM | 2026-06-01 | 2 | 350000 |
| TP.HCM | 2026-07-01 | 2 | 500000 |
| Đà Nẵng | 2026-06-01 | 1 | 90000 |
| Đà Nẵng | 2026-07-01 | 1 | 110000 |

Mỗi dòng là **một cặp `(region, month_start)`**. Một nhóm không đại diện cho “mọi tháng của vùng” hay “mọi vùng của tháng”, mà cho chính tổ hợp đó.

Nếu thêm `sales_channel`:

```sql
GROUP BY
    region,
    sales_channel,
    DATE_TRUNC('month', ordered_at::timestamp)::date
```

độ hạt trở thành **một vùng × một kênh × một tháng**, tạo nhiều nhóm chi tiết hơn. Chỉ nên thêm khóa nhóm khi kết quả cần mức phân rã đó; nếu không, số liệu báo cáo sẽ bị chia quá nhỏ.

### 7.1. Một dấu hiệu của sai độ hạt

Giả sử đề bài hỏi **doanh thu mỗi vùng**, nhưng truy vấn lại:

```sql
SELECT region, customer_id, SUM(amount)
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, customer_id;
```

Kết quả không còn một dòng trên mỗi vùng; mỗi khách trong vùng tạo nhóm riêng. Câu SQL có thể hợp lệ nhưng **không trả đúng cấu trúc mà đề bài cần**.

Trước khi viết `GROUP BY`, nên xác định danh sách khóa nhóm bằng một câu hoàn chỉnh:

> “Mỗi dòng kết quả là **một vùng**” → nhóm chỉ theo vùng.

> “Mỗi dòng kết quả là **một vùng trong một tháng**” → nhóm theo vùng và biểu thức tháng.

## 8. Quy tắc cột trong `SELECT` khi có `GROUP BY`

Một câu hỏi phổ biến: vì sao truy vấn này sai trong PostgreSQL?

```sql
-- Không hợp lệ trong PostgreSQL:
SELECT region, order_id, SUM(amount)
FROM sales_orders
GROUP BY region;
```

Một nhóm vùng có thể chứa **nhiều `order_id`**. Khi trả một dòng đại diện cho vùng, hệ quản trị không biết `order_id` nào phải được đặt vào kết quả. Do đó, theo quy tắc tổng hợp, một biểu thức trong `SELECT` thường phải thuộc một trong các loại:

1. **Biểu thức khóa nhóm** hoặc biểu thức được xác định từ các khóa nhóm theo quy tắc của hệ quản trị.
2. **Biểu thức tổng hợp** như `COUNT(*)`, `SUM(amount)`, `MIN(order_id)`.
3. **Hằng số hoặc biểu thức không phụ thuộc dòng chi tiết**.

Sửa câu hỏi theo đúng ý nghĩa:

```sql
-- Muốn một dòng trên mỗi vùng, không chọn order_id của từng đơn.
SELECT region, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM sales_orders
GROUP BY region;
```

Hoặc nếu **một dòng phải là một vùng–đơn**:

```sql
SELECT region, order_id, SUM(amount) AS total_amount
FROM sales_orders
GROUP BY region, order_id;
```

Nhưng truy vấn sau về thực chất nhóm ở độ hạt đơn, vì `order_id` duy nhất, nên `SUM(amount)` của mỗi nhóm chỉ là số tiền của một đơn. Điều đó thường không đáp ứng mục tiêu “tổng theo vùng”.

### 8.1. Phụ thuộc hàm và ngoại lệ theo hệ quản trị

Một số hệ quản trị cho phép chọn một cột chưa viết tường minh trong `GROUP BY` khi cột đó **phụ thuộc hàm** vào khóa nhóm. Ví dụ PostgreSQL có thể nhận ra phụ thuộc khi nhóm theo **khóa chính của bảng gốc**. Tuy nhiên, khả năng nhận dạng phụ thuộc hàm thay đổi giữa PostgreSQL, MySQL, các truy vấn con và các hệ quản trị khác.

Khi học hoặc viết SQL cần dễ chuyển hệ, cách trực tiếp là **nhóm theo tất cả những thuộc tính không tổng hợp cần hiển thị**, trừ khi bạn chủ động dùng một ngoại lệ có căn cứ từ schema và hệ quản trị. Không nên dựa vào chế độ MySQL cho phép chọn tùy tiện một giá trị không thuộc nhóm, vì kết quả có thể không có ý nghĩa xác định.

### 8.2. `SELECT *` thường không phù hợp khi nhóm

```sql
-- Không hợp lệ/không đúng ý nghĩa cho GROUP BY region:
SELECT *
FROM sales_orders
GROUP BY region;
```

`SELECT *` yêu cầu mọi cột chi tiết, nhưng một dòng nhóm không có một giá trị duy nhất cho `order_id`, `customer_id`, `ordered_at`... Hãy liệt kê rõ **khóa nhóm và đại lượng tổng hợp**.

### 8.3. Bí danh trong `GROUP BY`

PostgreSQL cho phép dùng alias của biểu thức `SELECT` trong `GROUP BY` ở một số ngữ cảnh:

```sql
SELECT
    DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
    COUNT(*) AS orders_count
FROM sales_orders
GROUP BY month_start;
```

Tuy nhiên, hỗ trợ alias và cách giải quyết **tên trùng với cột nguồn** khác nhau giữa các hệ. Dùng lại biểu thức hoặc tách CTE thường minh bạch hơn khi viết bài học muốn di động. `GROUP BY 1` (nhóm theo vị trí cột đầu trong `SELECT`) cũng được một số hệ hỗ trợ, nhưng dễ gây lỗi khi thay đổi thứ tự cột đầu ra.

## 9. `WHERE` và `HAVING`: lọc dòng hay lọc nhóm?

Giả sử yêu cầu: “Những vùng nào có **tổng tiền `PAID` ít nhất 400.000 VND**?”

```sql
SELECT
    region,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
HAVING SUM(amount) >= 400000
ORDER BY total_paid DESC;
```

Kết quả:

| region | total_paid |
|---|---:|
| TP.HCM | 850000 |
| Hà Nội | 480000 |

`WHERE` lọc các **đơn** không `PAID` trước khi cộng. `HAVING` lọc các **vùng** có tổng dưới 400.000 sau khi đã cộng.

### 9.1. Không đặt hàm tổng hợp trực tiếp vào `WHERE`

```sql
-- Sai:
SELECT region, SUM(amount)
FROM sales_orders
WHERE SUM(amount) >= 400000
GROUP BY region;
```

`WHERE` dùng khi chưa có nhóm, vì vậy không thể lọc bằng giá trị `SUM(amount)` của nhóm ở giai đoạn này.

### 9.2. Các câu hỏi nghe gần giống nhưng khác kết quả

**Câu A:** “Vùng có tổng tiền `PAID` từ 400.000 trở lên.”

```sql
WHERE status = 'PAID'
GROUP BY region
HAVING SUM(amount) >= 400000
```

**Câu B:** “Vùng có ít nhất hai **đơn lớn từ 200.000 trở lên** đã thanh toán.”

```sql
SELECT region, COUNT(*) AS large_paid_orders
FROM sales_orders
WHERE status = 'PAID'
  AND amount >= 200000
GROUP BY region
HAVING COUNT(*) >= 2;
```

Ở câu B, **mỗi đơn** được kiểm tra có đạt ngưỡng 200.000 hay không *trước khi đếm nhóm*. Đó không phải câu “vùng có tổng doanh thu 200.000”.

**Câu C:** “Vùng có **trên ba đơn `PAID`**.”

```sql
SELECT region, COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
HAVING COUNT(*) > 3;
```

Kết quả là Hà Nội và TP.HCM, mỗi vùng có 4 đơn `PAID`. Nhìn vào yêu cầu “từng dòng” hay “từng nhóm” giúp đặt điều kiện đúng.

## 10. `COUNT(*)`, `COUNT(column)` và `COUNT(DISTINCT ...)`

### 10.1. Ba phép đếm có ý nghĩa khác nhau

| Biểu thức | Đếm gì? |
|---|---|
| `COUNT(*)` | Mọi dòng của nhóm, kể cả dòng có cột `NULL` |
| `COUNT(column)` | Dòng có `column` **không `NULL`** |
| `COUNT(DISTINCT column)` | Số **giá trị khác nhau và không `NULL`** của cột trong nhóm |

Ví dụ “số khách hàng khác nhau đã mua ở mỗi vùng”:

```sql
SELECT
    region,
    COUNT(*) AS paid_order_count,
    COUNT(DISTINCT customer_id) AS distinct_buyers
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | paid_order_count | distinct_buyers |
|---|---:|---:|
| Hà Nội | 4 | 2 |
| TP.HCM | 4 | 2 |
| Đà Nẵng | 2 | 1 |

Hà Nội có 4 **đơn**, nhưng chỉ 2 **khách** (`customer_id` 1 và 2). TP.HCM có 4 đơn, nhưng chỉ 2 khách (3 và 4). Đà Nẵng có hai đơn cùng khách 5.

Nếu yêu cầu là “số người mua”, `COUNT(*)` sau khi nhóm theo vùng **không tự biến thành số người**. Phải hiểu độ hạt nguồn là đơn hàng và dùng `COUNT(DISTINCT customer_id)` khi cần đếm khách duy nhất.

### 10.2. `SUM(DISTINCT amount)` không phải cách chữa nhân đôi đơn hàng

Giả sử hai đơn khác nhau đều có `amount = 200000`. `SUM(DISTINCT amount)` chỉ cộng **một lần giá trị 200000** trong mỗi nhóm, dù có nhiều đơn thực có cùng số tiền.

```sql
SELECT
    SUM(amount) AS actual_total,
    SUM(DISTINCT amount) AS distinct_amount_values_total
FROM sales_orders
WHERE status = 'PAID'
  AND region = 'TP.HCM';
```

Với dữ liệu mẫu:

- `SUM(amount) = 850000`: cộng đủ bốn đơn TP.HCM.
- `SUM(DISTINCT amount) = 650000`: chỉ cộng các **giá trị số tiền khác nhau** `150000 + 200000 + 300000`.

Như vậy, `DISTINCT` bên trong `SUM` không có nghĩa “mỗi đơn chỉ cộng một lần”; nó có nghĩa “mỗi **giá trị** số tiền chỉ cộng một lần”.

## 11. `NULL` trong khóa nhóm và trong đại lượng tổng hợp

### 11.1. Các dòng có khóa nhóm `NULL` được gom cùng nhóm

Nếu bảng `sales_orders` có thêm các đơn mà `region IS NULL`, `GROUP BY region` sẽ gom các dòng thiếu vùng thành **một nhóm với khóa `NULL`**. Mặc dù phép so sánh `NULL = NULL` thông thường cho `UNKNOWN`, ngữ nghĩa phân nhóm trong SQL coi các giá trị `NULL` như thuộc cùng một nhóm để tổng hợp.

```sql
SELECT
    region,
    COUNT(*) AS order_count
FROM sales_orders
GROUP BY region;
```

Nếu dữ liệu có nhiều dòng `region = NULL`, chúng góp vào một dòng kết quả có `region = NULL`. Điều này **không có nghĩa** `NULL` là một vùng địa lý thật.

### 11.2. Hiển thị nhãn cho nhóm thiếu

```sql
SELECT
    COALESCE(region, 'Chưa xác định') AS region_label,
    COUNT(*) AS order_count
FROM sales_orders
GROUP BY COALESCE(region, 'Chưa xác định')
ORDER BY region_label;
```

Biểu thức `COALESCE` tạo tên hiển thị cho nhóm thiếu. Tuy nhiên, nếu `'Chưa xác định'` cũng có thể là một **giá trị thật** trong cột `region`, cách nhóm bằng `COALESCE` sẽ nhập hai trường hợp lại. Khi cần giữ khác biệt, hãy nhóm theo cột gốc `region` rồi dùng nhãn trình bày riêng.

### 11.3. Các hàm tổng hợp và `NULL`

Với các đại lượng thông thường:

- `COUNT(*)` đếm cả dòng có `NULL`.
- `COUNT(amount)` chỉ đếm số dòng có `amount` không `NULL`.
- `SUM(amount)`, `AVG(amount)`, `MIN(amount)`, `MAX(amount)` bỏ qua giá trị `NULL` của cột nguồn.
- Nếu một nhóm không có giá trị `amount` khác `NULL`, `SUM(amount)` và `AVG(amount)` trả `NULL`, còn `COUNT(amount)` trả 0.

```sql
SELECT
    region,
    COUNT(*) AS all_rows,
    COUNT(amount) AS rows_with_amount,
    SUM(amount) AS total_known_amount
FROM sales_orders
GROUP BY region;
```

Trong bảng mẫu, `amount` là `NOT NULL`, nên `COUNT(*)` và `COUNT(amount)` bằng nhau; phần giải thích ở đây dành cho dữ liệu thực có trường được phép thiếu.

Không nên tự thay mọi `NULL` thành 0 trước khi tính `AVG`: nếu 0 nghĩa là **không có doanh thu**, nó có thể được tính vào trung bình; nếu `NULL` nghĩa là **chưa biết**, đưa 0 vào sẽ làm sai mẫu số.

## 12. `GROUP BY` với `JOIN`: tránh nhân dữ liệu khi tính tổng

Một trong những lỗi nguy hiểm nhất là **đổi độ hạt của dữ liệu khi nối bảng** rồi vẫn tính tổng như thể mỗi dòng là một đơn.

Giả sử thêm bảng `order_items`, trong đó mỗi đơn có nhiều dòng sản phẩm:

| order_id | item_id | quantity |
|---:|---:|---:|
| 1001 | 1 | 1 |
| 1001 | 2 | 2 |
| 1002 | 3 | 1 |

Trong `sales_orders`, đơn `1001` chỉ là **một dòng** với `amount = 120000`. Sau khi:

```sql
SELECT
    o.order_id,
    o.amount,
    i.item_id
FROM sales_orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
```

đơn `1001` sẽ xuất hiện **hai dòng**, do có hai sản phẩm. Khi đó, truy vấn sau **sai nếu mục tiêu là tổng giá trị mỗi đơn một lần**:

```sql
-- Sai về độ hạt nếu muốn cộng tổng tiền đơn:
SELECT
    o.region,
    SUM(o.amount) AS total_amount
FROM sales_orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.region;
```

`SUM(o.amount)` sẽ cộng `120000` của đơn `1001` **hai lần**. Dùng `SUM(DISTINCT o.amount)` cũng không sửa đúng tổng, vì hai đơn hợp lệ có cùng số tiền sẽ bị nhập thành một giá trị.

### 12.1. Chọn nguồn đúng độ hạt

Nếu số tiền đã nằm ở bảng **đơn hàng**, và không cần lọc theo sản phẩm, hãy tổng hợp trực tiếp bảng `sales_orders`:

```sql
SELECT region, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region;
```

### 12.2. Khi phải `JOIN`, tổng hợp ở độ hạt đúng trước

Nếu dữ liệu giá tiền nằm ở bảng chi tiết, hãy tính tổng **mỗi đơn một lần** trước khi tính theo vùng. Giả sử `order_items` có cột `line_amount` biểu diễn giá trị của **một dòng sản phẩm**:

```sql
WITH per_order_amount AS (
    SELECT
        order_id,
        SUM(line_amount) AS order_amount
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.region,
    SUM(p.order_amount) AS total_paid
FROM sales_orders AS o
JOIN per_order_amount AS p
    ON p.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.region;
```

`per_order_amount` trả một dòng trên mỗi `order_id`, nên khi nối với bảng đơn (một dòng trên mỗi đơn), không còn nhân tiền theo số dòng sản phẩm. Ví dụ này minh họa thiết kế truy vấn khi bảng `order_items` có `line_amount`; bảng đó không nằm trong script tạo dữ liệu mẫu ở cuối bài.

### 12.3. `LEFT JOIN` và `COUNT(*)`

Giả sử cần “số đơn đã thanh toán của **từng khách**, kể cả người không có đơn”. Khi dùng bảng khách `customers` ở phía trái của `LEFT JOIN`, mỗi khách không có đơn phù hợp vẫn tồn tại một dòng có các cột phía đơn là `NULL`.

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS total_paid
FROM customers AS c
LEFT JOIN sales_orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Điểm đáng chú ý:

1. `COUNT(o.order_id)` đếm những đơn thực sự khớp; khách không có đơn `PAID` sẽ có số đếm 0.
2. `COUNT(*)` trong `LEFT JOIN` có thể trả 1 cho khách không khớp đơn nào, vì dòng khách vẫn được giữ.
3. Điều kiện `o.status = 'PAID'` ở `ON` giúp giữ khách không có đơn thanh toán; nếu chuyển nó sang `WHERE`, các dòng không khớp có thể bị loại.
4. `COALESCE(SUM(o.amount), 0)` biểu diễn tổng bằng 0 khi không có đơn phù hợp, theo quy tắc nghiệp vụ của ví dụ.

Trong bài toán này, bảng `customers` được giả định có khóa chính `customer_id` và cột `full_name`, nhưng không cần tạo nó để chạy các ví dụ nhóm theo `sales_orders`.

## 13. Nhóm không có dòng, nhóm rỗng và tổng toàn bảng

`GROUP BY` tạo nhóm từ **những khóa xuất hiện** trong đầu vào. Nếu sau `WHERE` không còn dòng nào:

```sql
SELECT region, COUNT(*) AS n
FROM sales_orders
WHERE status = 'UNKNOWN_STATUS'
GROUP BY region;
```

truy vấn trả **0 dòng**, vì không có vùng nào để tạo nhóm.

Tuy nhiên, phép tổng hợp **không có `GROUP BY`** có thể trả một dòng đại diện cho **toàn bộ đầu vào**, kể cả khi đầu vào rỗng:

```sql
SELECT
    COUNT(*) AS n,
    SUM(amount) AS total_amount
FROM sales_orders
WHERE status = 'UNKNOWN_STATUS';
```

Trong PostgreSQL, truy vấn này trả **một dòng**: `n = 0`, `total_amount = NULL`. `COUNT(*)` trên tập rỗng là 0, còn `SUM` trên tập không có giá trị để cộng trả `NULL`.

Khi cần giá trị 0 trong báo cáo, có thể:

```sql
SELECT
    COUNT(*) AS n,
    COALESCE(SUM(amount), 0) AS total_amount
FROM sales_orders
WHERE status = 'UNKNOWN_STATUS';
```

Nhưng chỉ dùng 0 khi quy ước báo cáo coi “không có giao dịch” là tổng tiền 0; với dữ liệu thiếu hoặc không xác định, `NULL` vẫn mang ý nghĩa khác.

### 13.1. Muốn hiện các nhóm không có giao dịch cần nguồn nhóm độc lập

Nếu cửa hàng muốn bảng báo cáo gồm **mọi vùng đã đăng ký**, kể cả vùng chưa có đơn, `GROUP BY` trực tiếp bảng đơn sẽ không tạo được vùng chưa từng xuất hiện.

Khi đó cần bảng danh mục vùng (`regions`) và `LEFT JOIN`, hoặc một tập giá trị vùng đã được định nghĩa:

```sql
WITH regions(region) AS (
    VALUES ('Hà Nội'), ('TP.HCM'), ('Đà Nẵng'), ('Cần Thơ')
)
SELECT
    r.region,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS total_paid
FROM regions AS r
LEFT JOIN sales_orders AS o
    ON o.region = r.region
   AND o.status = 'PAID'
GROUP BY r.region
ORDER BY r.region;
```

Kết quả thêm `Cần Thơ` với 0 đơn và 0 tiền. CTE `VALUES` dùng để minh họa; trong hệ thống thật, danh mục vùng nên được quản lý như dữ liệu có nguồn rõ ràng.

## 14. `GROUP BY` so với `DISTINCT` và hàm cửa sổ

### 14.1. Chỉ cần danh sách giá trị duy nhất?

Nếu muốn biết các vùng hiện có:

```sql
SELECT DISTINCT region
FROM sales_orders
ORDER BY region;
```

Đây là truy vấn **loại các giá trị trùng**, không yêu cầu tính tổng hợp. Có thể viết:

```sql
SELECT region
FROM sales_orders
GROUP BY region
ORDER BY region;
```

Hai truy vấn có thể cho cùng danh sách vùng. Nhưng `DISTINCT` thường diễn đạt mục tiêu “giá trị không lặp” rõ ràng hơn; `GROUP BY` phù hợp khi cần **tính toán theo nhóm**.

### 14.2. `GROUP BY` làm giảm số dòng, hàm cửa sổ giữ độ hạt

Giả sử muốn hiển thị **mỗi đơn** cùng tổng tiền `PAID` của **vùng chứa đơn đó**. Nếu dùng `GROUP BY region`, các dòng đơn bị gộp lại. Có thể dùng hàm cửa sổ:

```sql
SELECT
    order_id,
    region,
    amount,
    SUM(amount) OVER (PARTITION BY region) AS region_total
FROM sales_orders
WHERE status = 'PAID'
ORDER BY region, order_id;
```

Truy vấn này vẫn trả **một dòng trên mỗi đơn `PAID`**, đồng thời lặp giá trị tổng vùng bên cạnh từng đơn. `PARTITION BY region` phân nhóm để **tính cửa sổ** nhưng không gộp đầu ra thành một dòng trên mỗi vùng.

Phân biệt:

| Truy vấn | Độ hạt đầu ra |
|---|---|
| `GROUP BY region` + `SUM(amount)` | Một dòng trên mỗi vùng |
| `SUM(amount) OVER (PARTITION BY region)` | Một dòng trên mỗi đơn đầu vào |

Chọn `GROUP BY` hay hàm cửa sổ dựa trên **độ hạt kết quả mong muốn**, không chỉ dựa vào việc cả hai đều tính được tổng vùng.

## 15. Nhóm theo thời gian và múi giờ

Với dữ liệu thực có `TIMESTAMPTZ` (PostgreSQL), một thời điểm gần nửa đêm UTC có thể thuộc **tháng khác** ở Việt Nam. Nếu yêu cầu “doanh thu theo tháng ở Việt Nam”, phải dùng khóa nhóm theo tháng **sau khi chuyển sang múi giờ nghiệp vụ**.

Giả sử bảng `payments` có cột `paid_at TIMESTAMPTZ`, `amount` và `status`:

```sql
SELECT
    DATE_TRUNC(
        'month',
        paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS vietnam_month_start,
    COUNT(*) AS paid_count,
    SUM(amount) AS paid_total
FROM payments
WHERE status = 'PAID'
GROUP BY DATE_TRUNC(
    'month',
    paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
)::date
ORDER BY vietnam_month_start;
```

`paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh'` tạo giá trị `TIMESTAMP` **giờ địa phương Việt Nam** từ một thời điểm xác định; `DATE_TRUNC('month', ...)` đưa nó về đầu tháng trong lịch Việt Nam. Như vậy nhóm tháng không phụ thuộc `TimeZone` của phiên SQL.

Nếu cột là `DATE` và đã chứa ngày nghiệp vụ đúng ngay từ đầu, có thể nhóm theo ngày/tháng mà không cần bước chuyển múi giờ này.

### 15.1. Ngày lịch và tháng lịch không phải khoảng giây cố định

Không nên chia Unix timestamp cho một số giây “tháng trung bình” rồi gọi đó là tháng, vì tháng có 28–31 ngày. Khi doanh nghiệp yêu cầu nhóm theo **tháng lịch**, hãy dùng phép trích tháng/năm hoặc `DATE_TRUNC` trên ngày giờ theo đúng vùng.

### 15.2. Thời điểm và khóa nhóm

Chọn khóa nhóm theo thời gian phải nêu rõ:

- **Ngày nào?** Theo UTC hay một vùng như `Asia/Ho_Chi_Minh`?
- **Đơn vị nào?** Ngày, tuần, tháng, quý, năm hay khoảng 15 phút?
- **Tuần bắt đầu khi nào?** Theo chuẩn ISO hay quy tắc doanh nghiệp?
- **Dữ liệu có cập nhật muộn không?** Đơn xảy ra hôm trước nhưng được nhập hôm sau có được nhóm theo ngày xảy ra hay ngày ghi nhận?

Những lựa chọn này tác động trực tiếp đến số liệu dù cú pháp tổng hợp hoàn toàn hợp lệ.

## 16. Hiệu năng: chỉ mục, biểu thức và số nhóm

`GROUP BY` có thể dùng nhiều chiến lược thực thi, như **hash aggregation** hoặc **sort/group aggregation**. Hệ quản trị lựa chọn dựa trên thống kê, lượng dữ liệu, bộ nhớ, chỉ mục và các điều kiện truy vấn.

### 16.1. Lọc sớm đúng về ngữ nghĩa

Nếu báo cáo chỉ xét đơn `PAID` tháng 6:

```sql
SELECT
    region,
    SUM(amount) AS paid_total
FROM sales_orders
WHERE status = 'PAID'
  AND ordered_at >= DATE '2026-06-01'
  AND ordered_at <  DATE '2026-07-01'
GROUP BY region;
```

`WHERE` loại các đơn khác trạng thái và khác tháng **trước khi nhóm**, nên thường giảm số dòng phải tổng hợp. Khoảng ngày nửa mở `[2026-06-01, 2026-07-01)` cũng diễn đạt tháng 6 rõ ràng và phù hợp khi chuyển sang cột có giờ.

### 16.2. Nhóm theo biểu thức có chi phí riêng

```sql
GROUP BY DATE_TRUNC('month', ordered_at::timestamp)::date
```

Hệ quản trị phải tính biểu thức tháng để tạo khóa nhóm. Với dữ liệu lớn và báo cáo lặp lại thường xuyên, có thể xem xét thiết kế cột dẫn xuất (*generated column*, nếu hệ quản trị hỗ trợ và biểu thức hợp lệ), chỉ mục biểu thức hoặc bảng tổng hợp được cập nhật theo quy tắc rõ ràng.

Không nên tạo ngay nhiều cột tổng hợp hoặc chỉ mục chỉ vì có `GROUP BY`. Trước tiên hãy xác nhận **độ hạt đúng**, dùng `EXPLAIN`/`EXPLAIN ANALYZE` và quan sát dữ liệu thực.

### 16.3. Số nhóm quyết định kích thước kết quả

Nhóm theo `region` của hàng triệu đơn có thể chỉ tạo vài nhóm. Nhóm theo một khóa gần như duy nhất như `order_id` lại tạo gần bằng số dòng nguồn. Việc chọn thêm những cột rất chi tiết không chỉ thay đổi báo cáo mà còn thay đổi nhu cầu bộ nhớ/tài nguyên khi tổng hợp.

### 16.4. Dùng kiểu đúng từ đầu

Nếu số tiền đang được lưu dạng `TEXT`, mọi báo cáo phải cast trước khi `SUM`, tiềm ẩn lỗi dữ liệu sai và chi phí chuyển đổi. Nếu ngày giờ được lưu dạng chuỗi không thống nhất, việc nhóm theo tháng cũng khó chính xác. Nên thiết kế cột `amount` là `NUMERIC` thích hợp và `ordered_at` là kiểu thời gian đúng ngữ nghĩa từ khi lưu dữ liệu.

## 17. Lỗi thường gặp khi dùng `GROUP BY`

| Biểu hiện | Nguyên nhân | Cách xác định lại |
|---|---|---|
| `GROUP BY region` mà chọn `order_id` | Một vùng có nhiều mã đơn; cột không được nhóm/tổng hợp | Bỏ cột chi tiết hoặc đổi độ hạt đầu ra |
| Muốn tổng vùng nhưng nhóm cả `customer_id` | Đã chia vùng thành các nhóm theo khách | Nhóm đúng khóa nghiệp vụ |
| `GROUP BY region, channel` được hiểu là hai báo cáo riêng | Nhầm nhóm theo tổ hợp với các nhóm độc lập | Mỗi dòng là một **cặp vùng–kênh** |
| Đếm đơn hủy vào doanh thu đã thanh toán | Quên `WHERE status = 'PAID'` | Lọc dòng trước khi tổng hợp |
| Dùng `WHERE SUM(amount) > ...` | `WHERE` không lọc nhóm | Dùng `HAVING SUM(amount) > ...` |
| Nhóm theo `MONTH(date)` mà không có năm | Trộn dữ liệu tháng cùng số qua nhiều năm | Nhóm cả năm và tháng hoặc ngày đầu tháng |
| Muốn có vùng không phát sinh đơn nhưng không thấy | `GROUP BY` chỉ tạo nhóm có dữ liệu đầu vào | Bắt đầu từ bảng danh mục vùng và `LEFT JOIN` |
| `SUM(amount)` tăng bất thường sau `JOIN` | Nối một-nhiều làm lặp giá trị đơn | Tổng hợp ở độ hạt phù hợp trước khi nối |
| Dùng `SUM(DISTINCT amount)` để sửa dòng lặp | Hai đơn thật có thể cùng số tiền | Giải quyết quan hệ JOIN và độ hạt |
| `COUNT(*)` trên `LEFT JOIN` cho 1 khi không có đơn | Dòng phía trái vẫn tồn tại | Dùng `COUNT(right_table.primary_key)` |
| `COUNT(*)` được hiểu là số người mua | Bảng nguồn là đơn hàng, không phải khách | Dùng `COUNT(DISTINCT customer_id)` |
| Nhóm có `NULL` bị hiểu là nhóm giá trị thật | `NULL` được gom cùng nhóm | Phân biệt nhóm thiếu và danh mục có giá trị thật |
| Trông kết quả có vẻ đã được sắp dù thiếu `ORDER BY` | Thứ tự truy vấn không được bảo đảm | Viết `ORDER BY` trên kết quả cuối |
| Nhóm `TIMESTAMPTZ` theo ngày nhưng lệch giữa hai máy | Múi giờ phiên khác nhau | Cố định múi giờ nghiệp vụ trong biểu thức nhóm |
| Muốn giữ mọi dòng chi tiết và thêm tổng nhóm | `GROUP BY` gộp mất dòng nguồn | Cân nhắc hàm cửa sổ với `OVER (PARTITION BY ...)` |

## 18. Script tạo dữ liệu mẫu trong PostgreSQL

Để chạy các truy vấn trước đó, có thể tạo **bảng tạm** `sales_orders` trong một phiên PostgreSQL riêng. Bảng tạm tự xóa khi kết nối kết thúc. Nếu hệ thống đã có bảng thật cùng tên, một bảng tạm cùng tên có thể được ưu tiên khi truy vấn không ghi schema; nên chạy trong môi trường thực hành hoặc đổi tên thành `group_by_lab_orders`.

```sql
CREATE TEMP TABLE sales_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region VARCHAR(100) NOT NULL,
    sales_channel VARCHAR(20) NOT NULL,
    ordered_at DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO sales_orders (
    order_id, customer_id, region, sales_channel,
    ordered_at, status, amount
) VALUES
    (1001, 1, 'Hà Nội',  'Online', DATE '2026-06-01', 'PAID',      120000),
    (1002, 2, 'Hà Nội',  'Store',  DATE '2026-06-01', 'PAID',       80000),
    (1003, 3, 'TP.HCM',  'Online', DATE '2026-06-02', 'PAID',      200000),
    (1004, 1, 'Hà Nội',  'Online', DATE '2026-06-02', 'CANCELLED',  50000),
    (1005, 4, 'TP.HCM',  'Store',  DATE '2026-06-03', 'PAID',      150000),
    (1006, 5, 'Đà Nẵng','Online', DATE '2026-06-04', 'PAID',       90000),
    (1007, 1, 'Hà Nội',  'Online', DATE '2026-07-01', 'PAID',      220000),
    (1008, 3, 'TP.HCM',  'Online', DATE '2026-07-02', 'PENDING',    70000),
    (1009, 5, 'Đà Nẵng','Store',  DATE '2026-07-03', 'PAID',      110000),
    (1010, 3, 'TP.HCM',  'Online', DATE '2026-07-04', 'PAID',      300000),
    (1011, 2, 'Hà Nội',  'Store',  DATE '2026-07-04', 'PAID',       60000),
    (1012, 3, 'TP.HCM',  'Online', DATE '2026-07-05', 'PAID',      200000);
```

### 18.1. Chạy một vài truy vấn khảo sát

```sql
-- Tổng số dòng nguồn và số đơn PAID.
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders
FROM sales_orders;

-- Một cột nhóm.
SELECT region, COUNT(*) AS paid_count, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY total_paid DESC, region;

-- Hai cột nhóm.
SELECT region, sales_channel, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, sales_channel
ORDER BY region, sales_channel;

-- Nhóm theo biểu thức tháng.
SELECT
    DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
    SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY DATE_TRUNC('month', ordered_at::timestamp)::date
ORDER BY month_start;
```

`FILTER (WHERE ...)` bên trong hàm tổng hợp là cú pháp được PostgreSQL hỗ trợ. Truy vấn đầu chỉ dùng để kiểm tra số lượng trong dữ liệu mẫu; nếu hệ khác không hỗ trợ `FILTER`, có thể dùng `SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)` hoặc truy vấn đếm riêng.

## 19. Bài tập tự luyện

Hãy sử dụng bảng `sales_orders` ở mục 18. Trước mỗi bài, viết một câu: **“Mỗi dòng kết quả đại diện cho ...”** và dự đoán số nhóm.

### Bài 1 — Một cột nhóm

Tính **số đơn của từng trạng thái** (`PAID`, `PENDING`, `CANCELLED`), không lọc trạng thái trước. Sắp theo số đơn giảm dần, rồi trạng thái tăng dần.

### Bài 2 — Hai cột nhóm

Tính **số đơn `PAID` theo vùng và kênh**. Đối với từng cặp, xuất `region`, `sales_channel`, `paid_order_count`.

### Bài 3 — Nhóm theo tháng

Tính tổng `amount` của đơn `PAID` theo từng tháng, nhóm bằng biểu thức lấy **ngày đầu tháng** từ `ordered_at`. Dự đoán tổng tháng 6 và tháng 7.

### Bài 4 — Nhóm theo tháng và vùng

Tính doanh thu `PAID` của từng **vùng trong mỗi tháng**. Cho biết Hà Nội tháng 6 và tháng 7 lần lượt là bao nhiêu.

### Bài 5 — `HAVING`

Tìm các vùng có **ít nhất 4 đơn `PAID`**; xuất mã vùng (tên vùng), số đơn và tổng giá trị. Giải thích vì sao điều kiện `COUNT(*) >= 4` thuộc `HAVING`, không phải `WHERE`.

### Bài 6 — Đếm khách duy nhất

Đếm số `customer_id` khác nhau trong các đơn `PAID` theo từng vùng. So sánh kết quả với `COUNT(*)`.

### Bài 7 — Phân loại theo giá trị đơn

Đếm số đơn `PAID` theo ba nhóm số tiền `[0,100000)`, `[100000,200000)` và `[200000,+∞)`. Có thể dùng CTE để tránh lặp biểu thức `CASE`.

### Bài 8 — Nhận diện sai độ hạt

Một truy vấn cần “một dòng trên mỗi vùng” nhưng lại viết:

```sql
SELECT region, ordered_at, SUM(amount)
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, ordered_at;
```

Truy vấn trên có đúng yêu cầu không? Vì sao? Hãy sửa để trả một dòng trên mỗi vùng.

### Bài 9 — Tổng khi không có dòng

So sánh kết quả:

```sql
SELECT region, SUM(amount)
FROM sales_orders
WHERE status = 'NOT_A_REAL_STATUS'
GROUP BY region;
```

với:

```sql
SELECT COUNT(*), SUM(amount)
FROM sales_orders
WHERE status = 'NOT_A_REAL_STATUS';
```

Truy vấn nào có 0 dòng đầu ra, truy vấn nào có 1 dòng? Vì sao?

### Bài 10 — Vùng chưa có đơn

Muốn báo cáo bốn vùng gồm Hà Nội, TP.HCM, Đà Nẵng, Cần Thơ, nhưng dữ liệu mẫu chưa có đơn tại Cần Thơ. Hãy đề xuất truy vấn để Cần Thơ vẫn xuất hiện với số đơn `PAID` bằng 0.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:** `PAID = 10`, `CANCELLED = 1`, `PENDING = 1`.

```sql
SELECT status, COUNT(*) AS order_count
FROM sales_orders
GROUP BY status
ORDER BY order_count DESC, status ASC;
```

**Bài 2:** Có sáu nhóm. Hà Nội Online 2, Hà Nội Store 2, TP.HCM Online 3, TP.HCM Store 1, Đà Nẵng Online 1, Đà Nẵng Store 1.

```sql
SELECT region, sales_channel, COUNT(*) AS paid_order_count
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, sales_channel
ORDER BY region, sales_channel;
```

**Bài 3:** Tháng 6 có `640000`, tháng 7 có `890000`.

```sql
SELECT DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
       SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY DATE_TRUNC('month', ordered_at::timestamp)::date
ORDER BY month_start;
```

**Bài 4:** Hà Nội tháng 6 là `200000`, tháng 7 là `280000`.

```sql
SELECT region,
       DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
       SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region, DATE_TRUNC('month', ordered_at::timestamp)::date
ORDER BY region, month_start;
```

**Bài 5:** Hà Nội và TP.HCM, mỗi vùng có 4 đơn; tổng tiền lần lượt `480000` và `850000`.

```sql
SELECT region, COUNT(*) AS paid_order_count, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
HAVING COUNT(*) >= 4
ORDER BY region;
```

**Bài 6:** Hà Nội có 2 khách, TP.HCM có 2, Đà Nẵng có 1; số đơn tương ứng là 4, 4, 2.

```sql
SELECT region, COUNT(*) AS paid_order_count,
       COUNT(DISTINCT customer_id) AS distinct_buyers
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region
ORDER BY region;
```

**Bài 7:** Số đơn thuộc ba nhóm lần lượt là `3`, `3`, `4`.

```sql
WITH classified AS (
    SELECT CASE
        WHEN amount < 100000 THEN 'under_100k'
        WHEN amount < 200000 THEN '100k_to_under_200k'
        ELSE '200k_or_more'
    END AS amount_band
    FROM sales_orders
    WHERE status = 'PAID'
)
SELECT amount_band, COUNT(*) AS paid_order_count
FROM classified
GROUP BY amount_band
ORDER BY amount_band;
```

**Bài 8:** Chưa đúng, vì mỗi cặp `(region, ordered_at)` tạo nhóm riêng. Muốn một dòng trên mỗi vùng:

```sql
SELECT region, SUM(amount) AS total_paid
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region;
```

**Bài 9:** Truy vấn có `GROUP BY region` trả **0 dòng** vì không có khóa vùng nào sau lọc. Truy vấn tổng hợp không có `GROUP BY` trả **1 dòng** với `COUNT(*) = 0` và `SUM(amount) = NULL`.

**Bài 10:** Dùng bảng danh mục hoặc CTE các vùng ở phía trái `LEFT JOIN`:

```sql
WITH regions(region) AS (
    VALUES ('Hà Nội'), ('TP.HCM'), ('Đà Nẵng'), ('Cần Thơ')
)
SELECT r.region,
       COUNT(o.order_id) AS paid_order_count
FROM regions AS r
LEFT JOIN sales_orders AS o
    ON o.region = r.region
   AND o.status = 'PAID'
GROUP BY r.region
ORDER BY r.region;
```

</details>

## 20. Nguyên tắc mang sang các truy vấn tổng hợp tiếp theo

Một câu truy vấn `GROUP BY` đúng bắt đầu bằng câu hỏi **“mỗi dòng kết quả là một nhóm theo khóa nào?”**. Nếu nhóm theo một cột, mỗi giá trị của cột đó là một nhóm. Nếu nhóm theo nhiều cột, mỗi **tổ hợp giá trị** là một nhóm. Nếu nhóm theo biểu thức, các dòng cho **cùng giá trị biểu thức** sẽ nằm cùng nhóm.

Hãy nhớ những mẫu nền tảng:

```sql
-- Một dòng trên mỗi vùng.
SELECT region, SUM(amount)
FROM sales_orders
GROUP BY region;

-- Một dòng trên mỗi cặp vùng và kênh.
SELECT region, sales_channel, SUM(amount)
FROM sales_orders
GROUP BY region, sales_channel;

-- Một dòng trên mỗi tháng trong PostgreSQL.
SELECT DATE_TRUNC('month', ordered_at::timestamp)::date AS month_start,
       SUM(amount)
FROM sales_orders
GROUP BY DATE_TRUNC('month', ordered_at::timestamp)::date;
```

Trước khi tin vào kết quả, kiểm tra **độ hạt nguồn sau `JOIN`**, điều kiện lọc dòng trong `WHERE`, điều kiện lọc nhóm trong `HAVING`, hành vi của `NULL`, và thời gian/múi giờ nếu khóa nhóm là ngày tháng. Cuối cùng, thêm `ORDER BY` nếu báo cáo cần một thứ tự cụ thể.

`GROUP BY` không đơn thuần là cú pháp đi kèm `SUM` hoặc `COUNT`: nó là cách **định nghĩa từng đơn vị phân tích trong dữ liệu**. Khi chọn đúng khóa nhóm và xác định đúng phép đo, truy vấn tổng hợp trở thành một bản mô tả rõ ràng, có thể kiểm chứng và mở rộng cho những báo cáo phức tạp hơn.
