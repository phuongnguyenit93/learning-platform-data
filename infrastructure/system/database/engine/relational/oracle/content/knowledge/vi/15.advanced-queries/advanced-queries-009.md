# MODEL clause và bài toán tính toán trên tập ô

Trong một báo cáo doanh thu, dữ liệu có thể được nhóm theo sản phẩm và năm. Từ doanh thu lịch sử, ta muốn tạo thêm các ô dự báo cho năm tiếp theo, tính chênh lệch so với kế hoạch, phân bổ chỉ tiêu theo tháng hoặc lan truyền giá trị qua nhiều kỳ. Nếu viết mỗi phép tính thành một truy vấn riêng rồi JOIN kết quả, câu SQL có thể trở nên dài và khó theo dõi.

Oracle Database có **MODEL clause** để xử lý dữ liệu như một mô hình nhiều chiều gồm các **ô (cells)**. Mỗi ô được xác định bởi các giá trị chiều (*dimensions*) và chứa một hay nhiều giá trị đo (*measures*). Ta có thể tham chiếu một ô, tính giá trị mới, cập nhật ô có sẵn hoặc tạo ô chưa tồn tại bằng các quy tắc (*rules*).

Bài học này tập trung vào cách hình dung tập ô, khai báo `PARTITION BY`, `DIMENSION BY`, `MEASURES`, tham chiếu ô, `CV()`, quy tắc `UPDATE`/`UPSERT`, thứ tự thực thi, lặp tính toán và xử lý giá trị thiếu. Ví dụ chính dùng bài toán dự báo doanh thu theo sản phẩm và năm.

## 1. MODEL clause giải quyết bài toán gì?

Giả sử bảng doanh thu có các cột:

| PRODUCT_ID | FISCAL_YEAR | SALES_AMOUNT |
|---:|---:|---:|
| 10 | 2023 | 100 |
| 10 | 2024 | 120 |
| 20 | 2023 | 80 |
| 20 | 2024 | 88 |

Yêu cầu báo cáo:

- Giữ doanh thu lịch sử.
- Tạo ô dự báo năm 2025 bằng doanh thu 2024 tăng 10%.
- Tạo tiếp ô năm 2026 dựa trên giá trị năm 2025.
- Thực hiện độc lập cho từng sản phẩm.

Nếu chỉ dùng phép chiếu thông thường, ta có thể tính một cột dự báo cho các hàng hiện có, nhưng khó biểu diễn tự nhiên những **năm chưa có hàng trong bảng nguồn**. MODEL cho phép mô tả rõ các ô theo chiều và quy tắc gán giá trị:

~~~text
PRODUCT_ID = 10

FISCAL_YEAR     2023    2024    2025    2026
SALES_AMOUNT     100     120     132     145.2
                              ^       ^
                         ô mới    ô mới

PRODUCT_ID = 20

FISCAL_YEAR     2023    2024    2025    2026
SALES_AMOUNT      80      88     96.8   106.48
~~~

Mô hình không bắt buộc phải hiển thị theo ma trận ngang. Kết quả SQL vẫn có thể là các hàng `PRODUCT_ID`, `FISCAL_YEAR`, `SALES_AMOUNT`; cách hình dung ma trận giúp hiểu việc tham chiếu và tính toán trên từng ô.

### 1.1 Bốn khái niệm cần nắm

| Khái niệm | Ý nghĩa trong MODEL | Ví dụ |
|---|---|---|
| Partition | Nhóm mô hình độc lập; các quy tắc chạy riêng trong từng nhóm | Mỗi `PRODUCT_ID` |
| Dimension | Chiều dùng để định vị một ô | `FISCAL_YEAR` |
| Measure | Giá trị được lưu/tính trong ô | `SALES_AMOUNT` |
| Cell | Một vị trí xác định bởi tổ hợp dimension trong một partition | Sản phẩm 10, năm 2024 |

Một cách nhớ:

- **Partition** trả lời: mô hình nào đang được tính độc lập?
- **Dimension** trả lời: ô nào?
- **Measure** trả lời: giá trị nào nằm trong ô?
- **Rule** trả lời: giá trị của ô được tính ra sao?

## 2. Chuẩn bị bảng doanh thu thực hành

Trong schema thực hành được phép tạo bảng, chạy:

~~~sql
CREATE TABLE lab_sales_plan (
    product_id   NUMBER(6) NOT NULL,
    fiscal_year  NUMBER(4) NOT NULL,
    sales_amount NUMBER(14,2),
    CONSTRAINT pk_lab_sales_plan
        PRIMARY KEY (product_id, fiscal_year)
);
~~~

Nạp dữ liệu:

~~~sql
INSERT ALL
    INTO lab_sales_plan VALUES (10, 2023, 100)
    INTO lab_sales_plan VALUES (10, 2024, 120)
    INTO lab_sales_plan VALUES (20, 2023, 80)
    INTO lab_sales_plan VALUES (20, 2024, 88)
SELECT 1 FROM dual;

COMMIT;
~~~

Kiểm tra:

~~~sql
SELECT product_id, fiscal_year, sales_amount
FROM lab_sales_plan
ORDER BY product_id, fiscal_year;
~~~

Khóa chính `(PRODUCT_ID, FISCAL_YEAR)` đảm bảo mỗi sản phẩm có tối đa một hàng cho một năm trong bảng nguồn. Đây cũng là điều kiện dữ liệu quan trọng để mô hình có một ô duy nhất cho mỗi tổ hợp chiều trong từng partition.

## 3. Cấu trúc tổng quát của MODEL clause

Mẫu khái quát:

~~~sql
SELECT select_list
FROM source_table
MODEL
    [PARTITION BY (partition_expression, ...)]
    DIMENSION BY (dimension_expression, ...)
    MEASURES (measure_expression, ...)
    [IGNORE NAV | KEEP NAV]
    [RULES
        [UPDATE | UPSERT [ALL]]
        [AUTOMATIC ORDER | SEQUENTIAL ORDER]
        [ITERATE (number) [UNTIL (condition)]]
        (
            measure[cell_reference] = expression,
            ...
        )
    ]
ORDER BY ...;
~~~

Đây là khung minh họa các thành phần phổ biến; khi viết SQL thực tế cần tuân theo thứ tự cú pháp của release Oracle đang sử dụng.

Các phần:

1. `PARTITION BY` chia nguồn thành các mô hình độc lập.
2. `DIMENSION BY` khai báo các cột định vị ô.
3. `MEASURES` khai báo các giá trị có thể được đọc và tính.
4. `RULES` mô tả cách gán giá trị cho ô.
5. `UPDATE`/`UPSERT` quyết định có tạo ô khi ô đích chưa tồn tại hay không.
6. `SEQUENTIAL ORDER`/`AUTOMATIC ORDER` điều khiển thứ tự áp dụng rule.
7. `ITERATE` cho phép áp dụng rule nhiều lần.

MODEL là phần mở rộng SQL của Oracle. Không thể sao chép nguyên cú pháp này sang mọi hệ quản trị khác.

## 4. PARTITION BY: chia mô hình thành các nhóm độc lập

Ví dụ dự báo doanh thu độc lập cho từng sản phẩm:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

`PARTITION BY (product_id)` tạo một mô hình riêng cho từng sản phẩm. Khi rule tính `sales_amount[2025]`, tham chiếu năm 2024 được tìm **trong cùng partition sản phẩm**. Do đó:

- Partition sản phẩm 10 dùng 120 để tính 2025.
- Partition sản phẩm 20 dùng 88 để tính 2025.

Không có chuyện sản phẩm 10 lấy doanh thu năm 2024 của sản phẩm 20.

### 4.1 Không có PARTITION BY

Nếu không cần chia thành các mô hình độc lập, có thể bỏ `PARTITION BY`:

~~~sql
SELECT fiscal_year,
       sales_amount
FROM some_single_product_source
MODEL
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

Khi đó tất cả hàng nguồn thuộc một mô hình. Nếu dimension không đủ để phân biệt dữ liệu của các sản phẩm, cùng một năm có thể không còn xác định được một ô duy nhất. Vì vậy, nếu dữ liệu có nhiều sản phẩm, thường phải:

- Đưa `PRODUCT_ID` vào `PARTITION BY`, hoặc
- Đưa `PRODUCT_ID` vào `DIMENSION BY` nếu cần tham chiếu sản phẩm như một chiều trong cùng mô hình.

Không bỏ một chiều định danh chỉ để câu SQL ngắn hơn.

### 4.2 Partition khác dimension

Hai cách có thể tạo mô hình có tổ chức khác nhau:

~~~sql
PARTITION BY (product_id)
DIMENSION BY (fiscal_year)
~~~

Mỗi sản phẩm là một mô hình riêng, dimension chỉ là năm.

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

Tất cả sản phẩm nằm trong một mô hình; mỗi ô được định vị bằng cả mã sản phẩm và năm. Khi tham chiếu ô phải cung cấp điều kiện cho các chiều phù hợp.

Chọn partition khi các phép tính của từng nhóm độc lập và muốn biểu đạt ranh giới đó rõ ràng. Chọn nhiều dimension khi cần tham chiếu chéo giữa các sản phẩm hoặc giữa các nhóm trong cùng mô hình.

## 5. DIMENSION BY: xác định tọa độ của ô

Với dữ liệu thực hành:

~~~sql
DIMENSION BY (fiscal_year)
~~~

`FISCAL_YEAR` là dimension. Mỗi giá trị năm xác định một vị trí trong partition:

| Dimension value | Measure tại ô |
|---:|---:|
| 2023 | 100 |
| 2024 | 120 |
| 2025 | Chưa có trong dữ liệu nguồn |
| 2026 | Chưa có trong dữ liệu nguồn |

Dimension không nhất thiết phải là số. Nó có thể là ngày, chuỗi hoặc biểu thức có kiểu dữ liệu phù hợp. Ví dụ:

~~~sql
DIMENSION BY (month_start)
~~~

hoặc:

~~~sql
DIMENSION BY (region_code, fiscal_year)
~~~

### 5.1 Mỗi tổ hợp dimension trong partition phải xác định được một ô

Trong mô hình một chiều, một partition không nên có hai hàng nguồn cùng `FISCAL_YEAR` nếu chúng đại diện cho hai giá trị khác nhau của cùng measure. Trong mô hình nhiều chiều, tổ hợp các dimension phải xác định duy nhất ô theo yêu cầu của mô hình.

Nếu nguồn có nhiều dòng cho cùng một sản phẩm/năm, hãy xác định grain trước:

~~~sql
SELECT product_id,
       fiscal_year,
       SUM(sales_amount) AS sales_amount
FROM raw_sales
GROUP BY product_id, fiscal_year;
~~~

Sau đó đưa kết quả đã tổng hợp vào MODEL. Nếu không xử lý trùng dimension, Oracle có thể báo lỗi về dimension không duy nhất, chẳng hạn `ORA-32638: Non unique addressing in MODEL dimensions`.

Không dùng `DISTINCT` một cách máy móc để che dữ liệu trùng; hai hàng cùng dimension có thể có giá trị measure khác nhau và cần được tổng hợp theo nghiệp vụ.

### 5.2 Dimension có kiểu ngày

Ví dụ mô hình theo tháng:

~~~sql
SELECT product_id,
       month_start,
       sales_amount
FROM monthly_sales
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (month_start)
    MEASURES (sales_amount)
    RULES (
        sales_amount[DATE '2026-01-01'] =
            sales_amount[DATE '2025-12-01'] * 1.05
    )
ORDER BY product_id, month_start;
~~~

Ở đây các giá trị dimension là ngày đầu tháng. Dùng date literal để tham chiếu ổn định; không viết chuỗi ngày phụ thuộc `NLS_DATE_FORMAT`.

## 6. MEASURES: giá trị được lưu trong mỗi ô

`MEASURES` khai báo các biểu thức/giá trị được dùng làm nội dung của ô. Ví dụ:

~~~sql
MEASURES (sales_amount)
~~~

Có thể có nhiều measure:

~~~sql
MEASURES (
    sales_amount,
    budget_amount,
    sales_amount - budget_amount AS variance
)
~~~

Trong ví dụ này:

- `SALES_AMOUNT` là doanh thu.
- `BUDGET_AMOUNT` là kế hoạch.
- `VARIANCE` là measure tính từ hai biểu thức đầu vào.

Measure có thể được dùng trong rule:

~~~sql
RULES (
    variance[2024] = sales_amount[2024] - budget_amount[2024]
)
~~~

Một measure là giá trị tại từng cell, không phải dimension định vị cell. Nếu cần xác định một ô theo năm và khu vực, các chiều phải nằm trong `DIMENSION BY`; đưa `SALES_AMOUNT` vào `MEASURES` không khiến nó trở thành tọa độ.

## 7. Tham chiếu ô: measure[dimension value]

Trong MODEL, tham chiếu ô thường có dạng:

~~~sql
measure[dimension_value]
~~~

Với nhiều dimension, cung cấp giá trị theo thứ tự các chiều đã khai báo:

~~~sql
measure[dimension_value_1, dimension_value_2]
~~~

Ví dụ:

~~~sql
sales_amount[2024]
~~~

nghĩa là measure `SALES_AMOUNT` tại ô có dimension `FISCAL_YEAR = 2024` trong partition hiện tại.

Trong mô hình nhiều chiều:

~~~sql
sales_amount[10, 2024]
~~~

có thể tham chiếu ô sản phẩm 10, năm 2024 nếu thứ tự `DIMENSION BY` là `(product_id, fiscal_year)`.

### 7.1 Tham chiếu ô hiện có và ô chưa tồn tại

Với dữ liệu nguồn:

| FISCAL_YEAR | SALES_AMOUNT |
|---:|---:|
| 2023 | 100 |
| 2024 | 120 |

`sales_amount[2024]` tham chiếu ô hiện có. `sales_amount[2025]` là tham chiếu đến tọa độ chưa có trong dữ liệu đầu vào. Rule có thể tạo ô mới nếu dùng chế độ UPSERT phù hợp.

Nếu một ô không tồn tại, không được tự giả định giá trị measure bằng 0. Giá trị thiếu, ô không hiện diện và ô hiện diện nhưng measure NULL là những trạng thái cần phân biệt.

## 8. CV(): giá trị dimension của ô hiện tại

`CV()` là viết tắt của *current value*. Trong rule, nó trả về giá trị hiện tại của dimension đang xét. Có thể chỉ rõ dimension:

~~~sql
CV(fiscal_year)
~~~

Ví dụ:

~~~sql
sales_amount[CV(fiscal_year) - 1]
~~~

Nếu rule đang tính ô năm 2025, `CV(fiscal_year)` là 2025; biểu thức tham chiếu ô năm 2024.

### 8.1 Dùng CV để viết rule tổng quát

Thay vì viết riêng từng năm:

~~~sql
sales_amount[2025] = sales_amount[2024] * 1.10,
sales_amount[2026] = sales_amount[2025] * 1.10,
sales_amount[2027] = sales_amount[2026] * 1.10
~~~

có thể dùng quy tắc áp dụng cho một dải năm:

~~~sql
sales_amount[FOR fiscal_year FROM 2025 TO 2027 INCREMENT 1] =
    sales_amount[CV(fiscal_year) - 1] * 1.10
~~~

Phần `FOR` trong cell reference tạo các giá trị dimension đích theo dải; `CV(fiscal_year)` cho biết năm đang được gán ở mỗi lần áp dụng rule. Cú pháp `FOR` và cách kết hợp với rule cần được đối chiếu theo SQL Language Reference của release mục tiêu trước khi dùng trong production.

### 8.2 CV trong mô hình nhiều chiều

Giả sử:

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

ta có thể tham chiếu:

~~~sql
sales_amount[CV(product_id), CV(fiscal_year) - 1]
~~~

Điều này giữ nguyên `PRODUCT_ID` của ô đang tính và lùi một năm ở dimension `FISCAL_YEAR`. Nếu viết sai thứ tự chiều, tham chiếu có thể trỏ sang tọa độ khác hoặc gây lỗi.

## 9. Rule cơ bản: tính một ô từ ô khác

Ví dụ dự báo năm 2025:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

Rule `sales_amount[2025] = sales_amount[2024] * 1.10` được đọc như sau:

1. Measure đích là `SALES_AMOUNT`.
2. Cell đích có `FISCAL_YEAR = 2025`.
3. Giá trị gán là measure tại ô 2024 nhân 1,10.
4. Rule được áp dụng riêng trong mỗi partition sản phẩm.

### 9.1 UPDATE và UPSERT

Hai chế độ quan trọng:

| Chế độ | Khi cell đích đã tồn tại | Khi cell đích chưa tồn tại |
|---|---|---|
| `UPDATE` | Cập nhật giá trị measure | Không tạo cell mới |
| `UPSERT` | Cập nhật cell hiện có | Có thể tạo cell cho tham chiếu đích một ô theo quy tắc UPSERT |

Trong MODEL, `UPDATE` là hành vi mặc định nếu không chỉ định chế độ khác. Khi muốn thêm năm 2025 chưa có trong nguồn, hãy dùng `UPSERT`:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

Kết quả có thêm hàng cho năm 2025 ở mỗi sản phẩm, dù bảng `LAB_SALES_PLAN` ban đầu không có các hàng đó. Đây là **kết quả của câu SELECT**, không phải thao tác INSERT trực tiếp vào bảng nguồn.

### 9.2 UPSERT không ghi dữ liệu trở lại bảng nguồn

MODEL tính toán trên tập dữ liệu của câu truy vấn và trả các cell trong kết quả. Rule `UPSERT` tạo cell trong mô hình kết quả. Nó không tự thực hiện `INSERT` vào `LAB_SALES_PLAN`.

Nếu muốn lưu kết quả dự báo vào bảng vật lý, phải dùng một câu DML riêng, chẳng hạn `INSERT INTO ... SELECT ...` hoặc `MERGE`, và thiết kế transaction/khóa duy nhất phù hợp.

## 10. Nhiều rule và thứ tự áp dụng

Ta muốn dự báo liên tiếp năm 2025 và 2026:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT SEQUENTIAL ORDER (
        sales_amount[2025] = sales_amount[2024] * 1.10,
        sales_amount[2026] = sales_amount[2025] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

Rule thứ hai đọc giá trị năm 2025 được tạo bởi rule trước. `SEQUENTIAL ORDER` yêu cầu các rule được áp dụng theo thứ tự xuất hiện trong danh sách. Điều này phù hợp khi một rule phụ thuộc vào kết quả của rule trước.

### 10.1 SEQUENTIAL ORDER

`SEQUENTIAL ORDER` áp dụng các rule theo thứ tự đã viết. Ví dụ:

~~~sql
RULES UPSERT SEQUENTIAL ORDER (
    sales_amount[2025] = sales_amount[2024] * 1.10,
    sales_amount[2026] = sales_amount[2025] * 1.10
)
~~~

Rule 2025 chạy trước, sau đó rule 2026 có thể dùng giá trị mới của 2025.

### 10.2 AUTOMATIC ORDER

`AUTOMATIC ORDER` cho phép Oracle sắp xếp việc thực thi rule theo quan hệ phụ thuộc giữa các rule. Nó hữu ích khi muốn biểu diễn các phụ thuộc dữ liệu mà không tự áp đặt thứ tự viết, nhưng không nên dùng nếu rule có tác động phụ thuộc thứ tự mà người viết chưa xác định rõ.

Ví dụ các rule độc lập:

~~~sql
RULES UPSERT AUTOMATIC ORDER (
    sales_amount[2025] = sales_amount[2024] * 1.10,
    sales_amount[2026] = sales_amount[2024] * 1.20
)
~~~

Cả hai đều đọc năm 2024, không phụ thuộc lẫn nhau. Khi các rule có phụ thuộc, cần chọn thứ tự và kiểm tra kết quả bằng ví dụ nhỏ trước khi đưa vào báo cáo quan trọng.

### 10.3 UPDATE/UPSERT và thứ tự là hai quyết định riêng

- `UPDATE`/`UPSERT` xác định hành vi với cell đích có sẵn hay chưa.
- `SEQUENTIAL ORDER`/`AUTOMATIC ORDER` xác định cách áp dụng các rule.

Không nhầm `UPSERT` với `SEQUENTIAL ORDER`: một bên liên quan đến việc tạo cell, bên kia liên quan thứ tự tính toán.

## 11. FOR loop trong cell reference

Khi cần áp dụng cùng một công thức cho nhiều giá trị dimension, `FOR` có thể tạo một tập cell đích.

Ví dụ dự báo từ 2025 tới 2027:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT SEQUENTIAL ORDER (
        sales_amount[
            FOR fiscal_year FROM 2025 TO 2027 INCREMENT 1
        ] =
            sales_amount[CV(fiscal_year) - 1] * 1.10
    )
ORDER BY product_id, fiscal_year;
~~~

Mỗi giá trị năm trong dải là một cell đích. `CV(fiscal_year)` đại diện năm hiện tại đang được xử lý; rule đọc năm liền trước và nhân hệ số tăng trưởng.

Khi dùng `FOR`, cần lưu ý:

- Dimension phải có kiểu phù hợp với cách tạo dải.
- Khoảng bắt đầu/kết thúc và bước tăng phải đúng với miền dữ liệu.
- Rule cần đọc được cell nguồn trước đó; nếu năm liền trước không tồn tại hoặc measure là NULL, kết quả phụ thuộc cách xử lý giá trị thiếu.
- `UPSERT` được dùng khi cell đích có thể chưa tồn tại.

Với dimension ngày hoặc chuỗi, không áp dụng máy móc `FROM ... TO ... INCREMENT 1`; phải dùng cách tạo giá trị dimension đúng kiểu và cú pháp được Oracle hỗ trợ.

## 12. ITERATE: lặp lại các rule

`ITERATE(n)` cho phép áp dụng tập rule nhiều lần. Điều này hữu ích với một số bài toán cần cập nhật giá trị theo từng vòng lặp, chẳng hạn mô phỏng tăng trưởng lũy kế hoặc tính toán hội tụ.

Ví dụ minh họa một ô tăng 10% qua ba vòng:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPDATE SEQUENTIAL ORDER
        ITERATE (3) (
            sales_amount[2024] = sales_amount[2024] * 1.10
        )
ORDER BY product_id, fiscal_year;
~~~

Trong mô hình ví dụ, ô năm 2024 được cập nhật qua từng iteration. Sau ba vòng, giá trị cuối cùng bằng giá trị ban đầu nhân hệ số tăng trưởng ba lần. Ví dụ này chỉ nhằm minh họa cơ chế lặp; MODEL trong SELECT chỉ tạo kết quả truy vấn, không thay đổi bảng nguồn.

### 12.1 ITERATE và UNTIL

Có thể dừng sớm bằng điều kiện `UNTIL`:

~~~sql
RULES UPDATE SEQUENTIAL ORDER
    ITERATE (100) UNTIL (ABS(sales_amount[2024] - 200) < 0.01)
    (
        sales_amount[2024] =
            (sales_amount[2024] + 200) / 2
    )
~~~

Ví dụ dùng một phép cập nhật tiến dần về 200. Điều kiện `UNTIL` được kiểm tra giữa các vòng lặp; số vòng tối đa là 100, nhưng có thể dừng sớm khi sai khác nhỏ hơn ngưỡng.

Khi thiết kế điều kiện dừng:

- Phải có giới hạn vòng lặp hữu hạn để tránh tính toán quá lâu.
- Điều kiện hội tụ phải phản ánh ý nghĩa bài toán.
- Xem xét độ chính xác và ngưỡng sai số.
- Tránh rule không làm thay đổi giá trị nhưng vẫn lặp hết số vòng tối đa.

### 12.2 ITERATION_NUMBER

Trong rule lặp, pseudocolumn `ITERATION_NUMBER` cho biết số thứ tự iteration hiện tại. Nó có thể được dùng trong công thức hoặc điều kiện:

~~~sql
sales_amount[2024] =
    sales_amount[2024] + ITERATION_NUMBER
~~~

Đây chỉ là ví dụ minh họa việc truy cập số vòng lặp; một công thức thực tế cần xác định rõ giá trị khởi đầu và ý nghĩa mỗi vòng. Đừng nhầm `ITERATION_NUMBER` với `LEVEL`: một bên là vòng lặp của MODEL, bên kia là độ sâu trong hierarchical query.

## 13. Nhiều dimension: bài toán theo sản phẩm và khu vực

Mô hình có thể dùng nhiều chiều. Ví dụ bảng kế hoạch theo khu vực, sản phẩm và năm:

| REGION_ID | PRODUCT_ID | FISCAL_YEAR | SALES_AMOUNT |
|---|---:|---:|---:|
| NORTH | 10 | 2024 | 120 |
| SOUTH | 10 | 2024 | 90 |
| NORTH | 20 | 2024 | 88 |
| SOUTH | 20 | 2024 | 70 |

Một cách định nghĩa:

~~~sql
SELECT region_id,
       product_id,
       fiscal_year,
       sales_amount
FROM regional_sales
MODEL
    DIMENSION BY (region_id, product_id, fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount['NORTH', 10, 2025] =
            sales_amount['NORTH', 10, 2024] * 1.10
    )
ORDER BY region_id, product_id, fiscal_year;
~~~

Ô đích được xác định bởi ba tọa độ theo đúng thứ tự dimension: `REGION_ID`, `PRODUCT_ID`, `FISCAL_YEAR`.

Nếu muốn mỗi khu vực là partition độc lập:

~~~sql
PARTITION BY (region_id)
DIMENSION BY (product_id, fiscal_year)
MEASURES (sales_amount)
~~~

Khi đó trong mỗi partition, tham chiếu cell chỉ cần tọa độ `(product_id, fiscal_year)`. Cả hai cách đều có thể đúng; chọn theo cách muốn tổ chức phép tính.

## 14. Dùng CV để tính trên ô hiện tại trong nhiều dimension

Với:

~~~sql
DIMENSION BY (product_id, fiscal_year)
~~~

ta có thể viết:

~~~sql
sales_amount[CV(product_id), CV(fiscal_year) - 1]
~~~

Đây là giá trị cùng sản phẩm ở năm trước. Ví dụ tính phần trăm tăng trưởng:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       growth_rate
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (
        sales_amount,
        CAST(NULL AS NUMBER(10,4)) AS growth_rate
    )
    RULES UPDATE (
        growth_rate[2024] =
            (sales_amount[2024] - sales_amount[2023])
            / NULLIF(sales_amount[2023], 0)
    )
ORDER BY product_id, fiscal_year;
~~~

Measure `GROWTH_RATE` được khai báo để tính tỷ lệ tăng trưởng năm 2024 từ doanh thu năm 2023. `NULLIF` bảo vệ mẫu số bằng 0.

Nếu muốn tính cho nhiều năm trong dải:

~~~sql
growth_rate[FOR fiscal_year FROM 2024 TO 2026 INCREMENT 1] =
    (sales_amount[CV(fiscal_year)] -
     sales_amount[CV(fiscal_year) - 1])
    / NULLIF(sales_amount[CV(fiscal_year) - 1], 0)
~~~

Điều kiện là các cell năm trước có thể được tham chiếu. Nếu thiếu năm liền trước, phải xác định cách xử lý missing cell/NULL thay vì giả định nó bằng 0.

## 15. UPDATE, UPSERT và cell không tồn tại

Sự khác biệt này quyết định kết quả có xuất hiện thêm hàng hay không.

### 15.1 UPDATE chỉ thay đổi cell hiện có

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPDATE (
        sales_amount[2024] = sales_amount[2024] * 1.05
    )
ORDER BY product_id, fiscal_year;
~~~

Ô năm 2024 đã tồn tại nên được tính lại trong kết quả mô hình. Nếu rule nhắm tới năm 2025 chưa có, `UPDATE` không tự tạo hàng mới cho năm đó.

### 15.2 UPSERT tạo cell đích phù hợp

~~~sql
RULES UPSERT (
    sales_amount[2025] = sales_amount[2024] * 1.10
)
~~~

Nếu cell 2025 chưa tồn tại và rule tham chiếu một cell đích đơn, Oracle có thể tạo cell mới theo semantics UPSERT. Đây là cơ chế thường dùng cho forecast, budget hoặc các kỳ tương lai chưa có dữ liệu nguồn.

### 15.3 UPSERT ALL cho tham chiếu nhiều cell

`UPSERT ALL` là biến thể dành cho rule có tham chiếu đích nhiều cell theo cú pháp MODEL. Không dùng nó như từ khóa thay thế chung cho `UPSERT`; hãy xác định rule đang nhắm tới một cell cụ thể hay một tập cell.

Với bài toán cơ bản, ưu tiên cell reference một tọa độ rõ ràng hoặc dải `FOR` đã xác định; chỉ dùng wildcard/multi-cell reference khi đã nắm rõ cách Oracle xác định tập ô đích.

## 16. Giá trị NULL, ô thiếu và NAV

Trong MODEL, cần phân biệt:

1. **Cell không tồn tại:** tổ hợp dimension không có trong dữ liệu đầu vào và chưa được tạo bởi rule.
2. **Cell tồn tại, measure NULL:** có hàng cho tọa độ đó nhưng measure đang NULL.
3. **Cell tồn tại, measure có giá trị:** có hàng và measure mang giá trị cụ thể.

Ví dụ:

| FISCAL_YEAR | SALES_AMOUNT | Trạng thái |
|---:|---:|---|
| 2023 | 100 | Cell tồn tại, measure có giá trị |
| 2024 | NULL | Cell tồn tại, measure NULL |
| 2025 | — | Cell chưa tồn tại |

Không tự đồng nhất hai hàng cuối thành 0. Một năm chưa được nhập dữ liệu có thể khác với năm đã được ghi nhận nhưng chưa xác định doanh thu.

### 16.1 KEEP NAV và IGNORE NAV

`NAV` là khái niệm *null/absent value* trong ngữ cảnh MODEL. Hai lựa chọn:

- `KEEP NAV` giữ NULL và giá trị absent như NULL trong quá trình tính toán.
- `IGNORE NAV` dùng giá trị NAV mặc định mà Oracle quy định theo kiểu dữ liệu của measure; không được mặc định rằng mọi kiểu đều được thay bằng số 0.

Nếu không chỉ định, MODEL dùng chế độ `IGNORE NAV`. Khi kết quả NULL có ý nghĩa nghiệp vụ, hãy cân nhắc chỉ định `KEEP NAV` rõ ràng.

Quy tắc NAV phụ thuộc kiểu measure; không nên giả định mọi kiểu dữ liệu đều được thay bằng số 0. Với measure số, hành vi NAV có thể ảnh hưởng phép cộng/nhân và kết quả rule. Khi kết quả NULL có ý nghĩa nghiệp vụ, hãy chỉ định rõ cách xử lý và kiểm tra bằng dữ liệu thử.

Ví dụ chọn giữ NAV:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    KEEP NAV
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

`KEEP NAV` hữu ích khi muốn bảo toàn ý nghĩa thiếu dữ liệu và không muốn một cell chưa có/NULL bị diễn giải như giá trị thay thế. Với phép tính thực tế, có thể cần `CASE`, `NVL`, `COALESCE` hoặc `NULLIF` trong biểu thức rule để thể hiện chính sách nghiệp vụ.

### 16.2 Kiểm tra NULL trước khi tính

~~~sql
sales_amount[2025] =
    CASE
        WHEN sales_amount[2024] IS NULL THEN NULL
        ELSE sales_amount[2024] * 1.10
    END
~~~

Ví dụ này làm rõ rằng nếu doanh thu năm 2024 không có giá trị, forecast 2025 cũng không được tính thành số. Nếu nghiệp vụ muốn mặc định thiếu doanh thu là 0:

~~~sql
sales_amount[2025] = NVL(sales_amount[2024], 0) * 1.10
~~~

thì phải chấp nhận rõ quyết định đó. Thay NULL bằng 0 có thể làm dự báo sai nếu NULL thực chất là dữ liệu chưa được nạp.

## 17. Nhiều measure và quy tắc phụ thuộc nhau

Một mô hình có thể tính doanh thu dự báo, ngân sách và chênh lệch:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       budget_amount,
       variance_amount
FROM product_finance
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (
        sales_amount,
        budget_amount,
        CAST(NULL AS NUMBER(14,2)) AS variance_amount
    )
    RULES UPDATE (
        variance_amount[2024] =
            sales_amount[2024] - budget_amount[2024]
    )
ORDER BY product_id, fiscal_year;
~~~

`VARIANCE_AMOUNT` là measure được tính từ hai measure đầu vào. Có thể định nghĩa thêm tỷ lệ:

~~~sql
variance_percent[2024] =
    variance_amount[2024] / NULLIF(budget_amount[2024], 0)
~~~

Khi nhiều rule phụ thuộc nhau, dùng `SEQUENTIAL ORDER` hoặc `AUTOMATIC ORDER` theo ý định tính toán và kiểm tra kết quả. Không giả định một rule sẽ tự chạy trước chỉ vì nó xuất hiện trong một biểu thức khác; hãy khai báo thứ tự hoặc cấu trúc phụ thuộc rõ ràng.

## 18. MODEL so với GROUP BY, analytic và PIVOT

Các kỹ thuật này giải quyết những dạng bài toán khác nhau:

| Kỹ thuật | Mục tiêu chính | Đặc điểm |
|---|---|---|
| `GROUP BY` | Tổng hợp nhiều hàng thành một hàng mỗi nhóm | Phù hợp SUM/COUNT/AVG theo nhóm |
| Analytic function | Tính trên cửa sổ hàng nhưng vẫn giữ hàng chi tiết | Phù hợp running total, rank, moving average |
| `PIVOT` | Chuyển giá trị phân loại thành cột | Phù hợp báo cáo dạng bảng chéo |
| `MODEL` | Tham chiếu và tính toán trên các cell theo dimension | Phù hợp forecast, phân bổ, mô hình nhiều chiều, quy tắc phụ thuộc cell |

### 18.1 Khi GROUP BY là đủ

Nếu chỉ cần tổng doanh thu theo sản phẩm:

~~~sql
SELECT product_id,
       SUM(sales_amount) AS total_sales
FROM sales_history
GROUP BY product_id;
~~~

Không cần MODEL vì không có phép tham chiếu cell hoặc tạo giá trị theo tọa độ.

### 18.2 Khi analytic là đủ

Nếu cần tổng lũy kế theo năm:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount,
       SUM(sales_amount) OVER (
           PARTITION BY product_id
           ORDER BY fiscal_year
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_sales
FROM lab_sales_plan;
~~~

Analytic function tự nhiên hơn khi phép tính là cửa sổ trên các hàng hiện có. MODEL hữu ích hơn khi cần tham chiếu tọa độ cụ thể, tạo cell mới hoặc áp dụng rule nhiều bước.

### 18.3 Khi MODEL là lựa chọn phù hợp

MODEL có thể phù hợp khi:

- Dữ liệu có các chiều rõ ràng như sản phẩm, khu vực, tháng, năm.
- Cần tính giá trị ở ô chưa có trong nguồn.
- Công thức phụ thuộc ô hiện tại, ô trước hoặc ô khác chiều.
- Có nhiều rule liên quan và cần thứ tự/iteration rõ ràng.
- Muốn giữ logic mô hình trong một câu SQL.

MODEL không tự động nhanh hơn CTE hay analytic. Cú pháp phức tạp và chi phí tính toán có thể lớn; chỉ dùng khi cấu trúc bài toán thực sự cần mô hình cell.

## 19. ORDER BY sau MODEL và thứ tự trong mô hình

`ORDER BY` ở cuối câu truy vấn sắp xếp **các hàng kết quả trả về**:

~~~sql
ORDER BY product_id, fiscal_year
~~~

Nó không quyết định thứ tự áp dụng rule. Muốn điều khiển thứ tự rule, dùng `SEQUENTIAL ORDER` hoặc `AUTOMATIC ORDER` trong phần RULES.

Phân biệt:

- `SEQUENTIAL ORDER`: thứ tự tính các rule.
- `ORDER BY`: thứ tự hàng hiển thị sau khi MODEL tạo kết quả.

Không dựa vào thứ tự vật lý của hàng nguồn để suy luận thứ tự cell hoặc thứ tự rule.

## 20. MODEL và các điều kiện lọc dữ liệu nguồn

MODEL hoạt động trên tập hàng do phần truy vấn nguồn tạo ra. Nếu cần lọc kỳ lịch sử trước khi xây mô hình:

~~~sql
SELECT product_id,
       fiscal_year,
       sales_amount
FROM lab_sales_plan
WHERE fiscal_year >= 2023
MODEL
    PARTITION BY (product_id)
    DIMENSION BY (fiscal_year)
    MEASURES (sales_amount)
    RULES UPSERT (
        sales_amount[2025] = sales_amount[2024] * 1.10
    );
~~~

Điều kiện nguồn quyết định những hàng nào đi vào mô hình. Nếu loại năm 2024 khỏi nguồn, rule tham chiếu `sales_amount[2024]` có thể không có dữ liệu để tính. Hãy bảo đảm các cell đầu vào cần thiết vẫn được đưa vào mô hình.

Nếu cần chỉ hiển thị một số hàng sau khi tính, có thể bọc MODEL trong inline view/CTE rồi lọc kết quả bên ngoài:

~~~sql
WITH modeled AS (
    SELECT product_id,
           fiscal_year,
           sales_amount
    FROM lab_sales_plan
    MODEL
        PARTITION BY (product_id)
        DIMENSION BY (fiscal_year)
        MEASURES (sales_amount)
        RULES UPSERT (
            sales_amount[2025] = sales_amount[2024] * 1.10
        )
)
SELECT product_id, fiscal_year, sales_amount
FROM modeled
WHERE fiscal_year >= 2024
ORDER BY product_id, fiscal_year;
~~~

Tách nguồn và kết quả giúp phân biệt rõ **lọc dữ liệu đầu vào** với **lọc các cell sau tính toán**.

## 21. Ghi kết quả MODEL vào bảng vật lý

MODEL trong SELECT không tự ghi lại bảng nguồn. Nếu muốn lưu dự báo, có thể đưa kết quả truy vấn vào `INSERT`:

~~~sql
INSERT INTO sales_forecast (
    product_id,
    fiscal_year,
    forecast_amount
)
SELECT product_id,
       fiscal_year,
       sales_amount
FROM (
    SELECT product_id,
           fiscal_year,
           sales_amount
    FROM lab_sales_plan
    MODEL
        PARTITION BY (product_id)
        DIMENSION BY (fiscal_year)
        MEASURES (sales_amount)
        RULES UPSERT (
            sales_amount[2025] = sales_amount[2024] * 1.10
        )
) modeled
WHERE fiscal_year = 2025;
~~~

Đây là minh họa ý tưởng; bảng đích phải có cấu trúc và ràng buộc tương ứng, và điều kiện lọc kết quả phải đặt ở query block phù hợp. Trước khi chạy DML thật, hãy kiểm tra SELECT riêng, bảo đảm mỗi sản phẩm chỉ có một hàng forecast cho năm cần lưu, và xử lý khóa trùng bằng quy trình `MERGE`/upsert nghiệp vụ thích hợp.

## 22. Những lỗi thường gặp và hướng điều tra

| Triệu chứng/lỗi | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `ORA-32638: Non unique addressing in MODEL dimensions` | Có nhiều hàng nguồn cùng tổ hợp dimension trong một partition | Kiểm tra grain; tổng hợp hoặc sửa khóa trước MODEL |
| Rule không tạo hàng năm mới | Đang dùng UPDATE thay vì UPSERT, hoặc tham chiếu đích không phải cell phù hợp | Xác định cell đích và chọn UPSERT |
| Giá trị năm sau không dựa trên năm vừa tính | Rule order/dependency chưa được khai báo phù hợp | Dùng SEQUENTIAL ORDER hoặc AUTOMATIC ORDER theo quan hệ phụ thuộc |
| Kết quả forecast là NULL | Cell nguồn thiếu hoặc measure nguồn NULL/NAV | Kiểm tra sự hiện diện cell và chính sách NAV |
| Tất cả sản phẩm nhận cùng một giá trị | Thiếu partition/dimension phân biệt sản phẩm | Đưa product vào PARTITION BY hoặc DIMENSION BY |
| Tham chiếu sai cell | Sai thứ tự dimension hoặc sai giá trị tọa độ | Đối chiếu thứ tự DIMENSION BY và cell reference |
| Rule tính sai năm hiện tại | Dùng hằng số thay vì CV hoặc tính offset sai | Dùng CV(dimension) để tham chiếu tọa độ hiện tại |
| Kết quả có hàng trùng | Dimension không duy nhất hoặc nguồn JOIN bị nhân bản | Kiểm tra dữ liệu trước MODEL và grain |
| Lặp tính toán không dừng sớm | UNTIL không đạt hoặc thiếu điều kiện hội tụ | Đặt số vòng tối đa và kiểm tra điều kiện dừng |
| Kết quả MODEL bị hiểu là dữ liệu đã lưu | UPSERT trong MODEL chỉ tạo cell trong kết quả SELECT | Dùng INSERT/MERGE riêng nếu cần lưu |
| SQL không chạy trên hệ quản trị khác | MODEL là phần mở rộng Oracle | Dùng cách tương đương như CTE/analytic theo hệ quản trị |

Khi có lỗi, nên kiểm tra theo thứ tự:

1. Xác định dữ liệu nguồn và grain.
2. Kiểm tra tổ hợp partition + dimension có duy nhất không.
3. Đối chiếu cell reference với thứ tự dimension.
4. Kiểm tra cell nguồn có tồn tại và measure có NULL không.
5. Xem chế độ UPDATE/UPSERT.
6. Xem thứ tự rule và điều kiện iteration.

## 23. Bài thực hành tự kiểm tra

Sử dụng bảng `LAB_SALES_PLAN` đã tạo ở phần 2. Các câu lệnh SELECT MODEL không sửa bảng nguồn.

### Bài 1 — Tạo forecast một năm

Theo từng sản phẩm, tạo cell năm 2025 bằng doanh thu năm 2024 tăng 10%.

- Khai báo `PARTITION BY (product_id)`.
- Khai báo `DIMENSION BY (fiscal_year)`.
- Khai báo `MEASURES (sales_amount)`.
- Dùng UPSERT để tạo cell chưa có.

Giải thích tại sao nếu bỏ partition, dữ liệu nhiều sản phẩm có thể không còn được phân biệt đúng.

### Bài 2 — Tạo forecast nhiều năm

Tạo các cell 2025, 2026 và 2027, mỗi năm tăng 10% so với năm trước. Viết một phiên bản bằng các rule tường minh, một phiên bản dùng `CV()` và `FOR`.

### Bài 3 — UPDATE so với UPSERT

Chạy cùng rule nhắm tới năm 2025 bằng UPDATE và UPSERT. So sánh khi cell 2025 chưa có. Giải thích tại sao UPDATE không tạo hàng mới.

### Bài 4 — Nhiều dimension

Tạo nguồn có `REGION_ID`, `PRODUCT_ID`, `FISCAL_YEAR`, `SALES_AMOUNT`. Viết mô hình dùng:

~~~sql
DIMENSION BY (region_id, product_id, fiscal_year)
~~~

Tạo forecast cho một tọa độ cụ thể. Sau đó thử đưa REGION vào PARTITION BY và so sánh cách tham chiếu cell.

### Bài 5 — Tính variance

Tạo nguồn có `SALES_AMOUNT` và `BUDGET_AMOUNT`. Khai báo measure `VARIANCE_AMOUNT` và tính:

~~~sql
sales_amount - budget_amount
~~~

Giải thích vì sao variance là measure chứ không phải dimension.

### Bài 6 — Kiểm tra dimension trùng

Tạo hai hàng cùng `PRODUCT_ID`, `FISCAL_YEAR` nhưng amount khác nhau. Chạy MODEL và quan sát lỗi. Sau đó tổng hợp dữ liệu về một hàng cho mỗi tổ hợp dimension rồi chạy lại.

### Bài 7 — NULL và cell không tồn tại

Tạo một năm có hàng nhưng `SALES_AMOUNT` là NULL; để năm kế tiếp hoàn toàn không có hàng. So sánh hai trường hợp khi rule tham chiếu measure. Nêu chính sách phù hợp với nghiệp vụ.

### Bài 8 — ITERATE

Tạo một rule cập nhật cùng một cell qua ba iteration, mỗi vòng nhân 1.10. Tính bằng tay kết quả cuối cùng và đối chiếu với SQL.

### Bài 9 — UNTIL

Viết rule tiến dần tới một target bằng công thức trung bình giữa giá trị hiện tại và target. Đặt số vòng tối đa và điều kiện dừng dựa trên sai số. Giải thích nếu điều kiện không bao giờ đạt thì điều gì xảy ra.

### Bài 10 — So sánh với analytic

Viết truy vấn analytic tính running total theo sản phẩm/năm. So sánh với MODEL forecast. Nêu tình huống analytic đơn giản hơn và tình huống MODEL có lợi thế.

## 24. Ghi nhớ

| Thành phần | Vai trò |
|---|---|
| `PARTITION BY` | Tách các mô hình độc lập |
| `DIMENSION BY` | Khai báo tọa độ định vị cell |
| `MEASURES` | Khai báo giá trị trong cell |
| `RULES` | Khai báo công thức gán measure |
| `measure[dimension_value]` | Tham chiếu một cell |
| `CV(dimension)` | Lấy giá trị dimension của cell hiện tại |
| `UPDATE` | Chỉ cập nhật cell đã có |
| `UPSERT` | Cập nhật hoặc tạo cell đích phù hợp |
| `SEQUENTIAL ORDER` | Áp dụng rule theo thứ tự viết |
| `AUTOMATIC ORDER` | Sắp xếp rule theo quan hệ phụ thuộc |
| `FOR` | Tạo dải tọa độ cell đích |
| `ITERATE` | Lặp các rule một số vòng |
| `UNTIL` | Dừng lặp khi điều kiện đạt |
| `KEEP NAV` / `IGNORE NAV` | Chọn cách xử lý giá trị NULL/absent trong mô hình |

MODEL clause phù hợp với các bài toán mà dữ liệu được nhìn như một lưới nhiều chiều và giá trị của ô phụ thuộc vào ô khác. Hãy xác định grain, partition, dimension và measure trước; sau đó mới viết cell reference và rule. Dùng `CV()` để diễn đạt tọa độ hiện tại, chọn UPDATE hay UPSERT theo việc cell đích đã tồn tại hay chưa, và khai báo thứ tự/iteration khi có phụ thuộc. Cuối cùng, phân biệt cell thiếu với measure NULL và kiểm tra kết quả SELECT trước khi quyết định lưu dữ liệu vào bảng vật lý.
