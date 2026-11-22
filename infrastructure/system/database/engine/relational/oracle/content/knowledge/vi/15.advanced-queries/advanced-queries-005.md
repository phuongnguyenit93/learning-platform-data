# PIVOT, UNPIVOT và chuyển đổi dạng dữ liệu báo cáo trong Oracle Database

Trong hệ thống nghiệp vụ, dữ liệu thường được lưu theo dạng **mỗi dòng là một sự kiện hoặc một bản ghi**, còn báo cáo lại cần trình bày theo dạng **mỗi nhóm là một dòng và từng loại giá trị là một cột**. Ví dụ, bảng doanh thu có một dòng cho mỗi khu vực và quý, nhưng báo cáo cần các cột Q1, Q2, Q3, Q4 trên cùng một dòng khu vực. Đây là chuyển đổi từ dạng dài (long) sang dạng rộng (wide).

Oracle Database hỗ trợ hai phép biến đổi trong SQL:

- **PIVOT** gom nhóm và chuyển các giá trị của một cột thành các cột kết quả, thường kết hợp hàm tổng hợp như SUM, COUNT, AVG, MIN hoặc MAX.
- **UNPIVOT** chuyển nhiều cột có cùng vai trò thành các dòng, tạo ra một cột chứa tên/nhãn chiều và một hoặc nhiều cột chứa giá trị.

Hai phép biến đổi này hữu ích khi tạo báo cáo doanh thu theo quý, số lượng theo trạng thái, KPI theo tháng, bảng chấm công, dữ liệu khảo sát hoặc khi chuẩn hóa một bảng nguồn đang trải ngang nhiều cột. Bài học giải thích cú pháp Oracle, grouping ngầm của PIVOT, nhiều phép tổng hợp, PIVOT XML, UNPIVOT và NULL, cách thay thế bằng conditional aggregation, giới hạn khi chuyển đổi ngược và bài lab thực hành.

## 1. Dạng dữ liệu dài và dạng dữ liệu rộng

Giả sử dữ liệu doanh thu được lưu theo dạng dài:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |

Mỗi dòng biểu diễn một tổ hợp khu vực và quý. Dạng này phù hợp để lưu dữ liệu, thêm quý mới và tổng hợp theo nhiều chiều.

Nhưng báo cáo có thể muốn dạng rộng:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE |
|---|---:|---:|---:|
| North | 100 | 120 | 90 |
| South | 80 | 110 | 130 |

PIVOT chuyển giá trị trong cột QUARTER thành các cột Q1_REVENUE, Q2_REVENUE, Q3_REVENUE.

Chiều ngược lại, nếu nhận bảng wide từ file Excel hoặc hệ thống cũ:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE |
|---|---:|---:|---:|
| North | 100 | 120 | 90 |
| South | 80 | 110 | 130 |

UNPIVOT có thể đưa các cột quý trở lại dạng:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |

Mô hình long thường linh hoạt hơn cho lưu trữ và phân tích. Wide thường tiện cho một số định dạng báo cáo, biểu mẫu hoặc giao diện. Không nên chuyển dữ liệu sang wide chỉ vì bảng kết quả trông đẹp hơn nếu ứng dụng downstream cần một tập dữ liệu có cấu trúc động.

## 2. PIVOT: chuyển giá trị thành cột

### 2.1 Cú pháp cơ bản

~~~sql
SELECT ...
FROM source_table_or_subquery
PIVOT (
    aggregate_function(measure_column)
    FOR pivot_column
    IN (
        pivot_value_1 [AS column_alias_1],
        pivot_value_2 [AS column_alias_2],
        ...
    )
);
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| Nguồn dữ liệu | Bảng hoặc subquery cung cấp dimension, pivot key và measure |
| aggregate_function | Hàm tổng hợp như SUM, COUNT, AVG, MIN, MAX |
| measure_column | Giá trị cần tổng hợp |
| pivot_column | Cột có các giá trị sẽ biến thành cột đầu ra |
| IN (...) | Danh sách giá trị pivot được yêu cầu trong kết quả |
| column_alias | Tên dễ đọc cho cột sinh ra từ một giá trị pivot |

PIVOT không chỉ xoay cột. Nó **tổng hợp các dòng** theo những cột còn lại của nguồn dữ liệu. Đây là điểm cần hiểu trước khi dùng trong báo cáo.

### 2.2 Ví dụ PIVOT theo quý

Giả sử có bảng SALES với REGION, QUARTER và AMOUNT. Câu truy vấn:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Kết quả có các cột REGION, Q1, Q2, Q3, Q4. Mỗi khu vực trở thành một dòng; SUM(amount) tính tổng doanh thu cho từng quý.

Để tên cột có ý nghĩa hơn, đặt alias cho hàm tổng hợp:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Oracle tạo các cột có tên kết hợp alias giá trị pivot và alias aggregate, chẳng hạn Q1_REVENUE, Q2_REVENUE, Q3_REVENUE và Q4_REVENUE.

### 2.3 Tại sao cần inline view?

Trong ví dụ, subquery chỉ chọn ba cột:

- REGION: chiều cần giữ làm dòng.
- QUARTER: chiều sẽ xoay thành cột.
- AMOUNT: measure được tổng hợp.

Việc chỉ đưa các cột cần thiết vào nguồn PIVOT giúp kiểm soát rõ các chiều nhóm. Nếu đưa thêm SALE_ID, CUSTOMER_ID hoặc CREATED_AT vào nguồn mà không dùng chúng làm pivot key hay measure, những cột đó có thể trở thành khóa nhóm ngầm và làm kết quả có nhiều dòng hơn dự kiến.

Đây là một đặc điểm quan trọng của Oracle PIVOT: **các cột nguồn không được dùng trong pivot clause hoặc làm đối số measure sẽ tham gia grouping ngầm**. Hãy tạo inline view với đúng tập cột cần thiết trước khi pivot.

## 3. Grouping ngầm trong PIVOT

### 3.1 PIVOT tự nhóm theo các cột còn lại

Ví dụ:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

Oracle nhóm theo REGION vì:

- QUARTER là pivot column.
- AMOUNT là measure được SUM.
- REGION là cột còn lại.

Kết quả có một dòng cho mỗi REGION trong phạm vi dữ liệu được nhóm.

### 3.2 Thêm cột không mong muốn có thể làm thay đổi cấp nhóm

~~~sql
SELECT *
FROM (
    SELECT sale_id,
           region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

Vì SALE_ID không phải pivot column và không phải measure, nó trở thành một phần của grouping ngầm. Nếu mỗi sale_id là duy nhất, kết quả có thể thành một dòng cho mỗi giao dịch thay vì một dòng cho mỗi khu vực.

Muốn tổng hợp theo REGION, hãy bỏ SALE_ID khỏi inline view:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
);
~~~

### 3.3 PIVOT không có GROUP BY viết tường minh

Trong cú pháp PIVOT, các cột nhóm được xác định ngầm từ nguồn. Không thêm GROUP BY bên ngoài một cách máy móc. Nếu cần thay đổi mức tổng hợp, hãy kiểm soát SELECT list của inline view hoặc dùng một subquery/grouping trước PIVOT.

## 4. PIVOT với nhiều hàm tổng hợp

Một báo cáo có thể cần doanh thu, số giao dịch và giá trị trung bình cho từng quý. Oracle cho phép liệt kê nhiều aggregate trong cùng PIVOT:

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue,
    COUNT(*) AS transaction_count,
    AVG(amount) AS average_amount
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Các cột đầu ra được tạo cho từng tổ hợp giá trị pivot và aggregate alias, ví dụ:

- Q1_REVENUE
- Q1_TRANSACTION_COUNT
- Q1_AVERAGE_AMOUNT
- Q2_REVENUE
- Q2_TRANSACTION_COUNT
- Q2_AVERAGE_AMOUNT

Tên cụ thể phụ thuộc alias được khai báo. Nên đặt alias ngắn, rõ nghĩa và không trùng nhau để tránh tên cột sinh ra mơ hồ hoặc quá dài theo giới hạn identifier của phiên bản.

### 4.1 COUNT(*) và COUNT(measure) khác nhau

Giả sử một giao dịch có AMOUNT NULL:

- COUNT(*) đếm dòng giao dịch.
- COUNT(amount) chỉ đếm dòng có AMOUNT khác NULL.
- SUM(amount) bỏ qua giá trị NULL; nếu toàn bộ giá trị trong nhóm đều NULL thì tổng có thể là NULL.

Đây là khác biệt quan trọng khi báo cáo số giao dịch và tổng tiền.

### 4.2 Không có dữ liệu và dữ liệu NULL

Nếu một khu vực có một dòng Q2 với AMOUNT NULL, COUNT(*) cho biết dòng giao dịch tồn tại, COUNT(amount) cho biết không có giá trị amount không NULL, còn SUM(amount) không tạo ra một tổng số tiền đã biết.

Nếu không có dòng Q2 nào cho khu vực đó, kết quả pivot cho measure có thể là NULL hoặc giá trị đếm theo ngữ nghĩa aggregate. Để phân biệt rõ, nên đưa thêm COUNT(*) và COUNT(measure) vào báo cáo khi nghiệp vụ cần phân biệt:

1. Không có dòng giao dịch.
2. Có dòng giao dịch nhưng measure chưa được ghi.
3. Có dòng giao dịch với measure bằng 0.

Không thay mọi NULL thành 0 nếu ba trạng thái này có ý nghĩa khác nhau.

## 5. PIVOT với điều kiện lọc và nhiều chiều

### 5.1 Lọc dữ liệu trước khi PIVOT

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM sales
    WHERE sale_year = 2026
      AND status = 'CONFIRMED'
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

WHERE nằm trong inline view nên lọc các dòng nguồn trước khi tổng hợp. Đây là cách rõ ràng để xác định phạm vi báo cáo.

### 5.2 Pivot theo trạng thái

Ví dụ số đơn theo trạng thái:

~~~sql
SELECT *
FROM (
    SELECT region,
           order_status,
           order_id
    FROM orders
)
PIVOT (
    COUNT(order_id) AS order_count
    FOR order_status IN (
        'NEW' AS new,
        'PAID' AS paid,
        'CANCELLED' AS cancelled
    )
);
~~~

Kết quả có thể có NEW_ORDER_COUNT, PAID_ORDER_COUNT và CANCELLED_ORDER_COUNT theo từng REGION. Dùng COUNT(order_id) nếu ORDER_ID là khóa không NULL; COUNT(*) cũng có thể dùng để đếm dòng nguồn.

### 5.3 Pivot nhiều chiều theo cấp nhóm

Nếu muốn báo cáo theo REGION và CHANNEL, giữ cả hai trong inline view:

~~~sql
SELECT *
FROM (
    SELECT region,
           channel,
           quarter,
           amount
    FROM sales
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2)
)
ORDER BY region, channel;
~~~

Kết quả có một dòng cho mỗi tổ hợp REGION và CHANNEL. Cả hai cột đều là grouping columns ngầm vì không phải pivot key hoặc measure.

## 6. PIVOT tĩnh và danh sách giá trị

### 6.1 Danh sách IN được xác định trong câu SQL

Trong PIVOT thông thường, các giá trị trong IN được khai báo rõ:

~~~sql
FOR quarter IN (
    'Q1' AS q1,
    'Q2' AS q2,
    'Q3' AS q3,
    'Q4' AS q4
)
~~~

Điều đó giúp Oracle biết metadata và tên cột đầu ra khi parse câu SQL. Nếu dữ liệu xuất hiện giá trị mới như Q5 nhưng IN không liệt kê Q5, cột Q5 không tự xuất hiện trong kết quả pivot tĩnh.

### 6.2 Alias cho giá trị pivot

Alias giúp đặt tên cột đầu ra:

~~~sql
FOR month_no IN (
    1 AS jan,
    2 AS feb,
    3 AS mar
)
~~~

Khi kết hợp với aggregate alias:

~~~sql
PIVOT (
    SUM(amount) AS total
    FOR month_no IN (1 AS jan, 2 AS feb, 3 AS mar)
)
~~~

các cột có tên JAN_TOTAL, FEB_TOTAL và MAR_TOTAL.

Nên dùng alias tường minh thay vì phụ thuộc tên tự sinh từ literal, nhất là khi giá trị pivot là chuỗi dài hoặc có ký tự đặc biệt.

### 6.3 Giá trị không nằm trong IN

Nếu dữ liệu có một giá trị pivot không được liệt kê, chẳng hạn Q5, PIVOT tĩnh không tạo cột Q5. Các dòng Q5 không được đưa vào bất kỳ cột Q1–Q4 nào. Hãy xác định phạm vi dữ liệu và danh sách category trước khi xuất báo cáo.

## 7. PIVOT XML cho tập giá trị linh động

Khi category thay đổi thường xuyên và không biết trước toàn bộ danh sách, Oracle hỗ trợ PIVOT XML. Kết quả dùng một cột XMLType để biểu diễn các giá trị pivot thay vì tạo số lượng cột quan hệ thay đổi theo dữ liệu.

### 7.1 Dùng subquery trong IN

~~~sql
SELECT *
FROM (
    SELECT region,
           product,
           amount
    FROM sales
)
PIVOT XML (
    SUM(amount) AS revenue
    FOR product IN (
        SELECT DISTINCT product
        FROM sales
    )
);
~~~

Subquery trong IN xác định tập giá trị product. Với PIVOT XML dùng subquery, tập giá trị phải đáp ứng yêu cầu duy nhất của Oracle; DISTINCT là cách thường dùng khi lấy từ bảng nguồn.

Kết quả có các cột nhóm, cùng một cột XMLType chứa dữ liệu pivot. Ứng dụng cần đọc/parse XML nếu muốn trình bày từng category.

### 7.2 Dùng ANY

~~~sql
SELECT *
FROM (
    SELECT region,
           product,
           amount
    FROM sales
)
PIVOT XML (
    SUM(amount) AS revenue
    FOR product IN (ANY)
);
~~~

ANY yêu cầu Oracle đưa các giá trị pivot xuất hiện trong dữ liệu liên quan của từng nhóm vào kết quả XML. Đây là lựa chọn hữu ích khi muốn biểu diễn category thực tế mà không liệt kê thủ công.

### 7.3 PIVOT XML không tạo các cột quan hệ động

PIVOT XML vẫn trả về một schema result set cố định, trong đó dữ liệu pivot được đóng gói trong XMLType. Nếu client cần các cột Q1, Q2, Q3 được tạo động ở metadata SQL, XML không tự biến thành các cột quan hệ riêng.

Để có cột động thực sự, ứng dụng thường phải sinh câu SQL động dựa trên danh sách category, parse câu SQL mới và xử lý result set tương ứng. Cần kiểm soát giá trị và identifier đưa vào câu SQL động; không nối raw input của người dùng vào SQL.

## 8. UNPIVOT: chuyển nhiều cột thành dòng

### 8.1 Cú pháp cơ bản

~~~sql
SELECT ...
FROM source_table
UNPIVOT [INCLUDE NULLS | EXCLUDE NULLS] (
    measure_column
    FOR pivot_column
    IN (
        source_column_1 [AS value_1],
        source_column_2 [AS value_2],
        ...
    )
);
~~~

Các thành phần:

| Thành phần | Vai trò |
|---|---|
| measure_column | Cột kết quả chứa giá trị lấy từ các cột nguồn |
| pivot_column | Cột kết quả chứa nhãn chỉ ra giá trị đến từ cột nào |
| source_column | Các cột wide được chuyển thành dòng |
| value alias | Nhãn cho từng cột nguồn, ví dụ Q1 hoặc JAN |
| INCLUDE NULLS | Giữ cả dòng unpivot có measure NULL |
| EXCLUDE NULLS | Bỏ các dòng unpivot có measure NULL; đây là mặc định |

UNPIVOT không tổng hợp dữ liệu. Nó biến cấu trúc nhiều cột thành nhiều dòng.

### 8.2 Ví dụ UNPIVOT theo quý

Giả sử bảng QUARTERLY_SALES_WIDE có:

| REGION | Q1_SALES | Q2_SALES | Q3_SALES | Q4_SALES |
|---|---:|---:|---:|---:|
| North | 100 | 120 | 90 | 130 |
| South | 80 | 110 | 130 | 140 |

Truy vấn:

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Kết quả:

| REGION | QUARTER | REVENUE |
|---|---|---:|
| North | Q1 | 100 |
| North | Q2 | 120 |
| North | Q3 | 90 |
| North | Q4 | 130 |
| South | Q1 | 80 |
| South | Q2 | 110 |
| South | Q3 | 130 |
| South | Q4 | 140 |

Các cột nguồn Q1_SALES...Q4_SALES trở thành giá trị của một cột REVENUE; tên cột nguồn được chuyển thành nhãn trong QUARTER.

### 8.3 Cột không unpivot được giữ lại

Trong ví dụ, REGION không xuất hiện trong danh sách IN nên được giữ làm cột định danh cho mỗi nhóm dòng. Nếu bảng có thêm CUSTOMER_ID, PRODUCT hoặc YEAR và các cột đó không được unpivot, chúng cũng được giữ lại trong kết quả.

Chỉ đưa các cột định danh cần thiết vào nguồn nếu muốn kết quả dễ hiểu và không nhân bản quá nhiều dòng.

## 9. INCLUDE NULLS và EXCLUDE NULLS

Mặc định UNPIVOT dùng EXCLUDE NULLS. Những cột nguồn có giá trị NULL sẽ không tạo dòng trong kết quả. Có thể dùng INCLUDE NULLS để giữ lại chúng.

### 9.1 Ví dụ có NULL và số 0

Giả sử:

| REGION | Q1_SALES | Q2_SALES | Q3_SALES |
|---|---:|---:|---:|
| North | 100 | NULL | 0 |

UNPIVOT mặc định:

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3'
    )
);
~~~

Kết quả chỉ có Q1 với 100 và Q3 với 0. Dòng Q2 bị loại vì giá trị nguồn NULL. Giá trị 0 vẫn được giữ vì 0 không phải NULL.

### 9.2 INCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM quarterly_sales_wide
UNPIVOT INCLUDE NULLS (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3'
    )
);
~~~

Kết quả có cả Q1, Q2 và Q3; Q2 có REVENUE NULL. Đây là lựa chọn khi báo cáo cần phân biệt:

- Kỳ có giá trị 0.
- Kỳ chưa ghi nhận/không có giá trị.

### 9.3 NULL có ý nghĩa nghiệp vụ

Nếu NULL có nghĩa “chưa có số liệu”, bỏ dòng khi UNPIVOT có thể làm mất dấu thông tin đó. Nếu NULL có nghĩa “không áp dụng”, có thể nghiệp vụ lại muốn loại. Chọn INCLUDE hay EXCLUDE dựa trên ý nghĩa dữ liệu, không chỉ dựa vào việc kết quả có ít dòng hơn.

## 10. UNPIVOT nhiều measure cùng lúc

Một bảng wide có thể lưu cả số lượng và doanh thu theo từng quý:

| REGION | Q1_QTY | Q1_REVENUE | Q2_QTY | Q2_REVENUE |
|---|---:|---:|---:|---:|
| North | 10 | 1000 | 12 | 1300 |
| South | 8 | 800 | 9 | 950 |

Có thể unpivot theo nhóm cột:

~~~sql
SELECT region,
       quarter,
       quantity,
       revenue
FROM quarterly_metrics_wide
UNPIVOT (
    (quantity, revenue)
    FOR quarter IN (
        (q1_qty, q1_revenue) AS 'Q1',
        (q2_qty, q2_revenue) AS 'Q2',
        (q3_qty, q3_revenue) AS 'Q3',
        (q4_qty, q4_revenue) AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Mỗi cặp cột Q1_QTY/Q1_REVENUE trở thành một dòng Q1 với hai measure QUANTITY và REVENUE. Tương tự cho các quý còn lại.

### 10.1 Các cột phải tương thích kiểu dữ liệu

UNPIVOT yêu cầu các cột được đưa vào cùng một nhóm measure có kiểu dữ liệu tương thích theo quy tắc của Oracle. Với một measure đơn, các cột nguồn phải thuộc cùng data type group; Oracle có quy tắc chuyển đổi trong nhóm số. Không trộn tùy tiện NUMBER với VARCHAR2 hoặc DATE trong cùng một measure.

Với UNPIVOT nhiều measure, các cột tương ứng giữa các tuple phải tương thích theo từng vị trí: tất cả cột quantity tương thích với nhau, tất cả cột revenue tương thích với nhau. Nếu không, Oracle có thể báo lỗi datatype không tương thích.

Nếu nguồn có kiểu khác nhau, hãy CAST về kiểu đích rõ ràng trong một inline view trước khi UNPIVOT, đồng thời xác định format và cách xử lý dữ liệu không chuyển được.

### 10.2 INCLUDE NULLS với nhiều measure

Với tuple nhiều cột, hãy xác định chính sách NULL của cả nhóm measure và thử trên dữ liệu đại diện. INCLUDE NULLS hữu ích nếu cần giữ kỳ mà một hoặc nhiều measure chưa được ghi nhận; ứng dụng cần hiểu mỗi measure có thể NULL độc lập.

## 11. PIVOT và conditional aggregation

Không phải lúc nào cũng cần dùng cú pháp PIVOT. Có thể tạo cột báo cáo bằng aggregate kết hợp CASE:

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2_revenue,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3_revenue,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4_revenue
FROM sales
GROUP BY region
ORDER BY region;
~~~

Đây là **conditional aggregation** (tổng hợp có điều kiện).

### 11.1 So sánh hai cách

PIVOT:

~~~sql
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM sales
)
PIVOT (
    SUM(amount)
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
);
~~~

Conditional aggregation:

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4
FROM sales
GROUP BY region;
~~~

Hai cách có thể tạo kết quả tương đương nếu dùng cùng grouping, điều kiện và aggregate semantics.

| Tiêu chí | PIVOT | Conditional aggregation |
|---|---|---|
| Ý định xoay giá trị thành cột | Cú pháp trực tiếp, dễ nhận ra | Phải viết CASE cho từng cột |
| Nhiều điều kiện khác nhau mỗi cột | Có thể cần biểu thức hoặc nhiều lớp truy vấn | Linh hoạt trong từng CASE |
| Nhiều aggregate | Hỗ trợ nhiều hàm trong một PIVOT | Viết nhiều aggregate expression |
| Danh sách category tĩnh | IN list rõ ràng | CASE list rõ ràng |
| Category động | PIVOT XML hoặc SQL động | SQL động hoặc định dạng long/XML |
| Dễ kiểm soát logic đặc biệt | Phù hợp với mẫu pivot chuẩn | Thường linh hoạt hơn |

### 11.2 Đếm giao dịch và đếm giá trị không NULL

~~~sql
SELECT region,
       COUNT(CASE WHEN quarter = 'Q1' THEN 1 END) AS q1_rows,
       COUNT(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_known_amounts,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue
FROM sales
GROUP BY region;
~~~

Q1_ROWS đếm số dòng Q1; Q1_KNOWN_AMOUNTS chỉ đếm dòng có AMOUNT khác NULL; Q1_REVENUE cộng giá trị amount không NULL. Ba cột giúp báo cáo phân biệt không có giao dịch, có giao dịch nhưng thiếu amount và có amount bằng 0.

### 11.3 Không mặc định SUM NULL thành 0

Nếu không có dòng nào khớp một quý, SUM(CASE WHEN ... THEN amount END) có thể trả NULL. Có thể dùng NVL:

~~~sql
NVL(
  SUM(CASE WHEN quarter = 'Q1' THEN amount END),
  0
) AS q1_revenue
~~~

Nhưng chỉ làm vậy nếu báo cáo muốn biểu diễn “không có giá trị” thành số 0. Nếu cần phân biệt không phát sinh giao dịch với giao dịch có amount chưa ghi nhận, giữ NULL và bổ sung COUNT phù hợp.

### 11.4 PIVOT không mặc định nhanh hơn

PIVOT và conditional aggregation có thể được optimizer chuyển thành các phép tổng hợp tương tự. Không nên khẳng định một cú pháp luôn nhanh hơn cú pháp kia. Hãy chọn cách dễ diễn đạt logic, sau đó đo trên dữ liệu thực tế và xem execution plan khi cần tuning.

## 12. PIVOT và UNPIVOT không phải phép nghịch đảo hoàn hảo

Về hình thức, PIVOT chuyển long sang wide; UNPIVOT chuyển wide sang long. Nhưng hai phép không luôn đảo ngược chính xác.

### 12.1 PIVOT thường có tổng hợp làm mất chi tiết

Nếu nguồn có:

| REGION | QUARTER | AMOUNT |
|---|---|---:|
| North | Q1 | 100 |
| North | Q1 | 50 |

PIVOT SUM tạo Q1 = 150. Sau đó UNPIVOT chỉ khôi phục được một dòng North/Q1/150, không thể biết ban đầu có hai giao dịch 100 và 50.

Thông tin chi tiết đã mất do SUM. Muốn giữ chi tiết, cần giữ khóa giao dịch hoặc không tổng hợp ở cấp đó; nhưng khi đó kết quả pivot có thể có nhiều dòng hơn.

### 12.2 EXCLUDE NULLS làm mất thêm dòng

Nếu wide có Q2 NULL, UNPIVOT mặc định loại dòng Q2. Dù trước đó không có phép tổng hợp làm mất dữ liệu, lựa chọn EXCLUDE NULLS cũng làm mất thông tin rằng ô Q2 từng tồn tại nhưng không có giá trị.

Dùng INCLUDE NULLS nếu cần bảo toàn các ô NULL ở mức cấu trúc.

### 12.3 PIVOT tĩnh chỉ giữ category được liệt kê

Nếu IN list chỉ có Q1–Q4 mà dữ liệu nguồn có Q5, cột Q5 không được tạo. Vì vậy pivot rồi unpivot không thể phục hồi những category không được đưa vào danh sách.

### 12.4 Không có khóa dòng thì không thể khôi phục thứ tự gốc

Quan hệ trong Oracle không có thứ tự tự nhiên được bảo đảm. Sau PIVOT/UNPIVOT, nếu không có khóa và ORDER BY, không thể suy ra thứ tự ban đầu của các dòng. Nếu cần giữ thứ tự hoặc danh tính bản ghi, phải lưu khóa và sắp xếp rõ ràng.

## 13. PIVOT/UNPIVOT trong thiết kế báo cáo

### 13.1 Khi dữ liệu lưu trữ nên ở dạng long

Mô hình:

~~~text
SALES
  SALE_ID
  REGION
  SALE_DATE
  PRODUCT_ID
  AMOUNT
~~~

phù hợp khi:

- Category thay đổi theo thời gian.
- Có nhiều năm, tháng, quý hoặc trạng thái.
- Cần lọc, nhóm, join và phân tích theo nhiều chiều.
- Dữ liệu được nạp liên tục từ giao dịch.

Không cần thêm cột Q1, Q2, Q3, Q4 vào bảng giao dịch chỉ để làm báo cáo quý.

### 13.2 Khi wide phù hợp

Wide có thể hữu ích khi:

- Xuất báo cáo có số cột cố định.
- Tạo bảng chéo cho người đọc.
- Kết nối với mẫu Excel hoặc giao diện yêu cầu từng kỳ là một cột.
- Tạo dữ liệu đầu vào cho hệ thống downstream có schema cố định.

Nên tạo wide ở lớp view, query hoặc reporting mart phù hợp, thay vì làm hỏng mô hình giao dịch chuẩn hóa.

### 13.3 Tách lớp dữ liệu và lớp trình bày

Một kiến trúc thường dễ duy trì:

~~~text
Bảng giao dịch dạng long
          |
          v
Lọc và chuẩn hóa dữ liệu
          |
          v
Tổng hợp theo dimension
          |
          v
PIVOT / conditional aggregation
          |
          v
Báo cáo wide cho người dùng
~~~

Nếu hệ thống cần tái sử dụng số liệu ở nhiều loại báo cáo, cân nhắc view hoặc materialized view tùy tần suất, độ trễ và chính sách refresh. PIVOT trong SELECT không tự tạo bảng vật lý hay lưu kết quả.

## 14. Bài lab: PIVOT dữ liệu doanh thu dạng long

Các lệnh trong phần này dành cho schema thực hành riêng có quyền tạo bảng và quota phù hợp. Không chạy DDL/DML thử nghiệm trong schema production. Oracle DDL như CREATE TABLE có implicit commit.

### 14.1 Tạo bảng nguồn

~~~sql
CREATE TABLE lab_sales_long (
    sale_id NUMBER PRIMARY KEY,
    region  VARCHAR2(20) NOT NULL,
    quarter VARCHAR2(2) NOT NULL,
    amount  NUMBER(12,2)
);
~~~

### 14.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_sales_long VALUES (1, 'North', 'Q1', 100);
INSERT INTO lab_sales_long VALUES (2, 'North', 'Q1', 50);
INSERT INTO lab_sales_long VALUES (3, 'North', 'Q2', 120);
INSERT INTO lab_sales_long VALUES (4, 'North', 'Q3', 90);
INSERT INTO lab_sales_long VALUES (5, 'South', 'Q1', 80);
INSERT INTO lab_sales_long VALUES (6, 'South', 'Q2', 110);
INSERT INTO lab_sales_long VALUES (7, 'South', 'Q3', 130);
INSERT INTO lab_sales_long VALUES (8, 'East', 'Q2', NULL);
INSERT INTO lab_sales_long VALUES (9, 'East', 'Q4', 0);
COMMIT;
~~~

Dữ liệu có nhiều giao dịch cùng North/Q1, một measure NULL ở East/Q2 và một giá trị 0 ở East/Q4.

### 14.3 Xem dữ liệu nguồn

~~~sql
SELECT region,
       quarter,
       amount
FROM lab_sales_long
ORDER BY region, quarter, sale_id;
~~~

### 14.4 Pivot doanh thu theo quý

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Kết quả mong đợi về tổng:

| REGION | Q1_REVENUE | Q2_REVENUE | Q3_REVENUE | Q4_REVENUE |
|---|---:|---:|---:|---:|
| East | NULL | NULL | NULL | 0 |
| North | 150 | 120 | 90 | NULL |
| South | 80 | 110 | 130 | NULL |

Q1 của North bằng 150 vì có hai dòng 100 và 50. Q2 của East là NULL vì dòng duy nhất có AMOUNT NULL; Q4 của East bằng 0 vì có dòng với giá trị 0.

### 14.5 Pivot nhiều aggregate

~~~sql
SELECT *
FROM (
    SELECT region,
           quarter,
           amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue,
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
)
ORDER BY region;
~~~

Đối với East/Q2, cần quan sát:

- Q2_REVENUE là NULL vì amount của dòng đó NULL.
- Q2_ROW_COUNT phản ánh có một dòng nguồn.
- Q2_KNOWN_AMOUNT_COUNT là 0 vì không có amount khác NULL.

Đối với East/Q4, amount bằng 0 là giá trị đã biết; COUNT(amount) đếm được dòng này. Đây là cách phân biệt NULL và số 0.

### 14.6 So sánh bằng conditional aggregation

~~~sql
SELECT region,
       SUM(CASE WHEN quarter = 'Q1' THEN amount END) AS q1_revenue,
       SUM(CASE WHEN quarter = 'Q2' THEN amount END) AS q2_revenue,
       SUM(CASE WHEN quarter = 'Q3' THEN amount END) AS q3_revenue,
       SUM(CASE WHEN quarter = 'Q4' THEN amount END) AS q4_revenue
FROM lab_sales_long
GROUP BY region
ORDER BY region;
~~~

So sánh với kết quả PIVOT. Cùng grouping và aggregate thì các tổng có thể khớp nhau.

## 15. Bài lab: UNPIVOT dữ liệu wide

### 15.1 Tạo bảng wide

~~~sql
CREATE TABLE lab_sales_wide (
    region    VARCHAR2(20) PRIMARY KEY,
    q1_sales  NUMBER(12,2),
    q2_sales  NUMBER(12,2),
    q3_sales  NUMBER(12,2),
    q4_sales  NUMBER(12,2)
);
~~~

### 15.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_sales_wide VALUES ('North', 100, 120, NULL, 0);
INSERT INTO lab_sales_wide VALUES ('South', 80, NULL, 90, 140);
COMMIT;
~~~

North/Q3 và South/Q2 là NULL; North/Q4 là 0.

### 15.3 UNPIVOT mặc định EXCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM lab_sales_wide
UNPIVOT (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Kết quả không có North/Q3 và South/Q2 do các ô đó NULL. North/Q4 vẫn xuất hiện với revenue 0.

### 15.4 UNPIVOT INCLUDE NULLS

~~~sql
SELECT region,
       quarter,
       revenue
FROM lab_sales_wide
UNPIVOT INCLUDE NULLS (
    revenue
    FOR quarter IN (
        q1_sales AS 'Q1',
        q2_sales AS 'Q2',
        q3_sales AS 'Q3',
        q4_sales AS 'Q4'
    )
)
ORDER BY region, quarter;
~~~

Kết quả có đủ tám tổ hợp khu vực/quý, bao gồm hai dòng NULL. Đây là lựa chọn phù hợp nếu cần giữ trạng thái chưa có dữ liệu trong từng kỳ.

### 15.5 UNPIVOT nhiều measure

Tạo bảng minh họa:

~~~sql
CREATE TABLE lab_quarter_metrics (
    region      VARCHAR2(20),
    q1_qty      NUMBER(10),
    q1_revenue  NUMBER(12,2),
    q2_qty      NUMBER(10),
    q2_revenue  NUMBER(12,2)
);
~~~

Nạp:

~~~sql
INSERT INTO lab_quarter_metrics VALUES ('North', 10, 1000, 12, 1300);
INSERT INTO lab_quarter_metrics VALUES ('South', 8, 800, 9, 950);
COMMIT;
~~~

Truy vấn:

~~~sql
SELECT region,
       quarter,
       quantity,
       revenue
FROM lab_quarter_metrics
UNPIVOT (
    (quantity, revenue)
    FOR quarter IN (
        (q1_qty, q1_revenue) AS 'Q1',
        (q2_qty, q2_revenue) AS 'Q2'
    )
)
ORDER BY region, quarter;
~~~

Mỗi cặp cột được chuyển thành một dòng với hai measure. Khi thêm quý mới, cần thêm các cột nguồn và tuple tương ứng trong IN list.

### 15.6 Dọn bảng lab

Chỉ xóa các bảng do bạn tạo trong schema thực hành nếu đã xác nhận không còn cần dữ liệu. Không đưa DROP TABLE vào script có thể chạy nhầm production; DDL có implicit commit và không thể trông chờ ROLLBACK để khôi phục.

## 16. Dynamic PIVOT: khi category thay đổi

Một câu PIVOT tĩnh phải khai báo IN list tại thời điểm parse. Nếu báo cáo cần tự thêm cột theo danh mục hiện có, có hai hướng chính.

### 16.1 PIVOT XML

PIVOT XML cho phép dùng subquery hoặc ANY để xác định các giá trị pivot động, nhưng trả kết quả pivot trong XMLType. Cách này phù hợp khi client có thể xử lý XML hoặc cần một schema result set cố định.

### 16.2 Sinh SQL động

Ứng dụng có thể truy vấn danh sách category, tạo danh sách literal/alias đã được kiểm soát rồi sinh câu PIVOT mới. Mỗi danh sách category sẽ tạo một shape result set khác nhau.

Khi sinh SQL động:

- Chỉ lấy category từ nguồn dữ liệu đã được kiểm soát hoặc whitelist.
- Escape literal đúng cách; không nối raw input người dùng.
- Identifier/alias không thể được thay thế bằng bind variable thông thường; phải kiểm soát và quote identifier theo quy tắc Oracle.
- Các giá trị filter dữ liệu vẫn nên bind variable.
- Client cần xử lý metadata cột thay đổi giữa các lần chạy.

Không có một câu SELECT tĩnh thông thường trả về số cột quan hệ tùy ý theo dữ liệu mà vẫn giữ metadata cố định. Nếu ứng dụng không thật sự cần cột động, trả dữ liệu long thường đơn giản hơn.

## 17. Các lỗi và ngộ nhận thường gặp

| Lỗi/ngộ nhận | Nguyên nhân | Cách xử lý |
|---|---|---|
| PIVOT chỉ đổi tên cột, không tổng hợp | PIVOT có aggregate và grouping ngầm | Chọn aggregate phù hợp |
| Kết quả có quá nhiều dòng | Nguồn PIVOT có thêm cột không mong muốn, trở thành grouping key | Giảm SELECT list của inline view |
| Giá trị category mới tự xuất hiện thành cột | PIVOT tĩnh chỉ tạo cột trong IN list | Cập nhật IN, dùng PIVOT XML hoặc SQL động |
| PIVOT trả NULL nên tưởng không có dòng | Có thể có dòng nhưng measure NULL | Thêm COUNT(*) và COUNT(measure) |
| COUNT(*) và COUNT(amount) giống nhau | COUNT(amount) bỏ qua NULL | Chọn theo ý nghĩa đếm dòng hay đếm giá trị đã biết |
| UNPIVOT mất một số kỳ | Mặc định EXCLUDE NULLS | Dùng INCLUDE NULLS nếu cần giữ ô NULL |
| Số 0 bị loại khi UNPIVOT | Nhầm 0 với NULL | 0 vẫn được giữ; kiểm tra kiểu và dữ liệu |
| UNPIVOT dùng được mọi kiểu cột | Các cột nguồn phải tương thích datatype group | CAST trong inline view nếu có lý do rõ |
| PIVOT rồi UNPIVOT luôn khôi phục dữ liệu gốc | Aggregate, EXCLUDE NULLS và category bị bỏ có thể làm mất thông tin | Giữ khóa/chi tiết và kiểm tra semantics |
| PIVOT luôn nhanh hơn CASE | Optimizer và workload quyết định | So sánh actual plan trên dữ liệu đại diện |
| Cột động có thể bind như giá trị WHERE | IN list quyết định metadata cột khi parse | XML hoặc sinh SQL động an toàn |
| PIVOT XML tạo cột quan hệ riêng cho mỗi category | XML gom các giá trị vào một cột XMLType | Parse XML hoặc dùng SQL động nếu cần cột riêng |

## 18. Hiệu năng và lựa chọn kiến trúc

### 18.1 Kiểm soát số chiều grouping

PIVOT nhóm theo tất cả các cột nguồn còn lại. Đưa quá nhiều cột vào inline view có thể làm số nhóm tăng mạnh và kết quả bị chia nhỏ. Hãy chọn đúng dimension cần giữ trước khi pivot.

### 18.2 Lọc sớm khi có thể

Nếu chỉ báo cáo một năm hoặc một trạng thái, đặt điều kiện trong inline view để giới hạn nguồn. Điều này giúp truy vấn thể hiện rõ phạm vi dữ liệu và có thể giảm số dòng cần tổng hợp. Optimizer vẫn quyết định thứ tự thực thi vật lý dựa trên cost và transformations.

### 18.3 Index theo truy vấn nguồn

Index có thể hữu ích cho predicate lọc và join trước khi PIVOT/UNPIVOT. Ví dụ báo cáo lọc theo YEAR, REGION và QUARTER có thể cần xem index hiện có, độ chọn lọc, partitioning và workload. Không tạo index chỉ dựa trên một ví dụ SQL.

### 18.4 PIVOT trong view và materialized view

Một view chứa PIVOT là cách đóng gói logic truy vấn, không tự lưu kết quả. Nếu báo cáo nặng và được chạy thường xuyên, có thể đánh giá materialized view hoặc reporting table theo yêu cầu freshness, lịch refresh và khả năng query rewrite. Đây là quyết định kiến trúc riêng, không phải yêu cầu bắt buộc của cú pháp PIVOT.

### 18.5 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount)
    FOR quarter IN ('Q1' AS q1, 'Q2' AS q2, 'Q3' AS q3, 'Q4' AS q4)
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN thể hiện kế hoạch dự kiến, không phải phép đo thời gian thực. Khi tuning, cần xem actual plan, cardinality, sort/hash operations, I/O, CPU và kích thước dữ liệu đại diện.

## 19. Checklist thiết kế truy vấn báo cáo

Trước khi viết PIVOT hoặc UNPIVOT, xác định:

1. Dữ liệu đầu vào đang ở dạng long hay wide?
2. Mỗi dòng nguồn đại diện cho một giao dịch, một nhóm hay một bản tổng hợp?
3. Những cột nào phải được giữ làm dimension?
4. Cột nào là pivot key, cột nào là measure?
5. Cần SUM, COUNT, AVG, MIN hay MAX?
6. Nếu measure NULL, báo cáo phải giữ NULL, hiển thị 0 hay phân biệt với không có dòng?
7. Category có cố định không? Nếu động, client có xử lý XML hoặc schema cột thay đổi được không?
8. Với UNPIVOT, có cần INCLUDE NULLS không?
9. Các cột nguồn có datatype group tương thích không?
10. PIVOT có làm mất chi tiết do aggregate không? Có cần giữ khóa giao dịch?
11. Kết quả cần thứ tự nào? Hãy thêm ORDER BY tường minh.
12. Truy vấn có cần index, partition pruning, view hoặc materialized view không?

## 20. Bài tập tự luyện

**Câu 1 — PIVOT theo quý.** Từ LAB_SALES_LONG, viết truy vấn đưa Q1, Q2, Q3, Q4 thành cột tổng doanh thu theo REGION.

Gợi ý:

~~~sql
SELECT *
FROM (
    SELECT region, quarter, amount
    FROM lab_sales_long
)
PIVOT (
    SUM(amount) AS revenue
    FOR quarter IN (
        'Q1' AS q1,
        'Q2' AS q2,
        'Q3' AS q3,
        'Q4' AS q4
    )
);
~~~

**Câu 2 — Grouping ngầm.** Nếu thêm SALE_ID vào inline view của câu 1, vì sao kết quả có thể thành nhiều dòng cho mỗi REGION?

Gợi ý: SALE_ID không phải pivot key hoặc measure, nên nó trở thành một phần của grouping ngầm.

**Câu 3 — Nhiều aggregate.** Thêm COUNT(*) và COUNT(amount) vào PIVOT để phân biệt số dòng nguồn và số measure đã biết.

Gợi ý: Đặt alias riêng cho từng aggregate để tên cột đầu ra rõ ràng.

**Câu 4 — UNPIVOT NULL.** Chạy UNPIVOT mặc định trên LAB_SALES_WIDE và giải thích vì sao North/Q3 không xuất hiện.

Gợi ý: Mặc định là EXCLUDE NULLS. Chạy lại với INCLUDE NULLS để giữ dòng đó.

**Câu 5 — Số 0 và NULL.** Vì sao North/Q4 vẫn xuất hiện trong UNPIVOT mặc định dù revenue bằng 0?

Gợi ý: 0 là một giá trị số; chỉ NULL mới bị EXCLUDE.

**Câu 6 — Dynamic pivot.** Khi category sản phẩm được thêm mới mỗi tháng, hãy nêu hai hướng để báo cáo phản ánh category mới.

Gợi ý: PIVOT XML với subquery/ANY hoặc sinh SQL động an toàn. Nếu client chấp nhận dữ liệu long, có thể không cần pivot động.

**Câu 7 — PIVOT rồi UNPIVOT.** Nếu hai giao dịch North/Q1 là 100 và 50, sau PIVOT SUM rồi UNPIVOT có khôi phục được hai giao dịch riêng không?

Gợi ý: Không. SUM đã gộp thành 150 và làm mất danh tính hai dòng nguồn.

**Câu 8 — Chọn PIVOT hay CASE.** Một báo cáo cần Q1 doanh thu đã xác nhận, Q2 doanh thu mọi trạng thái và Q3 số giao dịch lỗi. Cách nào dễ biểu đạt điều kiện riêng cho từng cột?

Gợi ý: Conditional aggregation với CASE thường linh hoạt hơn khi mỗi cột có predicate khác nhau.

## 21. Tổng kết

PIVOT và UNPIVOT là hai công cụ chuyển đổi hình dạng dữ liệu báo cáo trong Oracle:

- **PIVOT** biến các giá trị của một dimension thành các cột, đồng thời áp dụng aggregate như SUM hoặc COUNT. Các cột nguồn còn lại tạo grouping ngầm, nên inline view cần chỉ chứa đúng dimension và measure mong muốn.
- **PIVOT XML** hỗ trợ category linh động bằng cách trả dữ liệu pivot trong XMLType; muốn các cột quan hệ động cần xử lý XML hoặc sinh SQL động có kiểm soát.
- **UNPIVOT** biến nhiều cột thành dòng và tạo nhãn cho cột nguồn. Mặc định EXCLUDE NULLS; INCLUDE NULLS giữ cả các ô chưa có giá trị.
- **Conditional aggregation** là phương án thay thế linh hoạt khi mỗi cột báo cáo cần điều kiện riêng hoặc muốn kiểm soát rõ logic.
- PIVOT và UNPIVOT không phải phép nghịch đảo hoàn hảo: aggregate, NULL bị loại và category không được liệt kê có thể làm mất thông tin.

Hãy thiết kế dữ liệu giao dịch theo semantics rõ ràng, dùng PIVOT/UNPIVOT ở lớp báo cáo khi phù hợp, kiểm soát grouping và NULL, rồi kiểm tra execution plan trên dữ liệu đại diện. Khi hiểu đúng các quy tắc này, bạn có thể tạo bảng chéo dễ đọc mà vẫn giữ được tính chính xác và khả năng bảo trì của truy vấn Oracle.
