# WITH ROLLUP, GROUPING và phân biệt dòng tổng với NULL dữ liệu

Khi lập báo cáo, ngoài các dòng chi tiết theo từng nhóm, ta thường cần thêm tổng phụ theo từng cấp và tổng cộng toàn bộ. MySQL hỗ trợ `GROUP BY ... WITH ROLLUP` để tạo các dòng tổng này trong cùng một truy vấn. Tuy nhiên, dòng tổng được tạo ra dùng `NULL` làm giá trị đại diện cho cấp nhóm đã được cuộn lên. Nếu dữ liệu gốc cũng có `NULL`, chỉ nhìn vào cột nhóm sẽ không thể biết đó là NULL thật hay NULL do ROLLUP tạo ra.

Hàm `GROUPING()` giải quyết sự mơ hồ đó: nó cho biết một giá trị NULL trong dòng kết quả có phải placeholder do phép tổng hợp tạo ra hay không. Bài học này hướng dẫn cách dùng `WITH ROLLUP`, đọc đúng thứ tự các cấp tổng, phân biệt NULL dữ liệu với NULL tổng hợp, định dạng và lọc dòng tổng, đồng thời xử lý khác biệt phiên bản MySQL.

Trong module `DATABASE_MYSQL`, các kỹ thuật này hỗ trợ truy vấn báo cáo doanh thu, số lượng đơn hàng, tồn kho và các chỉ số được tổng hợp theo nhiều chiều. Kết quả cần giữ được ý nghĩa nghiệp vụ: dòng chi tiết có dữ liệu NULL phải khác dòng subtotal hoặc grand total.

## 1. Tổng hợp theo nhiều cấp là gì?

Giả sử doanh nghiệp muốn báo cáo doanh thu theo khu vực và danh mục sản phẩm. Một báo cáo hữu ích thường cần ba cấp:

1. **Dòng chi tiết:** doanh thu của từng cặp khu vực và danh mục.
2. **Subtotal theo khu vực:** tổng doanh thu của mọi danh mục trong một khu vực.
3. **Grand total:** tổng doanh thu của toàn bộ dữ liệu được chọn.

Nếu chỉ dùng `GROUP BY region, category`, truy vấn chỉ trả về cấp chi tiết. Bạn có thể viết thêm các truy vấn riêng cho subtotal và grand total rồi ghép bằng `UNION ALL`, nhưng `WITH ROLLUP` tạo các cấp tổng theo thứ tự nhóm trong một phép tổng hợp.

Ví dụ hình dung:

```text
Khu vực      Danh mục       Doanh thu     Loại dòng
North        Hardware          100        Chi tiết
North        Software          150        Chi tiết
North        NULL              250        Tổng North
South        Hardware          200        Chi tiết
South        NULL               75        Chi tiết có category NULL
South        NULL              275        Tổng South
NULL         Hardware           50        Chi tiết có region NULL
NULL         NULL               50        Tổng nhóm region NULL
NULL         NULL              575        Tổng cộng
```

Các dòng có cùng giá trị NULL ở cột nhóm có thể mang ý nghĩa khác nhau. Vì thế, báo cáo cần thêm cờ nhận diện cấp tổng.

## 2. Chuẩn bị dữ liệu thực hành

Tạo bảng thử nghiệm với dữ liệu có cả NULL thật ở hai cột nhóm:

```sql
CREATE TABLE sales_rollup_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region VARCHAR(40) NULL,
    category VARCHAR(40) NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_sales_rollup_region_category (region, category)
) ENGINE=InnoDB;

INSERT INTO sales_rollup_demo (region, category, amount)
VALUES
    ('North', 'Hardware', 100.00),
    ('North', 'Software', 150.00),
    ('South', 'Hardware', 200.00),
    (NULL,    'Hardware',  50.00),
    ('South', NULL,        75.00);
```

Trong fixture này:

- `region IS NULL` ở hàng thứ tư nghĩa là dữ liệu nguồn chưa xác định khu vực.
- `category IS NULL` ở hàng thứ năm nghĩa là dữ liệu nguồn chưa xác định danh mục.
- `amount` luôn có giá trị để tổng doanh thu không bị mơ hồ do NULL.

Kiểm tra dữ liệu nguồn:

```sql
SELECT id, region, category, amount
FROM sales_rollup_demo
ORDER BY id;
```

## 3. Cú pháp `GROUP BY ... WITH ROLLUP`

Cú pháp cơ bản:

```sql
SELECT group_column_1,
       group_column_2,
       aggregate_function(...)
FROM table_name
GROUP BY group_column_1, group_column_2 WITH ROLLUP;
```

`WITH ROLLUP` yêu cầu MySQL tạo thêm các dòng tổng hợp từ phải sang trái theo danh sách biểu thức `GROUP BY`.

Với:

```sql
GROUP BY region, category WITH ROLLUP
```

MySQL tạo các cấp:

| Cấp | `region` | `category` | Ý nghĩa |
|---|---|---|---|
| Chi tiết | Giá trị nhóm | Giá trị nhóm | Tổng của từng cặp region/category. |
| Subtotal | Giá trị region | `NULL` | Tổng mọi category trong region đó. |
| Grand total | `NULL` | `NULL` | Tổng toàn bộ các nhóm. |

Chạy truy vấn đầu tiên:

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Kết quả có các dòng chi tiết, subtotal theo khu vực và grand total. Một số hàng có `region` hoặc `category` NULL từ dữ liệu nguồn; các dòng tổng cũng dùng NULL để biểu diễn cấp đã cuộn lên. Đây chính là lý do cần `GROUPING()`.

## 4. Thứ tự cột trong GROUP BY quyết định thứ tự subtotal

ROLLUP là phép tổng hợp theo phân cấp. Với `GROUP BY region, category WITH ROLLUP`, cấp category được cuộn trước, tạo subtotal theo region, sau đó region được cuộn để tạo grand total.

Nếu đổi thứ tự:

```sql
SELECT
    category,
    region,
    SUM(amount) AS revenue
FROM sales_rollup_demo
GROUP BY category, region WITH ROLLUP;
```

Các cấp sẽ là:

- Chi tiết theo category và region.
- Subtotal theo category (region được cuộn thành NULL).
- Grand total.

Thứ tự biểu thức trong `GROUP BY` vì vậy là một phần của thiết kế báo cáo, không chỉ là cách trình bày. Nếu cần subtotal theo region và subtotal theo category trong cùng báo cáo, một ROLLUP đơn lẻ không tạo ra mọi tổ hợp tổng hợp tùy ý.

MySQL hỗ trợ `WITH ROLLUP`; không nên giả định cú pháp `GROUPING SETS` hoặc `CUBE` của một số hệ quản trị khác có thể dùng nguyên trạng trong MySQL. Với các tổ hợp subtotal không theo một cây phân cấp, có thể ghép các truy vấn riêng bằng `UNION ALL`.

## 5. Vì sao NULL dữ liệu và NULL tổng hợp bị trùng hình thức?

Ở truy vấn:

```sql
SELECT region, category, SUM(amount) AS revenue
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Một dòng có `region = NULL, category = 'Hardware'` có thể là nhóm chi tiết chứa dữ liệu nguồn không xác định khu vực. Một dòng có `region = 'North', category = NULL` có thể là subtotal North, nhưng cũng có thể là nhóm chi tiết có dữ liệu nguồn `category IS NULL`.

Ngay cả cặp `(NULL, NULL)` cũng có thể xuất hiện nhiều lần với ý nghĩa khác nhau:

- Dòng chi tiết thuộc nhóm dữ liệu có `region IS NULL` và `category IS NULL`, nếu dữ liệu nguồn có cặp đó.
- Subtotal của nhóm region NULL, khi category được cuộn lên.
- Grand total, khi cả region và category đều được cuộn lên.

Không thể phân loại chắc chắn chỉ bằng:

```sql
CASE WHEN region IS NULL THEN 'Tổng cộng' ... END
```

Điều kiện đó sẽ gắn nhãn sai cho hàng dữ liệu nguồn có region NULL. Cần một tín hiệu nói rõ cột nào đang được ROLLUP cuộn lên.

## 6. `GROUPING()` nhận diện NULL do ROLLUP tạo ra

`GROUPING(expr)` trả về:

- `1` nếu NULL của biểu thức trong dòng kết quả được tạo ra do ROLLUP cuộn cấp nhóm đó.
- `0` nếu biểu thức vẫn là một phần của cấp nhóm hiện tại, kể cả khi giá trị dữ liệu nguồn thực sự là NULL.

Biểu thức truyền vào `GROUPING()` phải tương ứng với biểu thức trong `GROUP BY`. Với ví dụ hiện tại:

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS region_rolled_up,
    GROUPING(category) AS category_rolled_up
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Hai cột cờ cho biết cấp nào được cuộn:

| Dòng | `GROUPING(region)` | `GROUPING(category)` | Ý nghĩa |
|---|---:|---:|---|
| Chi tiết, cả hai giá trị có dữ liệu | 0 | 0 | Nhóm chi tiết. |
| Chi tiết có region NULL trong dữ liệu nguồn | 0 | 0 | Vẫn là nhóm chi tiết. |
| Chi tiết có category NULL trong dữ liệu nguồn | 0 | 0 | Vẫn là nhóm chi tiết. |
| Subtotal theo region | 0 | 1 | Category được cuộn lên. |
| Grand total | 1 | 1 | Cả region và category được cuộn lên. |

Điểm quan trọng: `GROUPING(region) = 0` không có nghĩa region khác NULL; nó có nghĩa region chưa bị cuộn. Nếu giá trị nguồn của region là NULL, cột vẫn NULL nhưng cờ GROUPING bằng 0.

### Ví dụ phân biệt chính xác trong fixture

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Đối với hàng nguồn `('South', NULL, 75.00)`, kết quả chi tiết có `g_region = 0` và `g_category = 0`. Dòng subtotal South có cùng `region = 'South'` và `category = NULL`, nhưng có `g_region = 0`, `g_category = 1`. Hai dòng có cùng giá trị hiển thị ở cột nhóm nhưng được phân biệt bằng cờ.

Đối với nhóm nguồn có `region IS NULL`, subtotal của nhóm đó có `g_region = 0`, `g_category = 1`; grand total có `g_region = 1`, `g_category = 1`. Nhờ vậy, ngay cả khi cả hai cột đều hiển thị NULL, ta vẫn nhận ra đúng loại dòng.

## 7. Định dạng nhãn dòng chi tiết, subtotal và grand total

Sau khi có cờ `GROUPING()`, dùng `CASE` để hiển thị nhãn có ý nghĩa. Không dùng `COALESCE(region, 'Tổng cộng')` một cách đơn giản vì nó sẽ nhầm NULL nguồn với NULL do ROLLUP.

```sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'Tất cả khu vực'
        WHEN region IS NULL THEN '(Chưa xác định khu vực)'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(category) = 1 THEN 'Tất cả danh mục'
        WHEN category IS NULL THEN '(Chưa phân loại)'
        ELSE category
    END AS category_label,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Quy tắc hiển thị:

1. Kiểm tra `GROUPING()` trước để nhận diện cấp tổng.
2. Nếu không phải dòng tổng nhưng giá trị nguồn NULL, hiển thị nhãn như “Chưa xác định”.
3. Nếu giá trị có dữ liệu, hiển thị giá trị gốc.

Thứ tự các nhánh `CASE` rất quan trọng. Nếu kiểm tra `region IS NULL` trước `GROUPING(region) = 1`, dòng grand total sẽ bị gắn nhãn “Chưa xác định khu vực” thay vì “Tất cả khu vực”.

Trong API hoặc báo cáo xuất file, nên trả thêm cờ `g_region`, `g_category` hoặc một `row_type` đã được tính rõ ràng. Đừng buộc tầng giao diện suy đoán loại dòng từ nhãn văn bản.

## 8. Phân loại dòng bằng `row_type`

Một báo cáo thường cần một trường đơn giản để client phân biệt chi tiết, subtotal và grand total:

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category,
    CASE
        WHEN GROUPING(region) = 1 THEN 'GRAND_TOTAL'
        WHEN GROUPING(category) = 1 THEN 'REGION_SUBTOTAL'
        ELSE 'DETAIL'
    END AS row_type
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

Vì cấp subtotal theo region có `GROUPING(category) = 1`, còn grand total có `GROUPING(region) = 1`, nhánh grand total phải được kiểm tra trước. Nếu đảo hai điều kiện, grand total cũng có thể bị phân loại thành subtotal.

Nếu cần phân biệt subtotal của nhóm region NULL với subtotal của một region có tên, cờ `g_region` vẫn bằng 0 ở cả hai trường hợp; giá trị `region` cho biết nhóm nguồn là NULL hay có tên. `row_type` cho biết cấp tổng, còn cột nhóm gốc cho biết giá trị nhóm.

## 9. Lọc dữ liệu nguồn bằng WHERE và lọc kết quả tổng hợp bằng HAVING

`WHERE` lọc các hàng nguồn trước khi nhóm và tạo ROLLUP. `HAVING` lọc các nhóm sau khi aggregate, bao gồm cả các dòng subtotal và grand total. Nếu dùng HAVING mà không xét `GROUPING()`, bạn có thể vô tình loại bỏ dòng tổng.

Ví dụ chỉ tính doanh thu từ một tập khu vực:

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
WHERE amount > 0
GROUP BY region, category WITH ROLLUP;
```

Điều kiện `WHERE amount > 0` loại hàng nguồn trước khi tính mọi cấp tổng.

Ví dụ chỉ giữ subtotal/grand total và nhóm chi tiết đạt ngưỡng:

```sql
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP
HAVING GROUPING(region) = 1
    OR GROUPING(category) = 1
    OR SUM(amount) >= 100;
```

Điều kiện này giữ mọi dòng tổng và chỉ giữ dòng chi tiết có doanh thu ít nhất 100. Nếu chỉ viết `HAVING SUM(amount) >= 100`, một số subtotal hoặc grand total có thể bị loại nếu không đạt ngưỡng. Hãy xác định rõ ngưỡng áp dụng cho chi tiết, subtotal hay cả hai.

## 10. Đếm hàng và xử lý NULL trong tổng hợp ROLLUP

Các hàm aggregate có quy tắc NULL riêng:

- `COUNT(*)` đếm mọi hàng trong nhóm.
- `COUNT(expr)` chỉ đếm hàng có `expr` khác NULL.
- `SUM(expr)`, `AVG(expr)`, `MIN(expr)` và `MAX(expr)` bỏ qua NULL trong đối số.
- Nếu không có giá trị khác NULL cho một aggregate, kết quả có thể là NULL.

Ví dụ:

```sql
SELECT
    region,
    category,
    COUNT(*) AS source_rows,
    COUNT(category) AS rows_with_category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
GROUP BY region, category WITH ROLLUP;
```

`COUNT(category)` không đếm hàng nguồn có category NULL, nhưng vẫn tính trên các nhóm subtotal/grand total theo cùng quy tắc. `COUNT(*)` đếm tất cả hàng nguồn đóng góp vào mỗi nhóm. Không nhầm `COUNT(category) = 0` với một dòng subtotal; hãy kết hợp các cờ GROUPING để hiểu cấp tổng.

Nếu muốn hiển thị doanh thu bằng 0 thay cho NULL khi không có dữ liệu, có thể dùng `COALESCE(SUM(amount), 0)`. Chỉ làm vậy khi 0 thực sự là cách biểu diễn phù hợp cho báo cáo; NULL có thể có ý nghĩa khác với tổng bằng không.

## 11. Sắp xếp kết quả có ROLLUP

Thứ tự kết quả của ROLLUP phản ánh cấu trúc tổng hợp, nhưng nếu báo cáo cần thứ tự tùy chỉnh, hãy sắp xếp rõ ràng theo cờ nhóm. Cách dễ kiểm soát là bọc truy vấn ROLLUP trong derived table rồi dùng `ORDER BY` ở truy vấn ngoài:

```sql
SELECT
    region,
    category,
    revenue,
    g_region,
    g_category,
    row_type
FROM (
    SELECT
        region,
        category,
        SUM(amount) AS revenue,
        GROUPING(region) AS g_region,
        GROUPING(category) AS g_category,
        CASE
            WHEN GROUPING(region) = 1 THEN 'GRAND_TOTAL'
            WHEN GROUPING(category) = 1 THEN 'REGION_SUBTOTAL'
            ELSE 'DETAIL'
        END AS row_type
    FROM sales_rollup_demo
    GROUP BY region, category WITH ROLLUP
) AS rollup_rows
ORDER BY
    g_region,
    region,
    g_category,
    category;
```

Trong ví dụ này, dòng grand total có `g_region = 1` nên được xếp sau các nhóm region có `g_region = 0`. Subtotal và chi tiết được phân biệt bằng `g_category`. Nếu muốn subtotal đứng sau toàn bộ detail của từng region, có thể thay đổi biểu thức sắp xếp dựa trên `g_category` và các cột nhóm.

Không dùng riêng `region IS NULL` hoặc `category IS NULL` để sắp xếp dòng tổng, vì dữ liệu nguồn NULL cũng có thể nằm trong cùng vùng giá trị. Hãy dùng cờ GROUPING.

## 12. Nhiều cấp ROLLUP và ý nghĩa của từng cờ

Với ba cột:

```sql
GROUP BY year, region, category WITH ROLLUP
```

MySQL tạo các cấp theo thứ tự:

1. Chi tiết theo năm, khu vực, danh mục.
2. Subtotal theo năm và khu vực (category được cuộn).
3. Subtotal theo năm (region và category được cuộn).
4. Grand total (cả ba cột được cuộn).

Truy vấn:

```sql
SELECT
    sales_year,
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(sales_year) AS g_year,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM yearly_sales
GROUP BY sales_year, region, category WITH ROLLUP;
```

Các cờ giúp phân loại chính xác:

| Cấp | `g_year` | `g_region` | `g_category` |
|---|---:|---:|---:|
| Chi tiết | 0 | 0 | 0 |
| Subtotal năm/khu vực | 0 | 0 | 1 |
| Subtotal năm | 0 | 1 | 1 |
| Grand total | 1 | 1 | 1 |

Với mỗi cấp, các cột phía bên phải trong danh sách GROUP BY được cuộn dần. Đây là quy tắc phân cấp cốt lõi của ROLLUP.

## 13. Giới hạn phiên bản và `GROUPING()`

`WITH ROLLUP` có mặt trong các phiên bản MySQL lâu đời, nhưng hàm `GROUPING()` là tính năng của MySQL 8.0. Trên MySQL 5.7, không có cách dùng `GROUPING()` tương đương để phân biệt trực tiếp NULL tổng hợp với NULL nguồn trong kết quả ROLLUP. Hãy kiểm tra phiên bản server trước khi dựa vào hàm này:

```sql
SELECT VERSION();
```

Với MySQL 8.0 trở lên, có thể dùng `GROUPING(region)` và `GROUPING(category)` trong truy vấn ROLLUP. Trên bản cũ không có hàm, tránh suy đoán từ NULL; hãy cân nhắc tự tạo các cấp báo cáo bằng `UNION ALL` để gắn nhãn rõ ràng.

Ngoài ra, cú pháp và giới hạn đi kèm `WITH ROLLUP` có thể khác giữa các bản MySQL. Nếu cần `ORDER BY` tùy chỉnh hoặc kết hợp với các tính năng khác, kiểm tra tài liệu đúng phiên bản; cách bọc kết quả ROLLUP trong derived table để sắp xếp ở truy vấn ngoài giúp tách phần tổng hợp khỏi phần trình bày.

## 14. Thay thế bằng UNION ALL khi cần kiểm soát từng cấp

Khi cần chạy trên phiên bản không có `GROUPING()`, hoặc cần các subtotal không theo một cây ROLLUP, có thể tạo từng cấp bằng `UNION ALL`. Mỗi nhánh thêm một cột loại dòng hoặc cờ rõ ràng.

Ví dụ trên MySQL 8.0 dùng CTE để tránh lặp lại điều kiện lọc:

```sql
WITH filtered_sales AS (
    SELECT region, category, amount
    FROM sales_rollup_demo
    WHERE amount > 0
)
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    0 AS g_region,
    0 AS g_category,
    'DETAIL' AS row_type
FROM filtered_sales
GROUP BY region, category

UNION ALL

SELECT
    region,
    NULL AS category,
    SUM(amount) AS revenue,
    0 AS g_region,
    1 AS g_category,
    'REGION_SUBTOTAL' AS row_type
FROM filtered_sales
GROUP BY region

UNION ALL

SELECT
    NULL AS region,
    NULL AS category,
    SUM(amount) AS revenue,
    1 AS g_region,
    1 AS g_category,
    'GRAND_TOTAL' AS row_type
FROM filtered_sales;
```

Ở đây, NULL trong nhánh detail là NULL dữ liệu nguồn; cờ `g_region` và `g_category` đều bằng 0. NULL trong subtotal hoặc grand total được gắn cờ rõ ràng. `UNION ALL` giữ tất cả các dòng, kể cả khi giá trị cột nhóm trùng nhau giữa detail và subtotal. Dùng `UNION` sẽ loại các hàng trùng hoàn toàn và có thể làm mất một dòng tổng hợp hợp lệ.

Nếu dùng MySQL 5.7, thay CTE bằng derived table lặp lại hoặc bảng tạm trong phạm vi session. Điều quan trọng là mỗi nhánh phải áp dụng cùng điều kiện lọc, cùng định nghĩa aggregate và cùng kiểu dữ liệu tương thích ở các vị trí SELECT.

## 15. Hiệu năng và cách kiểm tra kế hoạch thực thi

ROLLUP vẫn phải đọc và nhóm dữ liệu nguồn. Chi phí phụ thuộc số hàng đầu vào, số nhóm, kích thước khóa nhóm, index, bộ nhớ và cách optimizer thực hiện truy vấn.

Một số nguyên tắc:

- Lọc dữ liệu nguồn bằng `WHERE` trước khi nhóm nếu điều kiện có thể áp dụng mà không làm sai ý nghĩa báo cáo.
- Tạo index phù hợp với các cột lọc và nhóm khi workload chứng minh có lợi; index không bảo đảm mọi ROLLUP đều tránh được sort hoặc temporary table.
- Tránh chọn quá nhiều cột không cần thiết trong truy vấn tổng hợp.
- Dùng kiểu số phù hợp: `DECIMAL` cho số tiền và `BIGINT` cho số lượng lớn; tránh cộng tiền bằng `FLOAT` nếu cần chính xác thập phân.
- Dùng `EXPLAIN` để xem access path, key, estimated rows và các bước grouping/sort.
- Đo bằng dữ liệu gần thực tế; bảng nhỏ có thể khiến optimizer chọn table scan dù có index.

Ví dụ:

```sql
EXPLAIN
SELECT
    region,
    category,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(category) AS g_category
FROM sales_rollup_demo
WHERE amount >= 0
GROUP BY region, category WITH ROLLUP;
```

`EXPLAIN ANALYZE` có thể thực thi truy vấn để cung cấp số liệu thực tế trên các phiên bản hỗ trợ. Chỉ chạy khi chấp nhận chi phí thực thi trên môi trường tương ứng; với truy vấn báo cáo lớn, ưu tiên thử trên staging hoặc bản sao dữ liệu.

Không nên thêm `GROUPING()` vào mọi truy vấn chỉ để có thêm cột. Dùng nó khi cần phân biệt cấp tổng hoặc khi kết quả được đưa sang hệ thống khác cần metadata dòng.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ mọi NULL trong kết quả ROLLUP đều là dòng tổng | Dữ liệu nguồn NULL bị gắn nhãn sai | Dùng `GROUPING()` để phân biệt. |
| Kiểm tra `region IS NULL` trước `GROUPING(region)` | Grand total bị gắn nhãn là nhóm chưa xác định | Kiểm tra cờ GROUPING trước, rồi mới kiểm tra NULL dữ liệu. |
| Đảo thứ tự cột trong GROUP BY mà không xem xét phân cấp | Subtotal xuất hiện theo chiều khác | Xác định chiều subtotal trước khi sắp xếp cột nhóm. |
| Dùng `HAVING` chỉ theo SUM mà quên dòng tổng | Subtotal/grand total có thể bị lọc mất | Kết hợp điều kiện với `GROUPING()`. |
| Dùng `UNION` thay cho `UNION ALL` khi tự ghép cấp tổng | Dòng chi tiết và dòng tổng trùng giá trị có thể bị loại | Dùng `UNION ALL` và cột `row_type`/cờ. |
| Giả định MySQL hỗ trợ `GROUPING SETS` hoặc `CUBE` | Câu SQL không tương thích | Dùng ROLLUP theo phân cấp hoặc UNION ALL. |
| Dùng GROUPING() trên phiên bản không hỗ trợ | Lỗi hàm không tồn tại | Kiểm tra `VERSION()` và dùng phương án thay thế. |
| Sắp xếp chỉ bằng cột nhóm có NULL | Thứ tự dòng tổng lẫn với NULL nguồn | Sắp xếp bằng cờ GROUPING ở truy vấn ngoài. |
| Dùng `COUNT(column)` để đếm tất cả hàng | Bỏ qua hàng có column NULL | Dùng `COUNT(*)` nếu muốn đếm hàng. |

## 17. Bài tập thực hành

### Bài tập A — Tạo ROLLUP hai cấp

1. Tạo bảng `sales_rollup_demo` và nạp dữ liệu fixture.
2. Chạy `GROUP BY region, category WITH ROLLUP`.
3. Ghi lại các dòng chi tiết, subtotal theo region và grand total.
4. Đổi thứ tự thành `GROUP BY category, region WITH ROLLUP`.
5. Giải thích vì sao cấp subtotal thay đổi.

### Bài tập B — Phân biệt NULL nguồn và NULL tổng hợp

1. Giữ các hàng có region NULL và category NULL trong fixture.
2. Chạy ROLLUP cùng `GROUPING(region)` và `GROUPING(category)`.
3. Tìm dòng chi tiết có category NULL và subtotal của cùng region.
4. So sánh hai cột nhóm và hai cờ GROUPING.
5. Tạo `row_type` với ba nhãn DETAIL, REGION_SUBTOTAL và GRAND_TOTAL.

### Bài tập C — Lọc subtotal và grand total

1. Dùng `WHERE` để lọc các hàng nguồn theo một điều kiện.
2. Dùng `HAVING` để chỉ giữ nhóm có tổng đạt ngưỡng.
3. Điều chỉnh HAVING để vẫn giữ subtotal và grand total.
4. Giải thích thứ tự xử lý của WHERE, GROUP BY/ROLLUP và HAVING.

### Bài tập D — Tự dựng tổng bằng UNION ALL

1. Viết truy vấn detail, subtotal theo region và grand total riêng.
2. Ghép bằng `UNION ALL`.
3. Thêm cột cờ và `row_type` cho từng nhánh.
4. So sánh kết quả với ROLLUP trên MySQL 8.0.
5. Giải thích vì sao `UNION` có thể làm mất dòng tổng hợp hợp lệ.

### Bài tập E — Kiểm tra hiệu năng

1. Chạy `EXPLAIN` cho truy vấn ROLLUP.
2. Thử lọc nguồn bằng WHERE và so sánh estimated rows.
3. Đánh giá index trên `(region, category)` với dữ liệu lớn hơn.
4. Nếu phiên bản hỗ trợ, dùng `EXPLAIN ANALYZE` trên môi trường thử nghiệm.
5. Ghi lại chi phí, số nhóm và lý do chọn index hoặc table scan.

Bạn hoàn thành bài khi có thể tạo các cấp tổng bằng ROLLUP, giải thích ảnh hưởng của thứ tự GROUP BY, phân biệt NULL nguồn với NULL tổng hợp bằng GROUPING(), gắn nhãn dòng chính xác, lọc mà không làm mất tổng cần thiết và chọn UNION ALL khi cần các grouping set tùy chỉnh.

## 18. Nguyên tắc cần ghi nhớ

- `GROUP BY ... WITH ROLLUP` tạo subtotal và grand total theo thứ tự phân cấp của các biểu thức nhóm.
- Với `GROUP BY region, category WITH ROLLUP`, MySQL tạo chi tiết, subtotal theo region rồi grand total.
- NULL trong dòng tổng hợp có thể trùng hình thức với NULL thật trong dữ liệu nguồn.
- `GROUPING(expr) = 1` nhận diện cột đã bị ROLLUP cuộn lên; `0` nghĩa là cột vẫn thuộc cấp nhóm hiện tại, kể cả khi giá trị nguồn NULL.
- Trong `CASE`, kiểm tra GROUPING trước rồi mới kiểm tra `IS NULL` để định dạng nhãn.
- Dùng cờ GROUPING hoặc `row_type` khi trả kết quả báo cáo cho ứng dụng.
- `WHERE` lọc hàng nguồn trước tổng hợp; `HAVING` lọc các nhóm và có thể loại cả subtotal/grand total nếu không xét GROUPING.
- MySQL 8.0 hỗ trợ `GROUPING()`; với phiên bản cũ không có hàm này, có thể tự dựng các cấp bằng `UNION ALL` và cờ rõ ràng.
- `UNION ALL` giữ các dòng tổng hợp có giá trị cột trùng nhau; `UNION` có thể loại chúng.
- Dùng `EXPLAIN` và dữ liệu đại diện để đánh giá hiệu năng thay vì suy đoán từ việc có index.

Khi kết hợp `WITH ROLLUP` và `GROUPING()`, bạn có thể tạo báo cáo nhiều cấp mà vẫn giữ đúng ý nghĩa của NULL trong dữ liệu nguồn. Đây là nền tảng để hiển thị subtotal và grand total chính xác, lọc báo cáo an toàn và cung cấp kết quả có cấu trúc rõ ràng cho ứng dụng.
