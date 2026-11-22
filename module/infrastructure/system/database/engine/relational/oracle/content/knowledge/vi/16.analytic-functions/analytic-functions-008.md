# COUNT phân tích, RATIO_TO_REPORT và tỷ trọng trong nhóm trong Oracle

Trong báo cáo, đôi khi bạn cần giữ nguyên từng hàng chi tiết nhưng vẫn muốn biết mỗi hàng thuộc nhóm có bao nhiêu bản ghi, nhóm đó chiếm bao nhiêu phần trăm tổng thể hoặc một khoản doanh thu chiếm bao nhiêu tỷ trọng trong khu vực. Nếu dùng GROUP BY trực tiếp, Oracle gom nhiều hàng thành một hàng cho mỗi nhóm và bạn có thể mất các cột chi tiết. **Hàm phân tích (analytic functions)** giải quyết bài toán này: chúng tính toán trên một cửa sổ hàng liên quan nhưng vẫn giữ các hàng của truy vấn.

Hai công cụ hữu ích là:

- **COUNT phân tích**: đếm số hàng hoặc số giá trị không NULL trên toàn kết quả, trong từng partition, hoặc theo một cửa sổ chạy.
- **RATIO_TO_REPORT**: tính tỷ lệ của một giá trị so với tổng giá trị trong partition, rất phù hợp để biểu diễn tỷ trọng doanh thu, chi phí, số lượng hoặc ngân sách trong nhóm.

Ví dụ, một báo cáo doanh số có thể hiển thị từng giao dịch, số giao dịch của vùng, tổng doanh thu vùng và phần trăm đóng góp của giao dịch đó. Một báo cáo nhân sự có thể giữ từng nhân viên nhưng bổ sung số người trong phòng ban và thứ tự/đếm lũy kế theo ngày tuyển dụng.

Sau bài học, bạn có thể:

- Phân biệt COUNT aggregate với COUNT analytic.
- Dùng COUNT(*), COUNT(expr) và COUNT(DISTINCT expr) trong mệnh đề OVER.
- Đếm toàn bộ kết quả, đếm theo PARTITION BY và tạo running count theo ORDER BY/window frame.
- Hiểu cách xử lý NULL và vì sao số hàng sau JOIN ảnh hưởng kết quả đếm.
- Dùng RATIO_TO_REPORT để tính tỷ trọng trên toàn bộ tập dữ liệu hoặc trong từng nhóm.
- Đổi tỷ lệ thập phân thành phần trăm, làm tròn và định dạng hiển thị.
- Xử lý nhóm có tổng bằng 0 hoặc toàn bộ measure là NULL.
- Kết hợp GROUP BY, CTE và analytic functions mà không nhầm mức chi tiết (grain).
- Lọc kết quả analytic bằng query block bên ngoài và đọc execution plan khi cần.

> Các ví dụ dùng bảng có tiền tố LAB_ và phù hợp để thực hành trong schema riêng. COUNT và RATIO_TO_REPORT tính trên tập hàng mà query block cung cấp sau FROM/WHERE/JOIN/GROUP BY/HAVING; nếu JOIN đã nhân dòng, kết quả đếm và tỷ trọng cũng có thể bị ảnh hưởng. Hãy xác định rõ mỗi hàng đầu vào đại diện cho điều gì trước khi tính.

## 1. Aggregate và analytic: khác nhau ở kết quả trả về

### 1.1. COUNT aggregate gom hàng

Giả sử bảng SALES có các giao dịch:

| SALE_ID | REGION_ID | AMOUNT |
| ---: | --- | ---: |
| 1 | NORTH | 100 |
| 2 | NORTH | 200 |
| 3 | NORTH | 300 |
| 4 | SOUTH | 150 |
| 5 | SOUTH | 250 |

COUNT kết hợp GROUP BY tạo một hàng cho mỗi vùng:

```sql
SELECT region_id, COUNT(*) AS sale_count
FROM lab_sales
GROUP BY region_id;
```

Kết quả:

| REGION_ID | SALE_COUNT |
| --- | ---: |
| NORTH | 3 |
| SOUTH | 2 |

Các hàng giao dịch chi tiết đã được gom lại. Đây là lựa chọn đúng khi đầu ra cần **một hàng cho mỗi vùng**.

### 1.2. COUNT analytic giữ các hàng chi tiết

Thêm OVER:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_sale_count
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Kết quả khái niệm:

| SALE_ID | REGION_ID | AMOUNT | REGION_SALE_COUNT |
| ---: | --- | ---: | ---: |
| 1 | NORTH | 100 | 3 |
| 2 | NORTH | 200 | 3 |
| 3 | NORTH | 300 | 3 |
| 4 | SOUTH | 150 | 2 |
| 5 | SOUTH | 250 | 2 |

Oracle vẫn trả năm hàng giao dịch; mỗi hàng được bổ sung số giao dịch trong vùng tương ứng. Đây là điểm khác biệt cốt lõi: **GROUP BY thay đổi grain đầu ra, analytic function bổ sung kết quả trên các hàng của grain hiện tại**.

### 1.3. Mô hình xử lý

```text
Các hàng sau FROM / JOIN / WHERE
               │
               ▼
        Tập hàng của query block
               │
        ┌──────┴─────────┐
        ▼                ▼
   GROUP BY          OVER (...)
        │                │
        ▼                ▼
  Gom thành nhóm     Giữ từng hàng
  và tính COUNT     và gắn kết quả cửa sổ
        │                │
        ▼                ▼
  Một hàng/nhóm     Một hàng đầu vào/vị trí
```

Một câu SELECT có thể dùng cả aggregate và analytic, nhưng phải hiểu analytic đang nhìn thấy **các hàng sau GROUP BY** nếu query block có GROUP BY. Phần 8 sẽ trình bày trường hợp này.

## 2. COUNT phân tích: cú pháp và ba dạng đếm

Cú pháp tổng quát:

```sql
COUNT({* | [DISTINCT | ALL] expr})
OVER (
    [PARTITION BY partition_expression, ...]
    [ORDER BY order_expression ...]
    [windowing_clause]
)
```

`OVER` xác định cửa sổ dữ liệu mà hàm phân tích nhìn vào:

- Không có PARTITION BY: cửa sổ có thể là toàn bộ tập hàng của query block.
- Có PARTITION BY: chia tập hàng thành các nhóm logic độc lập.
- Có ORDER BY: xác định thứ tự xử lý trong partition; với aggregate analytic như COUNT, nó cũng liên quan đến window frame mặc định.
- Có windowing clause: giới hạn các hàng trong cửa sổ, ví dụ từ đầu partition đến hàng hiện tại.

### 2.1. COUNT(*) OVER(): đếm toàn bộ hàng của kết quả

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER () AS total_rows
FROM lab_sales
ORDER BY sale_id;
```

Mọi hàng đều nhận cùng một giá trị TOTAL_ROWS là 5. Không có PARTITION BY nên cửa sổ bao gồm toàn bộ hàng của query block.

Đây là cách bổ sung tổng số hàng vào từng dòng chi tiết, thường dùng cho báo cáo phân trang, hiển thị số bản ghi hoặc tính tỷ lệ trên toàn kết quả.

### 2.2. COUNT(*) OVER(PARTITION BY ...): đếm trong từng nhóm

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS rows_in_region
FROM lab_sales
ORDER BY region_id, sale_id;
```

Mỗi vùng được đếm riêng. Mọi hàng có REGION_ID bằng nhau thuộc cùng partition; các partition không ảnh hưởng lẫn nhau.

Nếu PARTITION BY nhiều cột, nhóm được xác định bởi tổ hợp giá trị của các cột:

```sql
COUNT(*) OVER (
    PARTITION BY region_id, product_id
) AS rows_per_region_product
```

Ví dụ này đếm số giao dịch cho từng tổ hợp vùng và sản phẩm.

### 2.3. COUNT(expr) bỏ qua NULL

Khác với COUNT(*), COUNT(expr) chỉ đếm các hàng mà biểu thức không NULL:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS all_region_rows,
    COUNT(amount) OVER (
        PARTITION BY region_id
    ) AS nonnull_amount_rows
FROM lab_sales
ORDER BY region_id, sale_id;
```

Nếu một vùng có bốn giao dịch nhưng một giao dịch chưa có AMOUNT, COUNT(*) trả 4 còn COUNT(AMOUNT) trả 3 cho mọi hàng trong vùng.

Quy tắc:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `COUNT(*)` | Đếm mọi hàng, kể cả hàng có cột NULL |
| `COUNT(expr)` | Đếm hàng có expr khác NULL |
| `COUNT(DISTINCT expr)` | Đếm số giá trị expr khác NULL và khác nhau |

COUNT trả 0 khi cửa sổ có hàng nhưng mọi giá trị expr đều NULL. Nếu query block không trả hàng nào, không có hàng đầu ra để hiển thị một giá trị COUNT analytic.

### 2.4. COUNT(DISTINCT expr) OVER(PARTITION BY ...)

Có thể đếm số giá trị khác nhau trong mỗi partition:

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    COUNT(DISTINCT product_id) OVER (
        PARTITION BY region_id
    ) AS distinct_products_in_region
FROM lab_sales
ORDER BY region_id, sale_id;
```

Ví dụ này cho biết mỗi vùng có bao nhiêu mã sản phẩm khác nhau, đồng thời vẫn giữ từng giao dịch.

**Giới hạn cú pháp Oracle:** khi dùng DISTINCT trong COUNT analytic, analytic clause chỉ được có PARTITION BY; không dùng ORDER BY hoặc windowing clause cùng DISTINCT trong cùng lời gọi COUNT. Nếu cần đếm distinct lũy kế theo thời gian, thường phải thiết kế query nhiều bước (ví dụ xác định lần xuất hiện đầu tiên rồi cộng cờ) thay vì viết COUNT(DISTINCT ...) OVER(ORDER BY ...).

## 3. PARTITION BY: định nghĩa nhóm cho hàm phân tích

PARTITION BY chia tập hàng thành các partition logic. Nó không sắp xếp kết quả cuối và cũng không loại hàng.

### 3.1. Đếm theo phòng ban

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_headcount
FROM lab_employees
ORDER BY department_id, employee_id;
```

Mỗi nhân viên vẫn có một hàng. Số nhân viên cùng phòng ban được lặp trên từng hàng của phòng đó.

### 3.2. PARTITION BY nhiều cấp

Có thể chia theo vùng và tháng:

```sql
COUNT(*) OVER (
    PARTITION BY region_id, TRUNC(sold_at, 'MM')
) AS sales_in_region_month
```

Mỗi tổ hợp REGION_ID và tháng là một partition riêng. Nếu biểu thức partition chứa hàm như TRUNC, cần cân nhắc kiểu dữ liệu và khả năng dùng biểu thức thống nhất trong các truy vấn liên quan.

### 3.3. Giá trị NULL trong khóa partition

Các hàng có cùng khóa partition NULL được xếp vào cùng một partition cho mục đích hàm phân tích. Ví dụ, các nhân viên chưa gán phòng ban (DEPARTMENT_ID IS NULL) được đếm chung trong partition NULL nếu không có quy tắc xử lý khác.

Nếu không muốn gom các hàng thiếu khóa vào một nhóm chung, hãy quyết định chính sách rõ ràng: lọc chúng, gắn nhãn nhóm riêng bằng CASE/NVL phù hợp, hoặc giữ partition NULL và giải thích ý nghĩa.

### 3.4. PARTITION BY không giống GROUP BY

| GROUP BY | PARTITION BY trong OVER |
| --- | --- |
| Gom các hàng thành nhóm kết quả | Chia hàng thành cửa sổ logic |
| Thường làm giảm số hàng đầu ra | Không tự làm giảm số hàng |
| Cột không aggregate phải thuộc GROUP BY | Có thể giữ các cột chi tiết của mỗi hàng |
| Dùng để tạo tổng hợp một hàng/nhóm | Dùng để bổ sung thống kê nhóm lên hàng chi tiết |

## 4. COUNT có ORDER BY: running count và window frame

COUNT analytic có thể kết hợp ORDER BY để tạo số đếm lũy kế.

### 4.1. Running count theo ngày

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at
    ) AS running_sales_count
FROM lab_sales
ORDER BY region_id, sold_at, sale_id;
```

Khi có ORDER BY trong analytic aggregate nhưng không chỉ định window frame, Oracle sử dụng frame mặc định dạng RANGE từ UNBOUNDED PRECEDING đến CURRENT ROW. Điều này có nghĩa các hàng có cùng giá trị ORDER BY (peer rows) cùng thuộc frame của nhau; chúng có thể nhận cùng running count tại mốc đó.

Nếu cần đếm tuần tự từng hàng, phải xác định thứ tự duy nhất và dùng ROWS:

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_by_row_count
FROM lab_sales
ORDER BY region_id, sold_at, sale_id;
```

Ở đây SALE_ID là tie-breaker để thứ tự không mơ hồ khi nhiều giao dịch có cùng SOLD_AT.

### 4.2. RANGE và ROWS khác nhau thế nào?

- `ROWS` xác định cửa sổ theo vị trí vật lý của hàng trong thứ tự analytic.
- `RANGE` xác định cửa sổ theo giá trị logic của biểu thức ORDER BY; các peer rows có cùng giá trị thường cùng được đưa vào frame.

Ví dụ, nếu ba giao dịch cùng thời điểm 10:00, với RANGE đến CURRENT ROW, cả ba có thể nhận count bao gồm cả ba giao dịch đó. Với ROWS và tie-breaker SALE_ID, các hàng lần lượt nhận count 1, 2, 3 trong phạm vi partition.

### 4.3. Cửa sổ trượt: đếm N hàng gần nhất

COUNT cũng dùng được với frame có giới hạn:

```sql
COUNT(*) OVER (
    PARTITION BY region_id
    ORDER BY sold_at, sale_id
    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
) AS sales_in_last_7_rows
```

Đây là số hàng trong tối đa bảy vị trí gần nhất tính đến hàng hiện tại. Nó **không tự có nghĩa bảy ngày gần nhất**; nếu dữ liệu có nhiều giao dịch trong một ngày hoặc ngày bị thiếu, ROWS vẫn đếm hàng. Muốn cửa sổ theo khoảng thời gian, cần dùng RANGE với biểu thức ngày/số và cú pháp phù hợp với kiểu ORDER BY, hoặc tổng hợp theo ngày trước.

### 4.4. Không có ORDER BY nếu chỉ cần tổng số trong partition

Nếu mục tiêu chỉ là số hàng trong cả vùng, không thêm ORDER BY:

```sql
COUNT(*) OVER (PARTITION BY region_id)
```

Thêm ORDER BY mà không chủ ý có thể biến kết quả từ tổng số toàn nhóm thành số đếm lũy kế. Đây là lỗi dễ gặp khi copy một biểu thức analytic từ báo cáo running total.

## 5. RATIO_TO_REPORT: tỷ trọng trong nhóm

### 5.1. Ý nghĩa và cú pháp

`RATIO_TO_REPORT(expr)` tính tỷ lệ của giá trị expr so với tổng expr trong partition:

```sql
RATIO_TO_REPORT(expr)
OVER (
    [PARTITION BY partition_expression, ...]
)
```

Về ý nghĩa:

```text
Tỷ trọng của một hàng
= giá trị của hàng
  / tổng giá trị trong partition
```

Ví dụ, nếu doanh thu một giao dịch là 200 và tổng doanh thu vùng là 1.000, tỷ trọng là 0,2 (tức 20%).

RATIO_TO_REPORT là hàm phân tích: nó **không gom các hàng**. Mỗi hàng nhận tỷ lệ của chính giá trị hàng đó so với tổng của partition.

### 5.2. Tỷ trọng trong toàn bộ kết quả

Không có PARTITION BY thì toàn bộ tập hàng của query block là một nhóm:

```sql
SELECT
    sale_id,
    amount,
    RATIO_TO_REPORT(amount) OVER () AS total_share
FROM lab_sales
ORDER BY sale_id;
```

Nếu tổng amount là 1.000, giao dịch 100 có tỷ lệ 0,1; giao dịch 200 có tỷ lệ 0,2. Các tỷ lệ của mọi hàng có AMOUNT khác NULL cộng lại bằng 1 khi tổng khác 0 (có thể sai khác rất nhỏ khi hiển thị do làm tròn).

### 5.3. Tỷ trọng theo vùng

```sql
SELECT
    sale_id,
    region_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Mỗi vùng có mẫu số riêng. Tổng các tỷ trọng trong NORTH bằng 1; tổng các tỷ trọng trong SOUTH cũng bằng 1, với điều kiện tổng của mỗi vùng khác 0 và measure hợp lệ.

### 5.4. Tỷ trọng theo nhiều chiều

Có thể tính tỷ trọng trong từng tổ hợp vùng-tháng:

```sql
RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id, TRUNC(sold_at, 'MM')
) AS share_in_region_month
```

Mẫu số là tổng amount của đúng partition vùng-tháng. Đổi partition key là đổi câu hỏi nghiệp vụ: tỷ trọng trong toàn công ty, trong vùng, trong vùng-tháng hay trong sản phẩm-vùng là những đại lượng khác nhau.

### 5.5. RATIO_TO_REPORT và SUM OVER

Có thể tự biểu diễn tỷ lệ bằng:

```sql
amount / SUM(amount) OVER (PARTITION BY region_id)
```

Với tổng khác 0, biểu thức này tương đương về ý nghĩa với:

```sql
RATIO_TO_REPORT(amount) OVER (PARTITION BY region_id)
```

RATIO_TO_REPORT ngắn gọn và diễn đạt rõ mục tiêu tỷ trọng. SUM OVER hữu ích khi bạn cũng cần hiển thị mẫu số hoặc cần tự xử lý trường hợp đặc biệt.

Lời gọi RATIO_TO_REPORT có cú pháp OVER với PARTITION BY; không thêm ORDER BY/windowing clause như khi viết COUNT analytic. Nếu cần tỷ lệ lũy kế theo thứ tự, hãy dùng SUM analytic có window frame để tính tử số lũy kế và tổng partition làm mẫu số, thay vì cố đặt ORDER BY vào RATIO_TO_REPORT.

## 6. NULL, tổng bằng 0 và dấu âm trong tỷ trọng

### 6.1. Measure NULL

Nếu expr là NULL, RATIO_TO_REPORT trả NULL cho hàng đó. Tổng mẫu số được tính theo SUM, vì vậy các giá trị NULL không đóng góp vào tổng. Điều này phù hợp với ý nghĩa “không có giá trị để tính tỷ trọng”, nhưng báo cáo phải phân biệt NULL với tỷ trọng 0.

- Amount bằng 0, tổng partition khác 0: tỷ trọng là 0.
- Amount NULL: tỷ trọng là NULL.
- Tất cả amount trong partition đều NULL: SUM partition là NULL, không có tỷ trọng có ý nghĩa.

Không tự thay NULL bằng 0 bằng NVL nếu nghiệp vụ cần phân biệt “không ghi nhận” với “đã ghi nhận giá trị bằng 0”.

### 6.2. Tổng partition bằng 0

Nếu tổng của partition bằng 0, phép chia không xác định. Trong Oracle, phép chia số cho 0 có thể phát sinh `ORA-01476: divisor is equal to zero`. Không thiết kế báo cáo dựa trên giả định tổng bằng 0 sẽ tự được biến thành một tỷ lệ hợp lệ.

Nếu tổng có thể bằng 0, hãy tính mẫu số và guard rõ ràng:

```sql
WITH sales_with_total AS (
    SELECT
        sale_id,
        region_id,
        amount,
        SUM(amount) OVER (
            PARTITION BY region_id
        ) AS region_total
    FROM lab_sales
)
SELECT
    sale_id,
    region_id,
    amount,
    region_total,
    CASE
        WHEN region_total = 0 THEN NULL
        ELSE amount / region_total
    END AS safe_region_share
FROM sales_with_total
ORDER BY region_id, sale_id;
```

Khi tổng là NULL (ví dụ mọi amount đều NULL), biểu thức ELSE cũng cho NULL vì chia cho NULL trả NULL. CASE ở đây nêu rõ chính sách: tổng 0 thì tỷ trọng không xác định và được biểu diễn NULL. Nếu nghiệp vụ muốn 0%, N/A hoặc trạng thái riêng, hãy thay chính sách có chủ đích.

### 6.3. Tổng âm hoặc có cả giá trị âm/dương

RATIO_TO_REPORT không tự bảo đảm kết quả nằm trong khoảng 0 đến 1. Nếu measure có số âm, ví dụ hoàn tiền, điều chỉnh hoặc lỗ, tổng có thể nhỏ hơn từng giá trị hoặc đổi dấu. Tỷ trọng khi đó có thể âm, lớn hơn 1 hoặc khó diễn giải như phần trăm đóng góp thông thường.

Nếu cần tỷ trọng doanh thu bán hàng, hãy xác định có loại hoàn tiền/điều chỉnh khỏi mẫu số không. Nếu cần phân tích net revenue, giá trị âm có thể phải được giữ. Công thức vẫn có thể tính được, nhưng cách giải thích nghiệp vụ phải phản ánh dấu và tổng.

## 7. Bộ dữ liệu thực hành cho COUNT và tỷ trọng

Tạo bảng giao dịch có dữ liệu ở nhiều vùng, nhiều sản phẩm, một vài giá trị NULL và một partition có tổng bằng 0:

```sql
CREATE TABLE lab_sales (
    sale_id    NUMBER(10)
        CONSTRAINT pk_lab_sales PRIMARY KEY,
    region_id  VARCHAR2(20),
    product_id NUMBER(10),
    sold_at    DATE,
    amount     NUMBER(12, 2)
);

INSERT INTO lab_sales VALUES
    (1, 'NORTH', 10, DATE '2026-01-01', 100);
INSERT INTO lab_sales VALUES
    (2, 'NORTH', 20, DATE '2026-01-01', 200);
INSERT INTO lab_sales VALUES
    (3, 'NORTH', 10, DATE '2026-01-02', 300);
INSERT INTO lab_sales VALUES
    (4, 'SOUTH', 10, DATE '2026-01-01', 150);
INSERT INTO lab_sales VALUES
    (5, 'SOUTH', 20, DATE '2026-01-03', 250);
INSERT INTO lab_sales VALUES
    (6, 'SOUTH', 20, DATE '2026-01-03', NULL);
INSERT INTO lab_sales VALUES
    (7, 'WEST', 30, DATE '2026-01-04', NULL);
INSERT INTO lab_sales VALUES
    (8, 'ZERO', 40, DATE '2026-01-05', 100);
INSERT INTO lab_sales VALUES
    (9, 'ZERO', 41, DATE '2026-01-06', -100);

COMMIT;
```

Dữ liệu có ý nghĩa:

| SALE_ID | REGION_ID | PRODUCT_ID | AMOUNT |
| ---: | --- | ---: | ---: |
| 1 | NORTH | 10 | 100 |
| 2 | NORTH | 20 | 200 |
| 3 | NORTH | 10 | 300 |
| 4 | SOUTH | 10 | 150 |
| 5 | SOUTH | 20 | 250 |
| 6 | SOUTH | 20 | NULL |
| 7 | WEST | 30 | NULL |
| 8 | ZERO | 40 | 100 |
| 9 | ZERO | 41 | -100 |

Tổng theo vùng:

| REGION_ID | ROWS | NONNULL_AMOUNTS | REGION_TOTAL |
| --- | ---: | ---: | ---: |
| NORTH | 3 | 3 | 600 |
| SOUTH | 3 | 2 | 400 |
| WEST | 1 | 0 | NULL |
| ZERO | 2 | 2 | 0 |

Nhóm WEST minh họa partition có toàn bộ measure NULL; nhóm ZERO minh họa tổng các giá trị khác NULL bằng 0. Hai trường hợp này cần chính sách riêng khi tính tỷ trọng.

Để minh họa COUNT theo phòng ban và chức danh, tạo thêm một bảng nhân sự nhỏ:

```sql
CREATE TABLE lab_analysts (
    employee_id   NUMBER(10) PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    department_id NUMBER(10),
    job_id        VARCHAR2(20),
    hire_date     DATE
);

INSERT INTO lab_analysts VALUES
    (1, 'An', 10, 'DEV', DATE '2022-01-10');
INSERT INTO lab_analysts VALUES
    (2, 'Binh', 10, 'QA', DATE '2022-02-15');
INSERT INTO lab_analysts VALUES
    (3, 'Chi', 10, 'DEV', DATE '2023-03-01');
INSERT INTO lab_analysts VALUES
    (4, 'Dung', 20, 'QA', DATE '2021-05-20');
INSERT INTO lab_analysts VALUES
    (5, 'Ha', 20, 'QA', DATE '2024-06-01');
INSERT INTO lab_analysts VALUES
    (6, 'Lam', NULL, 'HR', DATE '2024-07-01');

COMMIT;
```

Trong department 10 có hai DEV và một QA; department 20 có hai QA; nhân viên Lam chưa được gán phòng ban.

## 8. Kết hợp COUNT phân tích và RATIO_TO_REPORT

### 8.1. Báo cáo giao dịch kèm số hàng và tỷ trọng vùng

Với những partition có tổng khác 0:

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_row_count,
    COUNT(amount) OVER (
        PARTITION BY region_id
    ) AS region_nonnull_amount_count,
    SUM(amount) OVER (
        PARTITION BY region_id
    ) AS region_total,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share,
    ROUND(
        100 * RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS region_share_pct
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Kết quả:

| SALE_ID | REGION_ID | AMOUNT | ROW_COUNT | NONNULL_COUNT | REGION_TOTAL | REGION_SHARE | REGION_SHARE_PCT |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | NORTH | 100 | 3 | 3 | 600 | 0.166667 | 16.67 |
| 2 | NORTH | 200 | 3 | 3 | 600 | 0.333333 | 33.33 |
| 3 | NORTH | 300 | 3 | 3 | 600 | 0.500000 | 50.00 |
| 4 | SOUTH | 150 | 3 | 2 | 400 | 0.375000 | 37.50 |
| 5 | SOUTH | 250 | 3 | 2 | 400 | 0.625000 | 62.50 |
| 6 | SOUTH | NULL | 3 | 2 | 400 | NULL | NULL |

Lưu ý:

- REGION_ROW_COUNT đếm mọi hàng trong vùng.
- REGION_NONNULL_AMOUNT_COUNT đếm những giao dịch có amount.
- REGION_TOTAL lặp lại tổng vùng trên từng hàng.
- REGION_SHARE là tỷ lệ dạng số thập phân; nhân 100 để hiển thị phần trăm.
- Hàng có amount NULL vẫn được giữ, nhưng tỷ trọng của nó là NULL.

### 8.2. Định dạng phần trăm cho giao diện

Không cần đổi tỷ lệ thành text nếu consumer có thể định dạng số. Giữ NUMBER thường thuận tiện cho tính toán tiếp theo. Nếu cần chuỗi hiển thị trong SQL:

```sql
SELECT
    sale_id,
    region_id,
    TO_CHAR(
        ROUND(
            100 * RATIO_TO_REPORT(amount) OVER (
                PARTITION BY region_id
            ),
            2
        ),
        'FM990D00',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) || '%' AS region_share_display
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

TO_CHAR làm kết quả thành VARCHAR2. Nếu API hoặc tầng Java cần sắp xếp, cộng hoặc so sánh tỷ lệ, hãy trả giá trị NUMBER và định dạng ở tầng trình bày. Format model và NLS parameter tường minh giúp chuỗi hiển thị nhất quán giữa các session.

### 8.3. Tỷ trọng sản phẩm trong vùng sau khi tổng hợp

Nếu yêu cầu là tỷ trọng của **từng sản phẩm** trong vùng, trước tiên gom doanh thu theo vùng và sản phẩm, sau đó dùng RATIO_TO_REPORT trên các tổng đã gom:

```sql
WITH product_totals AS (
    SELECT
        region_id,
        product_id,
        SUM(amount) AS product_amount
    FROM lab_sales
    WHERE region_id IN ('NORTH', 'SOUTH')
      AND amount IS NOT NULL
    GROUP BY region_id, product_id
)
SELECT
    region_id,
    product_id,
    product_amount,
    RATIO_TO_REPORT(product_amount) OVER (
        PARTITION BY region_id
    ) AS product_share_in_region,
    ROUND(
        100 * RATIO_TO_REPORT(product_amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS product_share_pct
FROM product_totals
ORDER BY region_id, product_id;
```

Trong NORTH, sản phẩm 10 có tổng 400 (100 + 300), sản phẩm 20 có tổng 200. Tỷ trọng tương ứng là 66,67% và 33,33%. Đây là một ví dụ quan trọng về việc chọn đúng grain trước khi tính tỷ lệ.

### 8.4. Tỷ trọng theo nhóm sau GROUP BY khác tỷ trọng trên từng giao dịch

Nếu dùng RATIO_TO_REPORT trực tiếp trên từng giao dịch, mẫu số là tổng giao dịch trong partition. Nếu muốn tỷ trọng của **phòng ban theo job**, **sản phẩm theo vùng** hoặc **chi nhánh theo tháng**, hãy GROUP BY về đúng đơn vị đó trước.

Ví dụ đếm nhân viên theo phòng ban và chức danh, sau đó bổ sung số loại chức danh và tổng headcount:

```sql
WITH job_counts AS (
    SELECT department_id,
           job_id,
           COUNT(*) AS employees_in_job
    FROM lab_analysts
    GROUP BY department_id, job_id
)
SELECT
    department_id,
    job_id,
    employees_in_job,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS job_types_in_department,
    SUM(employees_in_job) OVER (
        PARTITION BY department_id
    ) AS department_headcount,
    RATIO_TO_REPORT(employees_in_job) OVER (
        PARTITION BY department_id
    ) AS job_share_in_department
FROM job_counts
ORDER BY department_id, job_id;
```

Ở query block bên ngoài, mỗi hàng là một tổ hợp department-job. Vì vậy COUNT(*) analytic đếm **số nhóm job** trong phòng ban, còn SUM(employees_in_job) analytic mới đếm tổng nhân viên của phòng ban. RATIO_TO_REPORT tính tỷ trọng headcount của job trong phòng ban.

## 9. Lọc dữ liệu và giữ đúng mẫu số của tỷ trọng

Một điểm quan trọng là WHERE lọc hàng **trước khi** analytic functions được tính trong cùng query block. Vì vậy, nếu lọc một sản phẩm trong query chứa RATIO_TO_REPORT, mẫu số chỉ còn tổng của sản phẩm đó, không còn tổng vùng ban đầu.

### 9.1. Lọc trước analytic: mẫu số thay đổi

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS share_after_filter
FROM lab_sales
WHERE region_id = 'NORTH'
  AND product_id = 10
ORDER BY sale_id;
```

Vì WHERE loại sản phẩm 20 trước khi analytic chạy, mẫu số NORTH trong query block này chỉ còn tổng của sản phẩm 10 (400). Hai giao dịch sản phẩm 10 lần lượt có tỷ trọng 25% và 75%. Đây là tỷ trọng trong **tập đã lọc**, không phải tỷ trọng của từng giao dịch trong toàn vùng (16,67% và 50%).

### 9.2. Tính tỷ trọng trước, lọc hiển thị sau

Nếu muốn chỉ hiển thị sản phẩm 10 nhưng tỷ trọng phải tính trên toàn vùng, dùng query block bên trong:

```sql
WITH sales_with_share AS (
    SELECT
        sale_id,
        region_id,
        product_id,
        amount,
        RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ) AS share_in_region
    FROM lab_sales
    WHERE region_id = 'NORTH'
)
SELECT *
FROM sales_with_share
WHERE product_id = 10
ORDER BY sale_id;
```

Ở đây analytic được tính trên tất cả giao dịch NORTH trước; query ngoài chỉ lọc những hàng sản phẩm 10. Tỷ trọng vẫn là 16,67% và 50% trên tổng vùng 600.

### 9.3. Top N nhưng tỷ trọng tính trên toàn nhóm

Tương tự, nếu báo cáo chỉ hiển thị ba sản phẩm có doanh thu cao nhất nhưng muốn tỷ trọng tính trên tổng vùng:

```sql
WITH product_totals AS (
    SELECT region_id,
           product_id,
           SUM(amount) AS product_amount
    FROM lab_sales
    WHERE region_id IN ('NORTH', 'SOUTH')
    GROUP BY region_id, product_id
),
shares AS (
    SELECT
        region_id,
        product_id,
        product_amount,
        RATIO_TO_REPORT(product_amount) OVER (
            PARTITION BY region_id
        ) AS region_share,
        ROW_NUMBER() OVER (
            PARTITION BY region_id
            ORDER BY product_amount DESC, product_id
        ) AS rn
    FROM product_totals
)
SELECT region_id, product_id, product_amount, region_share
FROM shares
WHERE rn <= 3
ORDER BY region_id, rn;
```

RATIO_TO_REPORT và ROW_NUMBER được tính trong CTE shares trên toàn bộ sản phẩm của từng vùng. Query ngoài mới lọc rn <= 3. Nếu lọc top 3 trước khi tính ratio, tỷ trọng sẽ được chia lại trên tổng của top 3, cho một đại lượng khác.

### 9.4. Vì sao analytic không dùng trực tiếp trong WHERE cùng query block?

Không viết:

```sql
SELECT sale_id, region_id,
       COUNT(*) OVER (PARTITION BY region_id) AS region_count
FROM lab_sales
WHERE COUNT(*) OVER (PARTITION BY region_id) > 2;
```

Oracle không cho đặt analytic function trực tiếp trong WHERE của cùng query block. Tính trong CTE/subquery rồi lọc ở query ngoài:

```sql
WITH counted_sales AS (
    SELECT
        sale_id,
        region_id,
        COUNT(*) OVER (
            PARTITION BY region_id
        ) AS region_count
    FROM lab_sales
)
SELECT *
FROM counted_sales
WHERE region_count > 2
ORDER BY region_id, sale_id;
```

### 9.5. COUNT OVER cho phân trang

Một ứng dụng có thể cần trả từng trang dữ liệu nhưng vẫn muốn biết tổng số hàng thỏa bộ lọc:

```sql
SELECT
    sale_id,
    region_id,
    amount,
    COUNT(*) OVER () AS total_matching_rows
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY sale_id
OFFSET 0 ROWS FETCH NEXT 3 ROWS ONLY;
```

COUNT OVER được tính trên tập hàng phù hợp WHERE của query block trước khi giới hạn trang bằng OFFSET/FETCH. Vì vậy mỗi hàng trong trang có thể mang tổng số hàng khớp bộ lọc, không chỉ số hàng được trả trong trang. Đây là mẫu hữu ích, nhưng nếu kết quả không có hàng nào thì không có hàng để mang tổng số 0; khi API cần tổng count ngay cả trang rỗng, có thể cần một query count riêng hoặc cấu trúc trả về khác.

## 10. COUNT và RATIO_TO_REPORT sau JOIN: chú ý fan-out

Analytic function không biết một hàng bị nhân là lỗi nghiệp vụ. Nó tính trên **tập hàng thực tế** sau FROM/JOIN/WHERE/GROUP BY/HAVING.

Giả sử một đơn hàng có hai dòng sản phẩm. Nếu join đơn hàng với dòng chi tiết, COUNT(*) theo order sẽ là 2, không phải 1:

```sql
SELECT
    o.order_id,
    l.line_id,
    COUNT(*) OVER (
        PARTITION BY o.order_id
    ) AS rows_per_order
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

Nếu cần đếm số đơn hàng duy nhất trong từng khách hàng sau join:

```sql
SELECT
    o.customer_id,
    o.order_id,
    l.line_id,
    COUNT(DISTINCT o.order_id) OVER (
        PARTITION BY o.customer_id
    ) AS distinct_orders_per_customer
FROM orders o
JOIN order_lines l
  ON l.order_id = o.order_id;
```

COUNT(DISTINCT ...) OVER(PARTITION BY ...) có thể đếm số order duy nhất trong partition trong khi vẫn giữ chi tiết dòng hàng. Nhớ giới hạn Oracle: lời gọi DISTINCT analytic không kèm ORDER BY hoặc window frame.

Nếu cần tỷ trọng doanh thu đơn hàng trên tổng doanh thu khách hàng nhưng query đã join với order lines, phải xác định AMOUNT đang ở grain đơn hàng hay dòng hàng. Cộng lại một cột header amount trên mỗi line sẽ nhân doanh thu đơn hàng theo số line. Hãy tổng hợp về grain đơn hàng trước, hoặc dùng measure thực sự thuộc grain dòng hàng.

Mẫu đúng khi cần tỷ trọng từng đơn trong tổng khách hàng:

```sql
WITH order_totals AS (
    SELECT order_id,
           customer_id,
           SUM(line_amount) AS order_amount
    FROM order_lines
    GROUP BY order_id, customer_id
)
SELECT
    order_id,
    customer_id,
    order_amount,
    RATIO_TO_REPORT(order_amount) OVER (
        PARTITION BY customer_id
    ) AS customer_order_share
FROM order_totals;
```

Ở đây mỗi hàng đầu vào của RATIO_TO_REPORT là một đơn hàng đã tổng hợp, nên mẫu số và tử số cùng ở grain order.

## 11. Thứ tự xử lý query block và kết hợp với GROUP BY

Để hiểu kết quả analytic, cần biết query block đã tạo ra tập hàng nào trước khi hàm phân tích chạy. Mô hình khái niệm trong Oracle:

1. FROM và JOIN xác định nguồn dữ liệu và các cặp hàng.
2. WHERE lọc hàng đầu vào.
3. GROUP BY và các aggregate gom hàng nếu có.
4. HAVING lọc các nhóm.
5. Analytic functions tính trên tập hàng còn lại của query block.
6. SELECT trả các biểu thức; ORDER BY cuối cùng sắp xếp kết quả hiển thị.

Vì thế:

- COUNT analytic sau JOIN đếm các hàng đã join, kể cả khi một bản ghi bị nhân do quan hệ 1:N.
- COUNT analytic trong query có GROUP BY đếm các **hàng nhóm** sau GROUP BY, không quay lại đếm các hàng nguồn ban đầu.
- WHERE trong cùng query block làm thay đổi tập hàng và mẫu số trước khi RATIO_TO_REPORT tính.
- ORDER BY cuối câu SQL không thay thế ORDER BY bên trong OVER.

### 11.1. COUNT analytic sau GROUP BY đếm số nhóm

Ví dụ:

```sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employees_in_job,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS job_groups_in_department
FROM lab_analysts
GROUP BY department_id, job_id
ORDER BY department_id, job_id;
```

Sau GROUP BY, mỗi hàng là một cặp department-job. COUNT(*) analytic vì thế đếm số nhóm chức danh trong mỗi phòng ban. Nó không đếm số nhân viên của phòng ban.

Nếu muốn tổng headcount theo phòng ban, có thể dùng:

```sql
SELECT
    department_id,
    job_id,
    COUNT(*) AS employees_in_job,
    SUM(COUNT(*)) OVER (
        PARTITION BY department_id
    ) AS department_headcount
FROM lab_analysts
GROUP BY department_id, job_id
ORDER BY department_id, job_id;
```

Ở đây COUNT(*) bên trong là aggregate theo department-job; SUM(...) OVER là analytic chạy trên các hàng nhóm. Oracle cho phép dùng aggregate làm đầu vào của analytic ở query block sau GROUP BY. Cách viết này khác với việc lồng một analytic function vào một analytic function khác.

### 11.2. Nếu cần tính analytic trước rồi mới tổng hợp

Đưa analytic vào CTE/subquery trước, sau đó GROUP BY ở query ngoài:

```sql
WITH detail_counts AS (
    SELECT
        employee_id,
        department_id,
        COUNT(*) OVER (
            PARTITION BY department_id
        ) AS department_headcount
    FROM lab_analysts
)
SELECT
    department_id,
    MAX(department_headcount) AS department_headcount
FROM detail_counts
GROUP BY department_id
ORDER BY department_id;
```

Ví dụ này cố ý minh họa hai query block: analytic được tính trên nhân viên chi tiết; query ngoài gom lại một hàng/phòng ban. Trong bài toán thực tế, nếu chỉ cần headcount, GROUP BY đơn giản thường đủ; không cần thêm analytic rồi aggregate lại.

### 11.3. Không lồng analytic trực tiếp

Không đặt một analytic function làm đối số trực tiếp cho analytic function khác trong cùng biểu thức:

```sql
-- Không dùng cách lồng analytic này:
SELECT
    RATIO_TO_REPORT(
        COUNT(*) OVER (PARTITION BY region_id)
    ) OVER ()
FROM lab_sales;
```

Hãy chia thành các query block nếu một phép tính analytic cần dùng kết quả của phép tính analytic trước đó:

```sql
WITH detail_counts AS (
    SELECT
        sale_id,
        region_id,
        COUNT(*) OVER (
            PARTITION BY region_id
        ) AS region_count
    FROM lab_sales
),
region_counts AS (
    SELECT DISTINCT region_id, region_count
    FROM detail_counts
)
SELECT
    region_id,
    region_count,
    RATIO_TO_REPORT(region_count) OVER () AS share_of_region_count_values
FROM region_counts;
```

Ví dụ cuối dùng hai query block để chuyển từ kết quả analytic trên từng hàng sang một hàng cho mỗi vùng trước khi tính tỷ trọng. DISTINCT ở CTE thứ hai bảo đảm mỗi vùng chỉ đóng góp một lần vào mẫu số. Trong hệ thống thực tế, nếu mục tiêu ngay từ đầu là đếm số hàng mỗi vùng, GROUP BY trực tiếp thường đơn giản hơn COUNT analytic rồi DISTINCT.

## 12. Làm tròn, độ chính xác và trình bày tỷ trọng

### 12.1. Giữ tỷ lệ dạng NUMBER khi còn tính toán

RATIO_TO_REPORT trả một giá trị số dạng tỷ lệ, ví dụ 0,25 tương ứng 25%. Nếu cần tính tiếp, hãy giữ tỷ lệ dạng NUMBER:

```sql
RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id
) AS share_ratio
```

Chỉ nhân 100 khi muốn hiển thị phần trăm:

```sql
100 * RATIO_TO_REPORT(amount) OVER (
    PARTITION BY region_id
) AS share_percent
```

Nếu dùng ROUND, hãy làm tròn ở bước trình bày:

```sql
ROUND(
    100 * RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ),
    2
) AS share_percent_2dp
```

Không làm tròn từng amount trước khi tính tổng nếu yêu cầu tài chính cần độ chính xác của dữ liệu gốc. Không cộng các tỷ lệ đã làm tròn để đối soát chính xác; tổng hiển thị có thể là 99,99% hoặc 100,01% do làm tròn từng hàng.

### 12.2. Định dạng số không giống giá trị số

TO_CHAR biến NUMBER thành chuỗi. Chuỗi phần trăm phù hợp giao diện nhưng không còn thuận tiện cho phép tính số học:

```sql
TO_CHAR(
    ROUND(100 * region_share, 2),
    'FM990D00',
    'NLS_NUMERIC_CHARACTERS=''.,'''
) || '%'
```

Nếu hệ thống nhận dữ liệu qua JDBC/REST, cân nhắc trả NUMBER và để tầng giao diện định dạng theo locale. Nếu bắt buộc trả text, định nghĩa rõ dấu thập phân, số chữ số và ký hiệu phần trăm.

### 12.3. Tỷ lệ âm và tỷ lệ vượt 100%

Nếu tổng partition dương nhưng một measure âm, tỷ lệ của measure đó âm. Nếu tổng nhỏ hơn một measure do các hàng khác âm, tỷ lệ của hàng dương có thể vượt 100%. Đây không nhất thiết là lỗi số học; nó phản ánh mẫu số có cả số âm.

Đừng tự ép mọi tỷ trọng vào khoảng 0–100% bằng LEAST/GREATEST nếu điều đó che giấu hoàn tiền, điều chỉnh hoặc số liệu âm. Hãy định nghĩa rõ chỉ tiêu là gross, net hay một tổng có quy tắc loại trừ.

## 13. Hiệu năng và các lỗi thường gặp

### 13.1. COUNT analytic vẫn cần xử lý partition/order

COUNT OVER(PARTITION BY ...) thường cần Oracle tổ chức dữ liệu theo partition và có thể cần sort hoặc thao tác bộ nhớ tùy execution plan. Khi thêm ORDER BY/window frame, chi phí có thể tăng vì phải duy trì thứ tự và cửa sổ. Không nên thêm PARTITION BY/ORDER BY dư thừa vào mọi biểu thức.

Các điểm nên kiểm tra:

- Số hàng đầu vào sau JOIN/WHERE.
- Kích thước và số lượng partition.
- Khả năng sort, PGA/TEMP và thứ tự truy cập.
- Thống kê optimizer và actual rows.
- Có thể lọc dữ liệu đúng nghiệp vụ trước analytic hay không.

### 13.2. RATIO_TO_REPORT không làm giảm số hàng

RATIO_TO_REPORT tính mẫu số trên partition rồi gắn tỷ lệ vào từng hàng. Nếu partition có một triệu hàng, truy vấn vẫn phải xử lý các hàng đó. Nếu chỉ cần tỷ trọng theo sản phẩm, tổng hợp về một hàng/sản phẩm trước để giảm grain và kích thước dữ liệu.

### 13.3. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| COUNT analytic lớn hơn dự kiến | JOIN nhân dòng hoặc query block đã có nhiều chi tiết hơn grain mong muốn | Đếm theo khóa phù hợp; sửa join hoặc tổng hợp trước |
| COUNT(expr) nhỏ hơn COUNT(*) | Một số expr là NULL | Dùng đúng loại COUNT theo định nghĩa dữ liệu |
| COUNT analytic lũy kế thay vì tổng nhóm | Có ORDER BY trong OVER và frame mặc định | Bỏ ORDER BY nếu cần toàn partition; hoặc khai báo frame rõ |
| Các hàng cùng timestamp nhận cùng running count | RANGE mặc định gom peer rows | Dùng ROWS và tie-breaker duy nhất nếu cần đếm từng hàng |
| COUNT(DISTINCT) analytic báo lỗi cú pháp | Có ORDER BY/window frame cùng DISTINCT | Chỉ dùng PARTITION BY trong lời gọi DISTINCT |
| Tỷ trọng không cộng thành 100% | Đang xem một phần nhóm, NULL, số âm hoặc làm tròn | Xác định mẫu số và tập hàng trước analytic |
| Tỷ trọng bằng NULL | Measure NULL hoặc tổng partition NULL | Kiểm tra dữ liệu đầu vào và chính sách NULL |
| Lỗi chia cho 0 | Tổng partition bằng 0 | Guard mẫu số bằng CASE ở query block ngoài |
| Tỷ trọng thay đổi sau khi thêm WHERE | WHERE lọc trước analytic | Tính analytic trong CTE trước rồi lọc ở ngoài |
| Tỷ trọng sai sau JOIN | Header measure bị nhân theo số dòng con | Pre-aggregate về đúng grain |
| Không dùng được analytic trong WHERE | Analytic được tính sau WHERE | Dùng CTE/subquery rồi lọc query ngoài |
| Tổng tỷ lệ hiển thị 99,99% | Làm tròn từng hàng | Giữ precision; chỉ làm tròn khi hiển thị |

### 13.4. Xem execution plan

Ví dụ xem plan ước tính:

```sql
EXPLAIN PLAN FOR
SELECT
    sale_id,
    region_id,
    COUNT(*) OVER (
        PARTITION BY region_id
    ) AS region_count,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS region_share
FROM lab_sales;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

EXPLAIN PLAN cho biết plan ước tính. Khi cần so sánh estimated rows với actual rows, có thể thu thập runtime statistics trong môi trường được phép và xem cursor bằng DBMS_XPLAN.DISPLAY_CURSOR với format phù hợp (ví dụ ALLSTATS LAST). Không bật hint hoặc truy vấn view động trên production nếu chưa hiểu tác động và quyền cần thiết.

## 14. Bài thực hành tổng hợp

Các bài tập sử dụng hai bảng lab_sales và lab_analysts đã tạo ở mục 7. Chạy trong schema thực hành; nếu bảng đã tồn tại, dùng dữ liệu hiện có hoặc chọn tên mới theo quy trình lab.

### Phần A — So sánh COUNT aggregate và analytic

Chạy hai truy vấn:

```sql
SELECT region_id, COUNT(*) AS sale_count
FROM lab_sales
GROUP BY region_id
ORDER BY region_id;

SELECT sale_id, region_id,
       COUNT(*) OVER (PARTITION BY region_id) AS region_count
FROM lab_sales
ORDER BY region_id, sale_id;
```

Trả lời:

1. Truy vấn nào trả một hàng/vùng?
2. Truy vấn nào giữ từng giao dịch?
3. Vì sao COUNT analytic vẫn hiển thị count 3 trên cả ba hàng NORTH?
4. Với vùng WEST, COUNT(*) và COUNT(amount) lần lượt trả bao nhiêu?

### Phần B — COUNT DISTINCT trong partition

```sql
SELECT
    sale_id,
    region_id,
    product_id,
    COUNT(DISTINCT product_id) OVER (
        PARTITION BY region_id
    ) AS distinct_products
FROM lab_sales
ORDER BY region_id, sale_id;
```

Xác định số sản phẩm khác nhau ở NORTH và SOUTH. Thử thêm ORDER BY vào lời gọi COUNT DISTINCT và giải thích vì sao cú pháp bị giới hạn.

### Phần C — Running count và peer rows

```sql
SELECT
    sale_id,
    region_id,
    sold_at,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at
    ) AS range_count,
    COUNT(*) OVER (
        PARTITION BY region_id
        ORDER BY sold_at, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_count
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sold_at, sale_id;
```

Quan sát hai giao dịch NORTH cùng ngày 2026-01-01. Giải thích vì sao RANGE mặc định có thể cho cùng count ở các peer rows trong khi ROWS cộng từng hàng theo thứ tự có tie-breaker.

### Phần D — Tỷ trọng giao dịch trong vùng

```sql
SELECT
    sale_id,
    region_id,
    amount,
    RATIO_TO_REPORT(amount) OVER (
        PARTITION BY region_id
    ) AS share_ratio,
    ROUND(
        100 * RATIO_TO_REPORT(amount) OVER (
            PARTITION BY region_id
        ),
        2
    ) AS share_percent
FROM lab_sales
WHERE region_id IN ('NORTH', 'SOUTH')
ORDER BY region_id, sale_id;
```

Xác nhận tỷ trọng NORTH cộng thành 1 và SOUTH cộng thành 1 nếu bỏ qua hàng NULL. Tính bằng tay 100/600, 200/600, 300/600 và 150/400, 250/400.

### Phần E — Tổng partition bằng 0

Chạy truy vấn guarded ratio ở mục 6.2. Xác nhận vùng ZERO được trả NULL theo chính sách đã chọn, không tạo tỷ trọng giả. Thử thay CASE bằng phép chia trực tiếp để quan sát lỗi trên môi trường lab; không cần chạy nếu công cụ/database đang dùng không cho phép thử lỗi.

### Phần F — Tính tỷ trọng theo sản phẩm

Chạy CTE PRODUCT_TOTALS ở mục 8.3. Tính lại doanh thu sản phẩm trong từng vùng bằng tay và giải thích vì sao phải GROUP BY trước khi gọi RATIO_TO_REPORT.

### Phần G — Lọc sau khi tính tỷ trọng

Chạy hai truy vấn ở mục 9.1 và 9.2. Vì sao tỷ trọng của sản phẩm 10 ở NORTH khác nhau? Chọn kết quả nào nếu báo cáo chỉ ẩn sản phẩm khác nhưng mẫu số vẫn phải là toàn vùng?

### Phần H — Headcount theo chức danh

Chạy truy vấn JOB_COUNTS ở mục 8.4. Đối chiếu:

- Department 10: DEV có 2 người, QA có 1 người; headcount là 3.
- Department 20: QA có 2 người; headcount là 2.
- Department NULL: HR có 1 người.

Giải thích vì sao COUNT(*) OVER trong query ngoài đếm số job groups, còn SUM(employees_in_job) OVER mới cho tổng nhân viên phòng ban.

### Phần I — COUNT OVER cho phân trang

Chạy truy vấn phân trang ở mục 9.5. Thử OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY. Tổng số hàng khớp bộ lọc có thay đổi không? Điều gì xảy ra nếu OFFSET lớn đến mức trang rỗng?

## 15. Nguyên tắc thực hành tốt

1. **Xác định grain trước khi tính.** Một hàng là giao dịch, dòng đơn hàng, sản phẩm đã tổng hợp hay phòng ban?
2. **Chọn đúng COUNT.** COUNT(*) đếm hàng; COUNT(expr) bỏ NULL; COUNT(DISTINCT expr) đếm giá trị khác nhau.
3. **Chỉ dùng PARTITION BY theo nhóm nghiệp vụ cần đo.** Đổi partition key là đổi mẫu số và ý nghĩa của kết quả.
4. **Không thêm ORDER BY nếu chỉ cần tổng nhóm.** Với COUNT analytic, ORDER BY có thể tạo running count theo frame mặc định.
5. **Khai báo ROWS và tie-breaker khi cần thứ tự từng hàng.** Không dựa vào thứ tự tình cờ giữa các peer rows.
6. **Đặt RATIO_TO_REPORT trên measure đúng grain.** Tổng hợp trước nếu tỷ trọng cần theo sản phẩm/đơn hàng/chi nhánh.
7. **Guard tổng bằng 0.** Chọn NULL, 0 hoặc trạng thái N/A theo nghiệp vụ; không để phép chia không xác định.
8. **Phân biệt NULL với 0.** NULL có thể có nghĩa chưa ghi nhận, còn 0 là một giá trị đã ghi nhận.
9. **Hiểu WHERE trước analytic.** Nếu cần lọc hiển thị nhưng giữ mẫu số toàn nhóm, tính trong CTE rồi lọc ở query ngoài.
10. **Không tính trên dữ liệu đã bị fan-out.** Kiểm tra JOIN và aggregate các bảng con trước nếu cần đúng một hàng/khóa cha.
11. **Giữ tỷ lệ là NUMBER khi còn tính toán.** Chỉ TO_CHAR ở bước trình bày; làm tròn ở cuối.
12. **Đọc execution plan và đo dữ liệu thực.** COUNT/RATIO_TO_REPORT không làm giảm số hàng và vẫn có thể cần sort/partition trên tập dữ liệu lớn.

## 16. Câu hỏi tự kiểm tra

1. COUNT(*) và COUNT(expr) khác nhau thế nào khi expr có NULL?
2. COUNT(*) OVER() khác COUNT(*) GROUP BY region_id ra sao về số hàng kết quả?
3. PARTITION BY region_id, product_id chia tập dữ liệu thành những nhóm nào?
4. Vì sao COUNT analytic trong query có GROUP BY có thể đếm số nhóm job thay vì số nhân viên?
5. COUNT(DISTINCT expr) OVER có giới hạn gì về ORDER BY và window frame trong Oracle?
6. Khi COUNT analytic có ORDER BY nhưng không khai báo frame, Oracle dùng kiểu frame mặc định nào?
7. RANGE và ROWS khác nhau ra sao khi có nhiều hàng cùng giá trị ORDER BY?
8. RATIO_TO_REPORT(amount) OVER(PARTITION BY region_id) dùng mẫu số nào?
9. Nếu amount là NULL, tỷ trọng của hàng đó là gì?
10. Nếu tổng partition bằng 0, vì sao cần guard trước phép chia?
11. Vì sao tổng các tỷ lệ đã làm tròn có thể không đúng chính xác 100%?
12. Tại sao WHERE product_id = 10 trong cùng query block làm thay đổi mẫu số RATIO_TO_REPORT?
13. Làm thế nào chỉ hiển thị top 3 sản phẩm nhưng tỷ trọng vẫn tính trên toàn bộ sản phẩm?
14. Vì sao COUNT(*) OVER sau JOIN có thể đếm nhiều dòng hơn số đơn hàng?
15. Khi cần tỷ trọng theo sản phẩm trong vùng, vì sao nên tổng hợp theo region_id và product_id trước?
16. COUNT OVER hữu ích thế nào trong truy vấn phân trang? Trường hợp trang rỗng có hạn chế gì?

## 17. Mô hình ghi nhớ

```text
COUNT ANALYTIC
    │
    ├── COUNT(*)       → mọi hàng
    ├── COUNT(expr)    → bỏ NULL
    ├── COUNT(DISTINCT expr) → giá trị khác nhau
    │
    ├── OVER()         → toàn bộ query block
    ├── PARTITION BY   → đếm trong từng nhóm
    └── ORDER BY/frame → running count hoặc cửa sổ trượt

RATIO_TO_REPORT(expr)
    │
    ├── expr / SUM(expr) trong partition
    ├── OVER()         → tỷ trọng toàn tập
    ├── PARTITION BY   → tỷ trọng trong nhóm
    ├── expr NULL      → tỷ trọng NULL
    └── tổng bằng 0    → cần chính sách/guard

ĐỂ TỶ TRỌNG ĐÚNG
    │
    ├── Chọn đúng grain
    ├── Kiểm tra JOIN/fan-out
    ├── Tính analytic trước khi lọc hiển thị
    ├── Giữ NUMBER, làm tròn ở bước trình bày
    └── Dùng CTE/subquery khi cần nhiều giai đoạn
```

**Điểm cần nhớ:** COUNT analytic bổ sung số đếm vào từng hàng mà không gom mất chi tiết; RATIO_TO_REPORT cho biết mỗi giá trị đóng góp bao nhiêu trong tổng partition. Kết quả chỉ đúng khi tập đầu vào, partition key, grain và mẫu số đúng với câu hỏi nghiệp vụ. Hãy xử lý NULL và tổng bằng 0 có chủ đích, tránh fan-out sau JOIN, và dùng query block bên ngoài khi cần lọc kết quả analytic mà vẫn giữ tỷ trọng trên toàn nhóm.
