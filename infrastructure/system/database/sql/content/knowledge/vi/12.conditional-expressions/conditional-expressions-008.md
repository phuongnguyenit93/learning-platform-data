# Giới hạn khi dùng CASE để tránh lỗi đánh giá biểu thức

## 1. CASE giúp rẽ nhánh giá trị, nhưng không phải “lá chắn” cho mọi lỗi

Trong SQL, `CASE` là **biểu thức điều kiện**: dựa trên các điều kiện, nó chọn một giá trị kết quả. Khi lập trình, người học dễ liên tưởng `CASE` với câu lệnh `if/else` trong Java hoặc Python rồi suy luận rằng mọi phép tính ở nhánh không được chọn **chắc chắn không bao giờ được đụng tới**.

Suy luận đó chỉ đúng trong một phạm vi nhất định. Trong phép tính thông thường trên từng hàng, `CASE` thường cho phép chọn nhánh phù hợp mà không cần tính giá trị của các nhánh không được chọn. Tuy nhiên, SQL được **phân tích, tối ưu hóa và lập kế hoạch** trước hoặc trong quá trình thực thi. Có những biểu thức có thể được xử lý ở thời điểm khác với trực giác “đọc từ trên xuống”, đặc biệt là:

- **Hằng số và biểu thức có thể tính trước (constant folding):** bộ tối ưu có thể đánh giá một phép tính ngay ở giai đoạn lập kế hoạch.
- **Hàm tổng hợp (`SUM`, `AVG`, `MIN`, `MAX`, …):** các biểu thức đầu vào của tổng hợp có thể được tính trước khi biểu thức `CASE` bao ngoài nhận giá trị tổng hợp.
- **Điều kiện kết hợp bằng `AND`/`OR`:** thứ tự đánh giá các điều kiện không phải hợp đồng thực thi cố định.
- **Ép kiểu và suy diễn kiểu:** SQL có thể yêu cầu các nhánh của `CASE` tương thích kiểu trước khi biết nhánh nào được chọn.
- **Hàm có lỗi miền giá trị, side effect hoặc hành vi phụ thuộc DBMS:** không thể dùng `CASE` như cơ chế xử lý ngoại lệ tổng quát.

Mục tiêu của bài là biết **khi nào `CASE` phù hợp**, nhận ra **giới hạn bảo vệ lỗi**, và viết các biểu thức SQL an toàn hơn cho chia cho 0, chuyển kiểu, hàm toán học và tổng hợp dữ liệu.

**Nguyên tắc trọng tâm:** ưu tiên **làm cho toán hạng của phép tính rủi ro trở nên an toàn** bằng các biểu thức như `NULLIF`, kiểm tra kiểu trước khi chuyển đổi hoặc chuẩn hóa dữ liệu. Dùng `CASE` để biểu diễn **quy tắc nghiệp vụ**, nhưng không mặc định nó tạo một thứ tự chạy vật lý cho mọi phép tính xung quanh.

## 2. Nhắc lại hai dạng CASE

### 2.1. Searched CASE: điều kiện riêng cho từng nhánh

~~~sql
CASE
    WHEN <dieu_kien_1> THEN <gia_tri_1>
    WHEN <dieu_kien_2> THEN <gia_tri_2>
    ELSE <gia_tri_mac_dinh>
END
~~~

Ví dụ phân loại tồn kho:

~~~sql
SELECT
    product_id,
    stock_quantity,
    CASE
        WHEN stock_quantity = 0 THEN 'HET_HANG'
        WHEN stock_quantity < 5 THEN 'SAP_HET'
        ELSE 'CON_HANG'
    END AS stock_status
FROM products;
~~~

Các điều kiện được xét theo thứ tự **ưu tiên logic của `CASE`**: nhánh `WHEN` đầu tiên có điều kiện `TRUE` quyết định giá trị kết quả. `WHEN` cho kết quả `FALSE` hoặc `UNKNOWN` không được chọn. Nếu không nhánh nào phù hợp thì dùng `ELSE`; thiếu `ELSE` sẽ trả `NULL`.

Dạng này thích hợp cho điều kiện phức tạp: khoảng giá trị, kiểm tra `NULL`, kết hợp nhiều cột hoặc kiểm tra điều kiện an toàn trước một phép tính.

### 2.2. Simple CASE: so một biểu thức với nhiều giá trị

~~~sql
CASE status
    WHEN 'NEW' THEN 'Mới tạo'
    WHEN 'DONE' THEN 'Hoàn tất'
    ELSE 'Khác'
END
~~~

Simple `CASE` phù hợp khi chỉ cần so sánh một biểu thức với các giá trị cụ thể. Chú ý trường hợp `NULL`:

~~~sql
-- Không hoạt động như phép kiểm tra NULL:
CASE status
    WHEN NULL THEN 'Chưa xác định'
    ELSE 'Có trạng thái'
END
~~~

So sánh kiểu `status = NULL` không cho `TRUE`. Hãy dùng searched `CASE`:

~~~sql
CASE
    WHEN status IS NULL THEN 'Chưa xác định'
    ELSE 'Có trạng thái'
END
~~~

Bài này chủ yếu dùng **searched `CASE`**, vì các điều kiện kiểm tra rủi ro cần được viết rõ.

## 3. Dữ liệu mẫu để quan sát tình huống rủi ro

Các ví dụ chính được viết cho **PostgreSQL**, với cách hoạt động của `NUMERIC`, `NULLIF`, tổng hợp và bộ tối ưu PostgreSQL. Các nguyên tắc về thứ tự logic còn áp dụng rộng hơn, nhưng thông báo lỗi và cách lập kế hoạch có thể khác giữa DBMS.

~~~sql
CREATE TABLE metrics (
    metric_id     INTEGER PRIMARY KEY,
    metric_name   VARCHAR(60) NOT NULL,
    numerator     NUMERIC(12, 2),
    denominator   NUMERIC(12, 2),
    raw_rate      VARCHAR(40),
    score         NUMERIC(12, 2)
);

INSERT INTO metrics (
    metric_id, metric_name, numerator, denominator, raw_rate, score
)
VALUES
    (1, 'Binh thuong',     100.00,  20.00, '12.50',      9.00),
    (2, 'Mau so bang 0',    70.00,   0.00, 'N/A',         0.00),
    (3, 'Tu so NULL',        NULL,   5.00, '8.0',        -2.00),
    (4, 'Mau so NULL',     50.00,    NULL, 'abc',        16.00),
    (5, 'Gia tri am',        0.00, -10.00, NULL,         25.00),
    (6, 'Binh thuong 2',   36.00,   6.00, '1000000000',  4.00);
~~~

Ý nghĩa các cột:

- `numerator`: tử số, có thể thiếu.
- `denominator`: mẫu số, có thể bằng 0 hoặc thiếu.
- `raw_rate`: dữ liệu văn bản đến từ nguồn chưa chuẩn hóa, có thể không chuyển được sang số.
- `score`: giá trị dùng cho ví dụ `SQRT` và `LN`; có cả giá trị âm hoặc bằng 0.

Một số phép toán sẽ gặp lỗi nếu viết trực tiếp:

~~~sql
-- Với PostgreSQL: có hàng denominator = 0 nên truy vấn có thể lỗi.
SELECT
    metric_id,
    numerator / denominator AS ratio
FROM metrics
ORDER BY metric_id;
~~~

~~~sql
-- PostgreSQL: chuỗi 'N/A' hoặc 'abc' không ép sang NUMERIC được.
SELECT metric_id, CAST(raw_rate AS NUMERIC)
FROM metrics;
~~~

~~~sql
-- PostgreSQL: SQRT không chấp nhận giá trị âm.
SELECT metric_id, SQRT(score)
FROM metrics;
~~~

Nhu cầu là hiển thị hoặc thống kê dữ liệu mà **không làm hỏng cả câu truy vấn** chỉ vì một vài hàng chứa giá trị không phù hợp. Tuy nhiên, xử lý lỗi kiểu gì phải xuất phát từ nghiệp vụ: bỏ hàng, trả `NULL`, đánh dấu lỗi hay từ chối dữ liệu đầu vào đều có ý nghĩa khác nhau.

## 4. CASE bảo vệ phép tính từng hàng ở mức logic

Một mẫu dễ hiểu để tránh chia cho 0:

~~~sql
SELECT
    metric_id,
    numerator,
    denominator,
    CASE
        WHEN denominator = 0 THEN NULL
        ELSE numerator / denominator
    END AS ratio
FROM metrics
ORDER BY metric_id;
~~~

Với dữ liệu minh họa trong PostgreSQL, biểu thức trên phù hợp cho phép chia **từng hàng**:

| metric_id | numerator | denominator | ratio |
| ---: | ---: | ---: | ---: |
| 1 | 100.00 | 20.00 | 5 |
| 2 | 70.00 | 0.00 | NULL |
| 3 | NULL | 5.00 | NULL |
| 4 | 50.00 | NULL | NULL |
| 5 | 0.00 | -10.00 | 0 |
| 6 | 36.00 | 6.00 | 6 |

Lý do:

- Hàng 2 chọn nhánh `THEN NULL`, không cần phép chia bằng 0 ở nhánh `ELSE`.
- Hàng 3 và 4 có một toán hạng `NULL`; phép chia số học với `NULL` cho `NULL`.
- Hàng 5 có mẫu số âm nhưng **khác 0**, nên phép chia hợp lệ về mặt SQL. Nếu nghiệp vụ cấm mẫu số âm, cần kiểm tra riêng.

Dạng `CASE` này là **một cách viết có ý nghĩa** cho ví dụ chia từng hàng. Vấn đề xuất hiện khi người viết suy rộng thành quy tắc “`CASE` luôn bảo vệ bất kỳ thứ gì được đặt trong nhánh `THEN` hoặc `ELSE`, ở mọi cấp truy vấn”. Hai phần tiếp theo làm rõ tại sao không thể bảo đảm như vậy.

## 5. Giới hạn thứ nhất: biểu thức hằng có thể được tính lúc lập kế hoạch

Xem câu SQL:

~~~sql
-- Không dùng như một bảo đảm an toàn chung:
SELECT CASE
    WHEN 1 = 1 THEN 42
    ELSE 1 / 0
END AS answer;
~~~

Theo trực giác, nhánh `WHEN 1 = 1` là `TRUE` nên `ELSE 1 / 0` sẽ không được chọn. Nhưng PostgreSQL và các DBMS có cơ chế tối ưu hằng số **có thể đánh giá biểu thức hằng ở giai đoạn lập kế hoạch**, trước khi thực hiện rẽ nhánh theo từng hàng. PostgreSQL nêu rõ rằng nguyên tắc không đánh giá các nhánh không cần thiết của `CASE` **không phải bảo đảm tuyệt đối**, và một biểu thức hằng kiểu `1/0` có thể bị phát hiện lỗi từ giai đoạn lập kế hoạch ngay cả khi ở nhánh không được chọn.

Điều cần hiểu:

1. **Phân tích và kiểm tra kiểu** phải xảy ra trước khi có giá trị từng hàng.
2. Bộ tối ưu được phép **rút gọn biểu thức hằng** để lập kế hoạch tốt hơn.
3. Một biểu thức vô nghĩa như `1/0` có thể gây lỗi hoặc bị xử lý sớm theo cơ chế của DBMS.
4. Câu SQL thành công trong một phiên bản/cấu hình không biến “nhánh chết luôn vô hại” thành hợp đồng di động.

Không nên đưa một phép tính chắc chắn không hợp lệ vào bất cứ nhánh nào rồi phụ thuộc vào thứ tự đánh giá để che nó. Nếu giá trị nguy hiểm đến từ dữ liệu, hãy **đưa điều kiện an toàn vào chính toán hạng** của phép tính như mục `NULLIF` bên dưới.

### 5.1. CASE không thay thế việc kiểm tra kiểu

Ví dụ:

~~~sql
-- PostgreSQL có thể từ chối ngay vì kiểu nhánh không tương thích.
SELECT CASE
    WHEN TRUE THEN 100
    ELSE 'khong_phai_so'
END;
~~~

PostgreSQL cần xác định **một kiểu kết quả chung** cho biểu thức `CASE`. Ở ví dụ này, literal không rõ kiểu `'khong_phai_so'` có thể bị cố ép sang kiểu số và gây lỗi, dù điều kiện `WHEN TRUE` trông như luôn chọn nhánh `100`.

Dạng phù hợp hơn là thống nhất ý định kiểu:

~~~sql
-- Muốn kết quả kiểu text:
SELECT CASE
    WHEN TRUE THEN CAST(100 AS TEXT)
    ELSE 'khong_phai_so'
END AS display_value;
~~~

Hoặc, nếu cột cần là số, dùng `NULL`/giá trị số phù hợp cho các trường hợp không áp dụng rồi định dạng nhãn ở lớp hiển thị:

~~~sql
SELECT CASE
    WHEN TRUE THEN 100
    ELSE NULL
END AS numeric_value;
~~~

**Điểm mấu chốt:** `CASE` quyết định giá trị dựa trên điều kiện; nó **không miễn trừ** quy tắc phân tích kiểu và không bảo đảm che một nhánh có cú pháp hoặc kiểu không hợp lệ.

## 6. Giới hạn thứ hai: hàm tổng hợp có thể được tính trước CASE bao ngoài

Đây là ví dụ quan trọng trong truy vấn báo cáo. Giả sử muốn lấy giá trị chia lớn nhất của các hàng, nhưng khi có mẫu số bằng 0 thì chỉ trả `NULL`.

Một câu SQL có vẻ hợp lý:

~~~sql
-- KHÔNG AN TOÀN: tổng hợp ở ELSE có thể được đánh giá trước CASE.
SELECT CASE
    WHEN MIN(denominator) = 0 THEN NULL
    ELSE MAX(numerator / denominator)
END AS max_ratio
FROM metrics
WHERE metric_id IN (1, 2);
~~~

Trong dữ liệu được lọc có:

- Hàng 1: `numerator = 100`, `denominator = 20`.
- Hàng 2: `numerator = 70`, `denominator = 0`.

Nhìn vào `WHEN MIN(denominator) = 0`, người viết có thể tưởng nhánh đầu trả `NULL` rồi không cần xử lý `MAX(numerator / denominator)`. Nhưng trong SQL, **đầu vào của các aggregate** như `MAX(numerator / denominator)` thường được tính ở giai đoạn tổng hợp **trước khi** biểu thức `CASE` bên ngoài sử dụng kết quả tổng hợp. Với PostgreSQL, phép chia trong `MAX` có thể gây lỗi trước khi điều kiện `CASE` được áp dụng.

Việc đổi thứ tự nhánh không giải quyết nguyên nhân, vì lỗi nằm ở **biểu thức đầu vào aggregate**. Hãy làm phép chia an toàn **ngay bên trong** aggregate:

~~~sql
SELECT
    MAX(
        numerator / NULLIF(denominator, 0)
    ) AS max_ratio
FROM metrics
WHERE metric_id IN (1, 2);
-- 5 (hàng có denominator = 0 trở thành NULL và MAX bỏ qua NULL)
~~~

Hoặc viết điều kiện cho **từng hàng trước khi đưa vào aggregate**:

~~~sql
SELECT
    MAX(
        CASE
            WHEN denominator <> 0
                THEN numerator / denominator
            ELSE NULL
        END
    ) AS max_ratio
FROM metrics
WHERE metric_id IN (1, 2);
-- 5
~~~

Hai cách này có ngữ nghĩa **bỏ qua các tỷ số không xác định** vì `MAX` thường bỏ qua giá trị `NULL`. Nếu quy tắc nghiệp vụ lại yêu cầu **cả nhóm là không hợp lệ khi có bất kỳ mẫu số bằng 0**, cần tách điều kiện nhóm và vẫn bảo vệ biểu thức đầu vào aggregate:

~~~sql
SELECT
    CASE
        WHEN COUNT(*) FILTER (WHERE denominator = 0) > 0
            THEN NULL
        ELSE MAX(numerator / NULLIF(denominator, 0))
    END AS max_ratio
FROM metrics
WHERE metric_id IN (1, 2);
-- NULL vì nhóm có denominator = 0.
~~~

`FILTER (WHERE ...)` là cú pháp được PostgreSQL hỗ trợ; nếu DBMS không hỗ trợ, có thể dùng tổng hợp có điều kiện như `SUM(CASE WHEN denominator = 0 THEN 1 ELSE 0 END)` theo ngữ nghĩa mong muốn.

**Nhớ kỹ:** `CASE` bao ngoài một aggregate **không đảm bảo bảo vệ** phép tính nguy hiểm bên trong aggregate. Cách chắc chắn hơn là làm cho **đối số của aggregate** an toàn trước.

## 7. Mẫu an toàn cơ bản: NULLIF trong phép chia

### 7.1. NULLIF hoạt động như thế nào?

`NULLIF(a, b)` trả:

- `NULL` nếu `a = b` là `TRUE`.
- Giá trị `a` trong trường hợp còn lại.

Vì vậy:

~~~sql
SELECT
    NULLIF(0, 0) AS a,     -- NULL
    NULLIF(5, 0) AS b,     -- 5
    NULLIF(NULL, 0) AS c; -- NULL
~~~

Khi đặt `NULLIF(denominator, 0)` vào **mẫu số**, các hàng có mẫu số bằng 0 trở thành phép chia với `NULL`, mà trong SQL thông thường cho kết quả `NULL` thay vì lỗi chia cho 0:

~~~sql
SELECT
    metric_id,
    numerator / NULLIF(denominator, 0) AS ratio
FROM metrics
ORDER BY metric_id;
~~~

Mẫu này thường **ngắn hơn và bền vững hơn** việc phụ thuộc vào `CASE` bao bên ngoài phép chia. Nó đặt sự bảo vệ **ngay tại chỗ có nguy cơ lỗi**:

~~~text
numerator / denominator              -- Có thể chia cho 0
             |
             v
numerator / NULLIF(denominator, 0)   -- Mẫu số 0 => NULL
~~~

Nếu `denominator` vốn đã `NULL`, `NULLIF` cũng trả `NULL` và phép chia có kết quả `NULL`.

### 7.2. Không tùy tiện thay NULL bằng 0

Một mẫu thường thấy:

~~~sql
SELECT
    metric_id,
    COALESCE(numerator / NULLIF(denominator, 0), 0) AS ratio
FROM metrics;
~~~

Câu này không gây lỗi chia cho 0 trong ví dụ, nhưng **thay kết quả không xác định bằng 0**. Cần hỏi:

- “Tỷ số thực sự bằng 0” có cùng ý nghĩa với “không thể tính tỷ số” không?
- Báo cáo có coi hàng này là lỗi dữ liệu, thiếu dữ liệu hoặc được phép là 0?
- Việc thay `NULL` bằng 0 có làm sai trung bình, tổng hợp hoặc tỷ lệ thống kê không?

Trong dữ liệu mẫu, hàng 5 có tỷ số hợp lệ là `0 / -10 = 0`. Hàng 2 có `70 / 0`, không định nghĩa. Nếu cả hai thành `0`, thông tin khác biệt đã bị mất.

Nếu nghiệp vụ cần phân biệt trạng thái, có thể trả cả cột giá trị và cột nguyên nhân:

~~~sql
SELECT
    metric_id,
    numerator / NULLIF(denominator, 0) AS ratio,
    CASE
        WHEN numerator IS NULL THEN 'MISSING_NUMERATOR'
        WHEN denominator IS NULL THEN 'MISSING_DENOMINATOR'
        WHEN denominator = 0 THEN 'ZERO_DENOMINATOR'
        ELSE 'VALID'
    END AS ratio_status
FROM metrics
ORDER BY metric_id;
~~~

Ở đây `CASE` dùng đúng vai trò **phân loại nghiệp vụ**, còn phép chia được bảo vệ bằng `NULLIF` ở nơi thực hiện.

### 7.3. Kiểu dữ liệu và phép chia số nguyên

Một biểu thức không bị lỗi vẫn có thể **sai về độ chính xác**:

~~~sql
-- Tùy DBMS và kiểu dữ liệu: có thể là phép chia số nguyên.
SELECT 1 / 2 AS ratio;
~~~

Trên nhiều DBMS, phép chia hai số nguyên có thể trả kết quả số nguyên; hệ khác có quy tắc chuyển kiểu riêng. Khi cần tỷ số thập phân, ép kiểu có chủ đích:

~~~sql
SELECT
    CAST(1 AS NUMERIC(12, 4)) / NULLIF(2, 0) AS ratio;
-- 0.5 ở những hệ hỗ trợ NUMERIC theo cách thông thường.
~~~

Nếu dùng cột `NUMERIC` như ví dụ thì tỷ số có kiểu số thập phân phù hợp hơn. Đối với tiền hoặc các tỷ lệ có yêu cầu làm tròn, còn cần xác định precision/scale, giới hạn tràn số và thời điểm làm tròn theo nghiệp vụ.

`NULLIF` bảo vệ **mẫu số bằng 0**, nhưng không tự xử lý tràn số, lỗi ép kiểu, phép chia với dữ liệu phi số hoặc những ràng buộc miền giá trị khác.

## 8. Giới hạn thứ ba: không thể tin thứ tự đánh giá của AND/OR

Trong một ngôn ngữ lập trình như Java, có thể dựa vào quy tắc short-circuit của `&&` và `||`. SQL khác ở chỗ bộ tối ưu thường được phép thay đổi cách đánh giá điều kiện để thực thi hiệu quả mà vẫn giữ ngữ nghĩa logic.

Xem một cột văn bản cần chuyển sang số:

~~~sql
-- KHÔNG AN TOÀN nếu raw_rate có 'abc' hay 'N/A':
SELECT
    metric_id,
    CAST(raw_rate AS NUMERIC) AS rate
FROM metrics
WHERE raw_rate <> 'N/A'
  AND CAST(raw_rate AS NUMERIC) > 10;
~~~

Người viết có thể nghĩ điều kiện thứ nhất luôn loại `'N/A'` rồi phép `CAST` mới chạy. Nhưng:

- Vẫn còn `'abc'`, bản thân điều kiện thứ nhất đã không đủ lọc dữ liệu xấu.
- Kể cả có một điều kiện lọc regex/giá trị hợp lệ chính xác hơn, **thứ tự đánh giá hai vế `AND` trong `WHERE` không phải bảo đảm vận hành** trên mọi DBMS hoặc kế hoạch.
- Bộ tối ưu có thể đẩy, gộp hoặc sắp xếp lại biểu thức để tối ưu truy vấn.

Một biến thể khác vẫn không nên coi là đủ an toàn:

~~~sql
-- Đừng dựa vào việc regex chắc chắn chạy trước CAST.
WHERE raw_rate ~ '^[0-9]+(\.[0-9]+)?$'
  AND CAST(raw_rate AS NUMERIC) > 10
~~~

Toán tử `~` ở ví dụ là regex đặc thù PostgreSQL. Đúng về **mặt ý tưởng lọc định dạng** nhưng không tạo cam kết `CAST` chỉ chạy sau regex. Ngoài ra, regex hợp lệ về ký tự chưa chắc chứng minh giá trị nằm trong phạm vi số mà kiểu đích cho phép.

**Nguyên tắc:** không dùng `AND`/`OR` để ép DBMS thực hiện phép kiểm tra an toàn theo một lịch chạy vật lý được người viết tưởng tượng ra.

### 8.1. Bảo vệ ngay trong biểu thức chuyển kiểu

Nếu DBMS có chức năng **thử chuyển đổi mà không gây lỗi**, nên cân nhắc dùng nó:

~~~sql
-- SQL Server:
SELECT
    metric_id,
    TRY_CONVERT(decimal(12, 2), raw_rate) AS parsed_rate
FROM metrics;
~~~

~~~sql
-- BigQuery:
SELECT
    metric_id,
    SAFE_CAST(raw_rate AS NUMERIC) AS parsed_rate
FROM metrics;
~~~

~~~sql
-- Các hệ có TRY_CAST, ví dụ một số phiên bản/hệ như DuckDB, Trino:
SELECT
    metric_id,
    TRY_CAST(raw_rate AS DECIMAL(12, 2)) AS parsed_rate
FROM metrics;
~~~

Những hàm này có **phạm vi hỗ trợ và quy tắc lỗi khác nhau**, không phải mọi DBMS đều có cùng tên/cú pháp. Ví dụ `TRY_CONVERT`/`TRY_CAST` của SQL Server không bảo đảm mọi cặp kiểu bị cấm tường minh đều biến thành `NULL`; cần đọc tài liệu dialect và kiểm thử trường hợp thật.

Nếu hệ không có safe cast, có thể:

1. **Chuẩn hóa và kiểm tra dữ liệu trước khi lưu vào cột số**.
2. Dùng một biểu thức `CASE` kiểm tra định dạng và giới hạn phù hợp **trước khi tính phép chuyển kiểu trên giá trị biến theo từng hàng**, đồng thời nhớ các giới hạn đánh giá đã nêu.
3. Chuyển đổi trong tầng ứng dụng có bộ parse và cơ chế trả lỗi rõ ràng.
4. Tách dữ liệu thô/không hợp lệ vào bảng staging, rồi chỉ đưa các giá trị đã kiểm tra sang cột có kiểu số.

Ví dụ PostgreSQL với phạm vi decimal được kiểm soát trong dữ liệu mẫu:

~~~sql
SELECT
    metric_id,
    raw_rate,
    CASE
        WHEN raw_rate ~ '^[0-9]{1,8}(\.[0-9]{1,2})?$'
            THEN CAST(raw_rate AS NUMERIC(10, 2))
        ELSE NULL
    END AS parsed_rate
FROM metrics
ORDER BY metric_id;
~~~

Mẫu regex ở đây chỉ chấp nhận **tối đa tám chữ số trước dấu chấm** và hai chữ số sau dấu chấm, không nhận số âm hay ký hiệu khoa học. Nó phù hợp **với hợp đồng nhập liệu hạn chế của ví dụ**, không phải bộ parser số phổ quát. Nếu nghiệp vụ cho phép dấu âm, dấu phân tách hàng nghìn, exponent hoặc khoảng trắng, quy tắc cần được thiết kế lại.

Với dữ liệu mẫu, `'12.50'` và `'8.0'` được chuyển thành số; `'N/A'` và `'abc'` cho `NULL`; chuỗi `'1000000000'` không hợp đồng vì dài hơn tám chữ số. Cần quyết định có muốn đánh dấu riêng lý do không hợp lệ thay vì gộp tất cả thành `NULL`.

### 8.2. CTE hoặc subquery không tự là hàng rào đánh giá

Có người thử viết:

~~~sql
WITH valid_rows AS (
    SELECT *
    FROM metrics
    WHERE raw_rate ~ '^[0-9]+(\.[0-9]+)?$'
)
SELECT CAST(raw_rate AS NUMERIC)
FROM valid_rows;
~~~

Về mặt biểu diễn logic, câu này có vẻ “lọc trước, chuyển kiểu sau”. Tuy nhiên, **CTE, view hoặc derived table không tự bảo đảm** kế hoạch thực thi tuần tự như việc chạy hai câu lệnh riêng. DBMS có thể gộp truy vấn con, đẩy điều kiện và biến đổi kế hoạch; mức vật chất hóa CTE tùy DBMS và phiên bản.

Trong PostgreSQL, `WITH ... MATERIALIZED` ở những phiên bản hỗ trợ có thể ảnh hưởng cách materialize và tối ưu CTE, nhưng đó là một công cụ kế hoạch cụ thể, không phải cách xử lý lỗi thay cho việc đảm bảo đầu vào hợp lệ. Nên chọn biểu thức an toàn, cột dữ liệu đúng kiểu hoặc quy trình validation độc lập theo yêu cầu của hệ thống.

## 9. Giới hạn thứ tư: lỗi miền giá trị của hàm toán học

Không phải mọi lỗi đến từ phép chia. Hàm toán học có thể yêu cầu toán hạng thuộc một miền nhất định:

- `SQRT(x)` cần `x >= 0` với kiểu số thực thông thường.
- `LN(x)` hoặc `LOG(x)` thường cần `x > 0`.
- Phép lũy thừa, chuyển đổi kiểu và số học có thể gây tràn số tùy kiểu/kích thước.

Với dữ liệu mẫu, `score` của hàng 3 là `-2`; `SQRT(-2)` trong PostgreSQL gây lỗi miền số.

### 9.1. CASE để tạo đối số an toàn

~~~sql
SELECT
    metric_id,
    SQRT(
        CASE
            WHEN score >= 0 THEN score
            ELSE NULL
        END
    ) AS root_score
FROM metrics
ORDER BY metric_id;
~~~

Thay vì để một hàm `SQRT` nguy hiểm ở nhánh kết quả của `CASE`, ví dụ này làm cho **đầu vào đưa vào `SQRT`** chỉ là giá trị không âm hoặc `NULL`. Hàm `SQRT(NULL)` cho `NULL` trong PostgreSQL; không phải xử lý số âm.

Dạng tương tự cho logarithm:

~~~sql
SELECT
    metric_id,
    LN(
        CASE
            WHEN score > 0 THEN score
            ELSE NULL
        END
    ) AS ln_score
FROM metrics
ORDER BY metric_id;
~~~

Nếu yêu cầu nghiệp vụ khác, ví dụ mọi điểm âm phải là `0` trước khi lấy căn, thay vì trả `NULL`, bạn cần quy định tường minh; không tự đưa số âm về `0` chỉ để tránh lỗi, vì điều đó biến **dữ liệu không hợp lệ** thành một giá trị hợp lệ giả.

### 9.2. CASE thường có ích nhưng không xử lý mọi lỗi kiểu số

Một câu như:

~~~sql
CASE
    WHEN score >= 0 THEN SQRT(score)
    ELSE NULL
END
~~~

là mẫu rẽ nhánh theo hàng dễ đọc, có thể hoạt động tốt trong ví dụ. Tuy nhiên, nếu phép tính bị **đẩy lên cấp aggregate**, có **hằng số gây lỗi tại planning**, hoặc trong một DBMS có quy tắc đánh giá khác, người viết không thể mở rộng kết luận một cách máy móc.

Ngay cả khi không có lỗi miền, giá trị rất lớn cũng có thể gây **tràn số** trong phép nhân, cộng hoặc ép kiểu. Kiểm tra số dương chưa chứng minh mọi phép toán khác đều an toàn. Cần thiết kế kiểu số phù hợp và kiểm tra phạm vi trên dữ liệu thật.

## 10. CASE bên ngoài không bảo đảm biểu thức bên trong các lớp khác

Một số ví dụ để định vị “lỗi nằm ở đâu”:

| Cách viết | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| `CASE WHEN denominator = 0 THEN NULL ELSE numerator / denominator END` | Thường phù hợp cho phép chia từng hàng, nhưng không phải quy tắc bảo vệ mọi kế hoạch/biểu thức khác | Có thể dùng `numerator / NULLIF(denominator, 0)` |
| `CASE WHEN MIN(denominator) = 0 THEN NULL ELSE MAX(numerator / denominator) END` | Aggregate có thể tính đầu vào phép chia trước `CASE` | `MAX(numerator / NULLIF(denominator, 0))`, sau đó áp dụng quy tắc nhóm |
| `WHERE text_is_valid AND CAST(text AS NUMERIC) > 10` | Không có bảo đảm thứ tự đánh giá điều kiện | Safe cast hoặc chuẩn hóa dữ liệu trước |
| `CASE WHEN TRUE THEN 1 ELSE 1/0 END` | Hằng số có thể được xử lý sớm lúc lập kế hoạch | Không đặt biểu thức luôn sai vào query |
| `CASE WHEN TRUE THEN 1 ELSE 'abc' END` | Các nhánh cần kiểu kết quả tương thích | `CAST` tường minh hoặc cùng kiểu |
| `CASE WHEN condition THEN some_function() END` | Hàm tùy DBMS có thể có side effect, lỗi, tác động tối ưu | Không dùng biểu thức khai báo để điều khiển thứ tự side effect |

### 10.1. Hàm do người dùng định nghĩa và tác dụng phụ

SQL khai báo “**cần tính giá trị gì**”, không phải môi trường đáng tin cậy để điều khiển chính xác số lần gọi các hàm có tác dụng phụ. DBMS có thể bỏ qua tính toán không cần thiết, tái sử dụng, đẩy vào kế hoạch hoặc đánh giá biểu thức theo quy tắc của nó.

Ví dụ một hàm do ứng dụng tự tạo gửi thông báo, ghi log, gọi API hoặc làm thay đổi trạng thái không nên được bảo vệ bằng ý tưởng “đặt nó trong nhánh `CASE` ít khi đúng thì chắc sẽ gọi đúng một lần”. Mức hỗ trợ và tính chất volatile/stable/immutable của UDF phụ thuộc DBMS và cách khai báo.

Nếu nghiệp vụ cần **thứ tự bước có side effect**, hãy dùng transaction, stored procedure/lệnh tuần tự với hợp đồng rõ ràng hoặc tầng ứng dụng, thay vì suy đoán thứ tự gọi từ biểu thức SQL.

## 11. Thiết kế phép tổng hợp khi có hàng không hợp lệ

### 11.1. Phân biệt “trung bình các tỷ số” với “tỷ số của tổng”

Hai công thức khác nhau về toán học:

~~~sql
-- Trung bình các tỷ số từng hàng hợp lệ:
SELECT
    AVG(numerator / NULLIF(denominator, 0)) AS avg_row_ratio
FROM metrics;
~~~

~~~sql
-- Tỷ số giữa tổng tử và tổng mẫu:
SELECT
    SUM(numerator) / NULLIF(SUM(denominator), 0) AS ratio_of_sums
FROM metrics;
~~~

Hai phép tính **không đồng nghĩa**. `AVG` bỏ qua các giá trị `NULL` (tức là bỏ các hàng không tính được tỷ số theo biểu thức). Trong tỷ số của tổng, `SUM` thường bỏ qua `NULL` ở từng cột độc lập; nếu không kiểm soát quy tắc loại hàng, tử và mẫu có thể đang cộng trên **hai tập hàng khác nhau**.

Để tỷ số của tổng chỉ dùng hàng mà cả tử và mẫu đều hợp lệ, có thể xác định điều kiện chung:

~~~sql
SELECT
    SUM(
        CASE
            WHEN numerator IS NOT NULL
             AND denominator IS NOT NULL
             AND denominator <> 0
                THEN numerator
            ELSE NULL
        END
    )
    /
    NULLIF(
        SUM(
            CASE
                WHEN numerator IS NOT NULL
                 AND denominator IS NOT NULL
                 AND denominator <> 0
                    THEN denominator
                ELSE NULL
            END
        ),
        0
    ) AS ratio_of_valid_sums
FROM metrics;
~~~

Câu SQL minh họa cách điều khiển **tập hàng tham gia** và vẫn bảo vệ mẫu số tổng. Trong nghiệp vụ thật, cần quyết định có cho phép mẫu âm hay không, có cho phép mẫu bằng 0 ở từng hàng nhưng tổng không bằng 0 hay không, và kết quả khi không có hàng hợp lệ được biểu diễn như thế nào.

### 11.2. Hàm cửa sổ và biểu thức trước/sau tổng hợp

Các biểu thức cửa sổ (`OVER`), aggregate và `CASE` có quy tắc phạm vi riêng. Ví dụ tính tỷ lệ giá trị của một hàng trên tổng cùng nhóm:

~~~sql
SELECT
    metric_id,
    numerator,
    numerator
    /
    NULLIF(SUM(numerator) OVER (), 0) AS share_of_total
FROM metrics
ORDER BY metric_id;
~~~

`NULLIF` được đặt **ngay ở mẫu số là kết quả cửa sổ**, tránh trường hợp tổng bằng 0. Nếu đặt `CASE` bao ngoài với một điều kiện khác rồi để phép chia `numerator / SUM(...) OVER ()` ở một nhánh, bạn cần hiểu rõ hệ thực thi và nghiệp vụ; việc bảo vệ trực tiếp tại mẫu số thường diễn đạt ý định hơn.

Đặt `CASE` **trong đối số** của aggregate hoặc hàm cửa sổ là một cách hợp lý để tạo dữ liệu đầu vào có điều kiện. Ngược lại, để một phép tính rủi ro nằm trong aggregate rồi chỉ kiểm tra **sau khi tổng hợp xong** là kiểu lỗi mà mục 6 cảnh báo.

## 12. CASE và rẽ nhánh nghiệp vụ: dùng đúng chỗ

`CASE` vẫn rất hữu ích, không phải một tính năng “không an toàn”. Vấn đề là **suy diễn quá mức về thứ tự đánh giá**.

Ví dụ phân loại tình trạng của từng hàng:

~~~sql
SELECT
    metric_id,
    CASE
        WHEN numerator IS NULL THEN 'THIEU_TU_SO'
        WHEN denominator IS NULL THEN 'THIEU_MAU_SO'
        WHEN denominator = 0 THEN 'MAU_SO_BANG_0'
        WHEN denominator < 0 THEN 'MAU_SO_AM'
        ELSE 'HOP_LE'
    END AS calculation_status,
    numerator / NULLIF(denominator, 0) AS raw_ratio
FROM metrics
ORDER BY metric_id;
~~~

Trong ví dụ này, `CASE` quyết định **nhãn trạng thái**; phép chia được bảo vệ trực tiếp bằng `NULLIF`. Còn việc cho phép phép chia với mẫu âm hay không được tách thành **quy tắc nghiệp vụ** thay vì bị giấu trong phép tính.

Nếu muốn `raw_ratio` chỉ có giá trị khi `denominator > 0`, có thể viết:

~~~sql
SELECT
    metric_id,
    CASE
        WHEN numerator IS NOT NULL
         AND denominator > 0
            THEN numerator / NULLIF(denominator, 0)
        ELSE NULL
    END AS accepted_ratio
FROM metrics
ORDER BY metric_id;
~~~

`NULLIF` vẫn giúp phép chia an toàn ngay tại chỗ, trong khi `CASE` biểu thị quy tắc “chỉ chấp nhận mẫu số dương”. Khi mẫu số âm, kết quả là `NULL` vì **nghiệp vụ không chấp nhận**, không phải vì phép chia âm tự nó là lỗi SQL.

### 12.1. CASE trong ORDER BY

Một ví dụ thuần rẽ nhánh, không liên quan đến che lỗi:

~~~sql
SELECT metric_id, metric_name, denominator
FROM metrics
ORDER BY
    CASE
        WHEN denominator IS NULL THEN 2
        WHEN denominator = 0 THEN 1
        ELSE 0
    END,
    metric_id;
~~~

Truy vấn xếp nhóm mẫu số hợp lệ trước, mẫu số 0 tiếp theo và thiếu mẫu số cuối cùng. `CASE` ở đây xác định **khóa sắp xếp nghiệp vụ**; nó không điều khiển thứ tự vật lý đánh giá tất cả biểu thức trong truy vấn.

### 12.2. CASE trong UPDATE

~~~sql
UPDATE metrics
SET raw_rate = CASE
    WHEN raw_rate IS NULL THEN 'MISSING'
    ELSE raw_rate
END
WHERE metric_id = 5;
~~~

`CASE` biểu đạt giá trị mới cần ghi theo điều kiện. Đây là thao tác **thay đổi dữ liệu**; cần điều kiện `WHERE` chính xác, transaction phù hợp và hiểu tác động trước khi chạy trên môi trường thật. Nếu `raw_rate` được dùng cho phép chuyển số, việc ghi chuỗi `'MISSING'` vào cùng cột có thể khiến việc chuyển kiểu sau này phức tạp hơn; đây chỉ là ví dụ cú pháp, không phải đề xuất schema tối ưu.

## 13. Những khác biệt DBMS cần biết

| Chủ đề | PostgreSQL | SQL Server | MySQL / MariaDB | SQLite |
| --- | --- | --- | --- | --- |
| `CASE` | Hỗ trợ, cùng logic ba giá trị; có giới hạn constant folding và aggregate | Hỗ trợ; tài liệu cảnh báo biểu thức aggregate trong `WHEN` có thể được đánh giá trước `CASE` | Hỗ trợ; xử lý lỗi và chuyển kiểu phụ thuộc SQL mode/ngữ cảnh | Hỗ trợ; kiểu dữ liệu động và quy tắc chuyển kiểu khác |
| Phép chia cho 0 | Thường báo lỗi | Thường báo lỗi hoặc xử lý theo thiết lập phiên/biểu thức | Kết quả lỗi/cảnh báo/`NULL` có thể phụ thuộc SQL mode và ngữ cảnh `SELECT`/DML | Phép chia cho 0 thường trả `NULL` |
| `NULLIF(a, b)` | Có | Có | Có | Có |
| Chuyển kiểu an toàn | Không có cùng một `TRY_CAST` phổ quát trong SQL lõi PostgreSQL | `TRY_CAST` / `TRY_CONVERT` trong phạm vi hỗ trợ | Quy tắc chuyển đổi riêng, kiểm tra tùy mode/hàm | Ép kiểu động có thể không báo lỗi giống hệ strict |
| Regex | Toán tử `~` | Cú pháp khác, phiên bản có hỗ trợ riêng | `REGEXP` hoặc chức năng regex | Không mặc định có engine `REGEXP` đầy đủ |
| CTE/materialization | Có cơ chế inlining/materialization tùy phiên bản và cú pháp | CTE thường là biểu thức truy vấn, không mặc định lưu vật lý | Tùy optimizer/phiên bản | Tùy kế hoạch và hint materialization |

Điều quan trọng không phải ghi nhớ mọi nhánh dialect. Khi viết SQL dùng nhiều hệ, hãy kiểm tra:

- **Kiểu đích** của phép tính và chuyển đổi.
- Quy tắc lỗi cho phép chia, ép kiểu, phép toán miền giá trị.
- Hỗ trợ `TRY_CAST`/`SAFE_CAST` hoặc kỹ thuật thay thế.
- Điều kiện nào được phép tối ưu/đẩy vào kế hoạch.
- Đơn vị kiểm thử: dữ liệu hợp lệ, `NULL`, số 0, dữ liệu sai kiểu, giá trị ngoài phạm vi và quy mô lớn.

Không kết luận một truy vấn “an toàn đa hệ” chỉ vì nó chạy thành công trên vài hàng ở một DBMS.

## 14. Phương pháp thiết kế biểu thức an toàn

Khi gặp yêu cầu “dùng `CASE` để tránh lỗi”, có thể làm theo trình tự suy luận sau.

### Bước 1 — Xác định phép tính thực sự có thể lỗi

| Phép tính | Điều kiện nguy hiểm | Kết quả an toàn cần quyết định |
| --- | --- | --- |
| `a / b` | `b = 0` | `NULL`, bỏ hàng, hay báo lỗi nghiệp vụ? |
| `CAST(text AS NUMERIC)` | Text không hợp lệ hoặc ngoài phạm vi | `NULL`, trạng thái lỗi, hay từ chối dữ liệu? |
| `SQRT(x)` | `x < 0` | `NULL` hay xử lý miền giá trị khác? |
| `LN(x)` | `x <= 0` | `NULL` hay đánh dấu không hợp lệ? |
| `a * b` với kiểu giới hạn | Tràn phạm vi số | Kiểu rộng hơn, kiểm tra phạm vi hay loại dữ liệu? |
| Hàm tự định nghĩa | Lỗi nghiệp vụ / side effect | Thay đổi thiết kế để không phụ thuộc short-circuit |

### Bước 2 — Bảo vệ tại toán hạng hoặc nơi tạo dữ liệu

Ví dụ:

~~~sql
numerator / NULLIF(denominator, 0)
~~~

~~~sql
SQRT(CASE WHEN score >= 0 THEN score ELSE NULL END)
~~~

~~~sql
-- Theo dialect hỗ trợ:
TRY_CAST(raw_rate AS DECIMAL(12, 2))
~~~

Đưa dữ liệu không hợp lệ thành một trạng thái có ý nghĩa **trước khi phép tính không thể xử lý nó**. Nếu trạng thái đó là `NULL`, xem kỹ phép toán phía sau có xử lý `NULL` đúng theo mục đích hay không.

### Bước 3 — Đặt CASE ở tầng biểu đạt nghiệp vụ

Ví dụ tách nhãn lỗi khỏi giá trị:

~~~sql
SELECT
    metric_id,
    CASE
        WHEN denominator = 0 THEN 'ZERO_DENOMINATOR'
        WHEN denominator IS NULL THEN 'MISSING_DENOMINATOR'
        ELSE 'OK'
    END AS status,
    numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
~~~

Cách này dễ đọc, dễ đo lường tỷ lệ lỗi dữ liệu và ít gắn thành công của phép tính vào một giả định về thứ tự đánh giá.

### Bước 4 — Xác định giai đoạn aggregate/window và ranh giới truy vấn

Nếu biểu thức rủi ro xuất hiện **bên trong `SUM`, `AVG`, `MAX` hoặc hàm cửa sổ**, phải bảo vệ **bên trong đối số hoặc mẫu số của phép tính**. Một `CASE` đặt bên ngoài là nơi xử lý **kết quả** của giai đoạn đó, không phải hàng rào chắc chắn cho mọi phép tính ở giai đoạn trước.

### Bước 5 — Xử lý lỗi dữ liệu ở đúng nơi

Một hệ thống có thể chấp nhận `NULL` khi không tính được tỷ số. Hệ khác có thể yêu cầu **từ chối** bản ghi với denominator bằng 0, ghi lỗi kiểm tra và ngăn không cho dữ liệu vào bảng chính. Với dữ liệu bên ngoài, staging và validation ở bước nhập thường dễ kiểm soát hơn viết mỗi báo cáo một kiểu che lỗi.

Không dùng `COALESCE(..., 0)` để làm sạch báo cáo nếu việc đó khiến dữ liệu sai được hiểu thành số hợp lệ.

## 15. Những ngộ nhận thường gặp

| Ngộ nhận | Phân tích |
| --- | --- |
| “`CASE` luôn giống `if/else` của Java, không bao giờ đụng nhánh không chọn.” | SQL có tối ưu hằng số, kiểm tra kiểu và các giai đoạn tổng hợp; không thể suy ra cam kết thực thi vật lý tổng quát. |
| “Đặt `MAX(1/x)` trong nhánh `ELSE` là đủ tránh chia cho 0.” | Đầu vào aggregate có thể được tính trước `CASE` bao ngoài. |
| “Viết `WHERE x <> 0 AND 1/x > 10` chắc chắn an toàn.” | Không nên dựa vào thứ tự đánh giá `AND`; dùng `1 / NULLIF(x, 0)` ở nơi phép chia xảy ra. |
| “`COALESCE(1 / x, 0)` tự tránh lỗi chia cho 0.” | Phép chia là đối số cần được tính; nếu nó lỗi trước khi tạo `NULL` thì `COALESCE` không xử lý lỗi đó. |
| “`NULLIF` sửa mọi lỗi toán học.” | Nó chỉ giải quyết so sánh bằng một giá trị cần thay `NULL`; không giải quyết cast lỗi, overflow, log âm… |
| “Một regex lọc xong là mọi chuỗi đều cast được.” | Regex phải khớp kiểu, giới hạn phạm vi và cách hiểu định dạng; không bảo đảm thứ tự đánh giá khi đặt ở vế `AND` riêng. |
| “Một CTE là hàng rào khiến phần trong luôn chạy xong trước phần ngoài.” | Optimizer có thể inline/biến đổi; materialization phụ thuộc DBMS và cú pháp. |
| “`CASE` trả `NULL` cho lỗi nghĩa là dữ liệu giờ đã đúng.” | `NULL` chỉ là cách biểu đạt không có kết quả; cần quy tắc và theo dõi lỗi dữ liệu. |
| “Khi `CASE` đã chọn giá trị, không cần quan tâm kiểu các nhánh khác.” | Kiểu kết quả chung được xác định trong quá trình phân tích SQL. |
| “Một truy vấn chạy trên SQLite có chia 0 trả `NULL` thì chắc chạy giống PostgreSQL.” | DBMS có quy tắc lỗi/kiểu khác nhau. |

## 16. Bài tập thực hành

Các bài dùng bảng `metrics` ở mục 3. Với những câu SQL được đánh dấu **không an toàn**, hãy đọc để hiểu lỗi; không dùng trong mã production.

### Bài 1 — Chia an toàn

Viết truy vấn trả `metric_id` và `ratio = numerator / denominator`, nhưng khi denominator bằng 0 hoặc `NULL` thì `ratio` là `NULL`.

**Đáp án:**

~~~sql
SELECT
    metric_id,
    numerator / NULLIF(denominator, 0) AS ratio
FROM metrics
ORDER BY metric_id;
~~~

Kết quả hàng 1 là `5`, hàng 2 là `NULL`, hàng 3 và 4 là `NULL`, hàng 5 là `0`, hàng 6 là `6`. Hàng 3 thiếu tử số, hàng 4 thiếu mẫu số.

### Bài 2 — Tìm lỗi aggregate

Đoạn SQL sau có thể gây lỗi ở đâu?

~~~sql
SELECT CASE
    WHEN MIN(denominator) = 0 THEN NULL
    ELSE MAX(numerator / denominator)
END
FROM metrics
WHERE metric_id IN (1, 2);
~~~

**Đáp án:** biểu thức `numerator / denominator` là **đầu vào của aggregate `MAX`**, có thể được tính trước `CASE` bao ngoài; hàng 2 có mẫu bằng 0. Sửa bằng `MAX(numerator / NULLIF(denominator, 0))` và xác định nghiệp vụ có muốn trả `NULL` cho toàn nhóm khi tồn tại mẫu 0 hay muốn bỏ riêng hàng không hợp lệ.

### Bài 3 — Vì sao COALESCE chưa đủ?

Phân tích:

~~~sql
SELECT
    COALESCE(numerator / denominator, 0)
FROM metrics;
~~~

**Đáp án:** `COALESCE` chỉ thay giá trị `NULL` được tạo ra; nó không phải công cụ bắt lỗi chia cho 0 trong `numerator / denominator`. Phải viết `COALESCE(numerator / NULLIF(denominator, 0), 0)` nếu nghiệp vụ thật sự muốn thay kết quả không xác định bằng 0.

### Bài 4 — Đưa kiểm tra vào đối số hàm toán học

Tạo cột `safe_root` bằng căn bậc hai của `score` khi không âm; với score âm hoặc `NULL`, trả `NULL`.

**Đáp án:**

~~~sql
SELECT
    metric_id,
    SQRT(
        CASE
            WHEN score >= 0 THEN score
            ELSE NULL
        END
    ) AS safe_root
FROM metrics
ORDER BY metric_id;
~~~

Giá trị `score` của hàng 3 là `-2` nên kết quả `safe_root` bằng `NULL`, không chạy phép `SQRT(-2)`. Với score `0`, căn là `0` hợp lệ.

### Bài 5 — Chọn giữa CASE và safe cast

Cột `raw_rate` có các giá trị như `'12.50'`, `'N/A'`, `'abc'` và `NULL`. Một truy vấn cần lọc các giá trị có thể chuyển thành số lớn hơn 10. Vì sao mẫu `WHERE raw_rate ~ 'regex' AND CAST(raw_rate AS NUMERIC) > 10` chưa là bảo đảm di động?

**Đáp án:** thứ tự đánh giá `AND` không phải hợp đồng cho mọi DBMS/kế hoạch; regex còn phải kiểm soát phạm vi kiểu số. Ở DBMS hỗ trợ phép chuyển đổi an toàn, có thể áp dụng `TRY_CONVERT`/`TRY_CAST`/`SAFE_CAST` tương ứng rồi so sánh kết quả số. Nếu không, cần validation với miền dữ liệu/kiểu rõ ràng ở tầng nhập hoặc biểu thức `CASE` phù hợp.

### Bài 6 — Phân biệt hai cách thống kê

Với hai hàng có các cặp `(numerator, denominator) = (10, 2)` và `(90, 18)`:

~~~sql
SELECT AVG(numerator / NULLIF(denominator, 0)) FROM ...;
SELECT SUM(numerator) / NULLIF(SUM(denominator), 0) FROM ...;
~~~

Hai cách đều cho `5` trong ví dụ này. Hãy đổi cặp thứ hai thành `(90, 30)` và tính lại.

**Đáp án:** trung bình tỷ số hàng là `(10/2 + 90/30) / 2 = (5 + 3)/2 = 4`; tỷ số của tổng là `(10+90)/(2+30) = 100/32 = 3.125`. Hai công thức phục vụ ý nghĩa thống kê khác nhau; `CASE` không quyết định thay bạn nên chọn công thức nào.

### Bài 7 — Thiết kế trạng thái lỗi tường minh

Viết một `SELECT` trả `metric_id`, `ratio` và `ratio_status` theo quy tắc:

- Thiếu tử số → `MISSING_NUMERATOR`.
- Thiếu mẫu số → `MISSING_DENOMINATOR`.
- Mẫu số bằng 0 → `ZERO_DENOMINATOR`.
- Mẫu số âm → `NEGATIVE_DENOMINATOR`.
- Còn lại → `VALID`.

Giá trị `ratio` chỉ được tính khi `ratio_status` là `VALID`.

**Đáp án gợi ý:**

~~~sql
SELECT
    metric_id,
    CASE
        WHEN numerator IS NOT NULL
         AND denominator > 0
            THEN numerator / NULLIF(denominator, 0)
        ELSE NULL
    END AS ratio,
    CASE
        WHEN numerator IS NULL THEN 'MISSING_NUMERATOR'
        WHEN denominator IS NULL THEN 'MISSING_DENOMINATOR'
        WHEN denominator = 0 THEN 'ZERO_DENOMINATOR'
        WHEN denominator < 0 THEN 'NEGATIVE_DENOMINATOR'
        ELSE 'VALID'
    END AS ratio_status
FROM metrics
ORDER BY metric_id;
~~~

Việc kiểm tra theo thứ tự trên làm rõ ưu tiên: nếu cả tử số và mẫu số cùng thiếu, kết quả báo thiếu tử số trước. Nếu nghiệp vụ muốn báo nhiều lỗi cùng lúc, một cột trạng thái đơn có thể chưa đủ; có thể trả danh sách lỗi hoặc nhiều cờ kiểm tra.

### Bài 8 — Nêu một tình huống CASE không bảo vệ được

Hãy giải thích tại sao đoạn sau không phải là cách đáng tin cậy để tránh lỗi:

~~~sql
SELECT CASE
    WHEN 1 = 1 THEN 100
    ELSE 1 / 0
END;
~~~

**Đáp án:** hằng số `1/0` có thể bị bộ tối ưu đánh giá ở **giai đoạn lập kế hoạch**; nguyên tắc lựa chọn nhánh `CASE` khi xử lý giá trị từng hàng không phải cam kết toàn bộ các biểu thức hằng/aggregate chưa từng được xử lý trước đó. Không nên đặt phép tính luôn sai vào query để trông đợi một nhánh khác che nó.

## 17. Ghi nhớ

`CASE` là công cụ tốt để **biểu diễn quy tắc rẽ nhánh và chọn giá trị**. Trong biểu thức đơn giản trên từng hàng, nó thường tránh phải tính giá trị của nhánh không được chọn. Nhưng đừng dùng `CASE` như **cơ chế bắt ngoại lệ** hoặc **hợp đồng thứ tự thực thi** cho mọi biểu thức SQL.

Khi nguy cơ là phép chia cho 0, ưu tiên `numerator / NULLIF(denominator, 0)`. Khi nguy cơ nằm ở đối số của `SQRT`, `LN` hay phép chuyển kiểu, bảo đảm **đối số đưa vào hàm là hợp lệ** hoặc dùng phép chuyển đổi an toàn có hỗ trợ trong DBMS. Với hàm tổng hợp, bảo vệ **biểu thức bên trong aggregate** trước khi dùng `CASE` để diễn đạt quy tắc kết quả. Với dữ liệu văn bản bẩn, kiểm tra/chuẩn hóa theo kiểu và miền giá trị, không giả định `AND` hoặc CTE sẽ chạy theo thứ tự người viết hình dung.

**Cách viết an toàn nhất là đặt điều kiện bảo vệ ngay tại phép tính có thể lỗi, đồng thời giữ ý nghĩa của dữ liệu không hợp lệ thật rõ ràng.**
