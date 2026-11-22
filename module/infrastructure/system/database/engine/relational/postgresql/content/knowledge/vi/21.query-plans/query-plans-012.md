# Extended statistics cho các cột có phụ thuộc trong PostgreSQL

Một câu truy vấn có thể viết đúng SQL, có index phù hợp nhưng PostgreSQL vẫn chọn kế hoạch thực thi không như mong đợi. Một nguyên nhân quan trọng nằm ở **ước lượng số hàng** (*cardinality estimation*): PostgreSQL phải dự đoán có bao nhiêu hàng thỏa điều kiện, bao nhiêu nhóm sau `GROUP BY`, và bao nhiêu hàng được xử lý ở từng bước trước khi thực sự chạy truy vấn.

Khi điều kiện lọc tác động đến nhiều cột có quan hệ với nhau, thống kê của từng cột riêng lẻ có thể không đủ. Ví dụ:

- `category_id = 7` gần như quyết định `category_code = 'CAT-007'`.
- `province_id` và `province_name` có thể biểu diễn cùng một thông tin.
- `district_id` có thể xác định `province_id`, dù chiều ngược lại không đúng.
- Một tổ hợp `country_code</BT> và `currency_code` có thể xuất hiện thường xuyên hơn dự đoán nếu coi hai cột độc lập.

Nếu planner đơn giản nhân xác suất của hai điều kiện, nó có thể dự đoán chỉ **10 hàng**, trong khi thực tế có **1.000 hàng**. Sai số này có thể làm thay đổi quyết định chọn sequential scan, index scan, thứ tự JOIN, hash join, nested loop hoặc phương pháp aggregate.

PostgreSQL cung cấp **extended statistics**, khai báo bằng `CREATE STATISTICS`, để giúp planner hiểu các mối quan hệ **giữa nhiều cột** trong cùng một quan hệ. Trong đó, thống kê **functional dependencies** — `dependencies` — đặc biệt hữu ích cho các cột có quan hệ phụ thuộc về giá trị.

Bài học thuộc chương **Kế hoạch truy vấn**, tập trung vào cách hiểu và sử dụng extended statistics một cách chính xác, từ lý thuyết selectivity đến ví dụ thực hành, metadata, chi phí và giới hạn của planner.

## 1. Vấn đề gốc: planner cần dự đoán số hàng

Khi gặp:

~~~sql
SELECT *
FROM orders
WHERE region_id = 10
  AND region_name = 'North';
~~~

PostgreSQL không thực thi trước mọi phương án rồi mới chọn kế hoạch. Planner dùng thông tin có sẵn, bao gồm:

- Kích thước quan hệ và số trang ước tính.
- Thống kê phân bố của từng cột.
- Tỷ lệ NULL.
- Các giá trị phổ biến (*most common values*, MCV).
- Histogram và số giá trị phân biệt ước tính.
- Indexes có sẵn.
- Thống kê mở rộng giữa nhiều cột nếu được tạo và phân tích.
- Các tham số cost, độ song song và cấu trúc truy vấn.

Một đại lượng trung tâm là **selectivity**: tỷ lệ hàng dự kiến thỏa một điều kiện.

Nếu bảng có 100.000 hàng và điều kiện được ước lượng selectivity 0,01:

\[
\text{estimated rows} \approx 100{,}000 \times 0{,}01 = 1{,}000
\]

Planner dùng con số đó ở nhiều giai đoạn tiếp theo. Nếu ước lượng thực tế là 1.000 nhưng planner dự đoán 10, sai số có thể lan sang những phép JOIN hoặc tổng hợp phía trên.

### 1.1. EXPLAIN cho thấy ước lượng, EXPLAIN ANALYZE cho thấy thực tế

~~~sql
EXPLAIN
SELECT *
FROM some_table
WHERE a = 7 AND b = 'X';
~~~

Trong output, phần như `rows=10` là **ước lượng của planner**.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM some_table
WHERE a = 7 AND b = 'X';
~~~

Với `ANALYZE`, PostgreSQL **thực sự chạy truy vấn** và hiển thị số hàng thực tế trong `actual rows</BT> cùng số lần chạy node (`loops</BT>).

Hai giá trị này không nhất thiết bằng nhau; mục tiêu là ước lượng đủ sát để planner chọn kế hoạch hợp lý.

### 1.2. Đọc số hàng đúng tại từng node

Trong một kế hoạch phức tạp, một node có thể có `rows=100</BT> và `actual rows=20 loops=5</BT>. `actual rows</BT> thường được hiển thị theo **mỗi lần lặp** của node, nên khi đối chiếu tổng khối lượng phải chú ý `loops</BT>.

Không so trực tiếp một giá trị `actual rows</BT> tại một node con với tổng hàng của toàn bộ query nếu chưa hiểu cấu trúc plan.

## 2. Giả định độc lập và phép nhân selectivity

Khi PostgreSQL không có thông tin đáng tin cậy về quan hệ giữa các điều kiện, việc ước lượng tổ hợp thường dựa trên giả định **độc lập tương đối**.

Với hai điều kiện A và B:

\[
P(A\land B)\approx P(A)\times P(B)
\]

Ví dụ:

~~~text
Bảng: 100.000 hàng

category_id có 100 giá trị, phân bố đều:
P(category_id = 7) ≈ 0,01

category_code có 100 giá trị, phân bố đều:
P(category_code = 'CAT-007') ≈ 0,01

Nếu coi độc lập:
P(cả hai) ≈ 0,01 × 0,01 = 0,0001

Estimated rows ≈ 100.000 × 0,0001 = 10.
~~~

Nhưng nếu mỗi `category_id</BT> luôn gắn với một `category_code</BT>:

~~~text
category_id=7  -> category_code='CAT-007'

Trong 100.000 hàng:
  category_id=7 và category_code='CAT-007'
  thực tế xuất hiện 1.000 lần.
~~~

Sai số là 100 lần:

\[
\frac{\text{actual rows}}{\text{estimated rows}}
=\frac{1{,}000}{10}=100
\]

### 2.1. Vì sao sai số có thể gây kế hoạch kém?

Nếu planner nghĩ chỉ có 10 hàng, nó có thể chọn một phương án hữu ích cho số hàng nhỏ, như nested loop thực hiện lookup nhiều lần ở bảng khác. Nếu thực tế có 1.000 hay 100.000 hàng, chiến lược khác có thể hiệu quả hơn.

Tuy vậy, **ước lượng sai không chứng minh chắc chắn plan sai**: lựa chọn plan còn phụ thuộc indexes, kích thước bảng, cache, phân phối dữ liệu và chi phí từng operator.

### 2.2. Không phải mọi cặp cột đều độc lập

Các ví dụ thường gặp:

| Cột A | Cột B | Quan hệ có thể tồn tại |
|---|---|---|
| `city_id` | `country_id` | Thành phố xác định quốc gia |
| `department_code` | `department_name` | Mã bộ phận xác định tên |
| `postal_code` | `city` | Có thể phụ thuộc, tùy quốc gia/chất lượng dữ liệu |
| `product_id` | `category_id` | Sản phẩm xác định danh mục |
| `region_code` | `region_label` | Có thể cùng diễn đạt một phân loại |
| `status` | `resolution_code` | Có thể có những tổ hợp phổ biến hoặc không hợp lệ |

Đừng mặc định mọi cặp có vẻ liên quan đều có quan hệ một-một. Ví dụ `country_id</BT> không quyết định duy nhất `city_id</BT> khi một quốc gia có nhiều thành phố.

## 3. Extended statistics là gì?

**Extended statistics** là thông tin thống kê bổ sung do PostgreSQL thu thập về **tổ hợp nhiều cột** hoặc, ở các phiên bản hỗ trợ, về **biểu thức**.

Cú pháp phổ biến:

~~~sql
CREATE STATISTICS statistics_name (dependencies)
ON column_a, column_b
FROM schema_name.table_name;
~~~

Sau đó chạy:

~~~sql
ANALYZE schema_name.table_name;
~~~

Các bước này tách biệt:

1. `CREATE STATISTICS` khai báo **đối tượng thống kê** và loại thông tin muốn thu thập.
2. `ANALYZE` lấy mẫu/đọc dữ liệu để **thu thập số liệu** cho đối tượng đó.
3. Planner có thể sử dụng thống kê khi ước lượng cho những mẫu truy vấn phù hợp.

### 3.1. Đây không phải index

`CREATE STATISTICS` **không tạo đường truy cập vật lý** như B-tree, GiST hoặc GIN. Nó không làm PostgreSQL đọc dữ liệu theo thứ tự mới hay rút ngắn việc tìm kiếm hàng trực tiếp.

Nó giúp planner **chọn kế hoạch** bằng ước lượng tốt hơn. Nếu muốn tăng tốc truy cập hàng, vẫn cần xem index và thiết kế query tương ứng.

### 3.2. Đây không phải constraint

Statistics không bắt buộc dữ liệu tuân thủ một quan hệ phụ thuộc. Nếu `category_id=7</BT> thường đi với `'CAT-007'</BT>, một câu INSERT nhập `'CAT-999'</BT> vẫn có thể được chấp nhận trừ khi có constraint hoặc logic ghi bảo vệ.

Nếu nghiệp vụ yêu cầu khóa danh mục phải hợp lệ, hãy dùng mô hình chuẩn hóa, `FOREIGN KEY</BT>, `UNIQUE</BT> hoặc kiểm tra phù hợp; không dựa vào thống kê để bảo vệ toàn vẹn dữ liệu.

### 3.3. Statistics không tự đổi dữ liệu truy vấn

Sau khi thêm thống kê, câu SELECT vẫn có ý nghĩa và kết quả logic như trước. Điều có thể thay đổi là **ước lượng cardinality** và từ đó **kế hoạch vật lý** được chọn.

## 4. Ba nhóm extended statistics thường dùng

PostgreSQL hỗ trợ ba kiểu extended statistics quan trọng:

| Loại | Cú pháp | Vấn đề chính |
|---|---|---|
| Functional dependencies | `dependencies` | Nhiều cột có quan hệ xác định/phụ thuộc về giá trị |
| Multivariate distinct counts | `ndistinct` | Ước lượng số tổ hợp phân biệt cho `GROUP BY</BT> nhiều cột |
| Multivariate most common values | `mcv` | Ước lượng các tổ hợp giá trị phổ biến, phân phối chéo không đều |

Một đối tượng có thể yêu cầu nhiều kiểu:

~~~sql
CREATE STATISTICS sales_stats (dependencies, ndistinct, mcv)
ON region_id, region_name, status
FROM sales;
~~~

Ví dụ này là cú pháp mô hình, giả định bảng/cột `sales</BT> tồn tại.

### 4.1. Chọn loại theo vấn đề, không theo cảm giác

Nếu query:

~~~sql
SELECT *
FROM catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

bị ước lượng thấp do hai cột thực chất phụ thuộc, `dependencies` là ứng viên tự nhiên.

Nếu query:

~~~sql
SELECT category_id, status, COUNT(*)
FROM catalog
GROUP BY category_id, status;
~~~

bị ước lượng sai **số nhóm phân biệt**, `ndistinct` phù hợp hơn.

Nếu một số cặp `(region, status)</BT> xuất hiện rất thường xuyên hoặc gần như không có, `mcv` có thể phản ánh độ lệch đó tốt hơn việc dùng tỷ lệ riêng của từng cột.

## 5. Functional dependency: X xác định Y nghĩa là gì?

Một quan hệ phụ thuộc hàm được ký hiệu:

\[
X \rightarrow Y
\]

Diễn giải: biết giá trị X thì giá trị Y được xác định, trong phạm vi dữ liệu hoặc bất biến đang xét.

Ví dụ:

~~~text
category_id  category_code
-----------  -------------
7            CAT-007
7            CAT-007
7            CAT-007
9            CAT-009
9            CAT-009
~~~

Ở dữ liệu này:

~~~text
category_id -> category_code
~~~

vì những hàng có cùng category_id có cùng category_code.

### 5.1. Phụ thuộc một chiều

Nếu:

~~~text
district_id -> province_id
~~~

một huyện thuộc một tỉnh. Nhưng:

~~~text
province_id -> district_id
~~~

thường **không đúng**, vì một tỉnh có nhiều huyện.

Độ mạnh/phương hướng phụ thuộc là yếu tố cần quan tâm, không chỉ biết “hai cột có liên quan”.

### 5.2. Dữ liệu có ngoại lệ

Một bảng thực tế có thể chứa:

~~~text
category_id=7, category_code=CAT-007  99,5% số hàng
category_id=7, category_code=CAT-008   0,5% số hàng
~~~

Khi đó mối quan hệ rất mạnh nhưng không tuyệt đối. Extended statistics có thể mô tả **độ phụ thuộc thống kê**, thay vì buộc một định luật logic được bảo đảm bằng constraint.

### 5.3. Phụ thuộc nhiều cột

Đôi khi cặp `(tenant_id, local_code)</BT> cùng xác định `display_label</BT>, nhưng từng cột riêng không xác định được.

Khái niệm:

\[
(\text{tenant\_id},\text{local\_code})\rightarrow\text{display\_label}
\]

PostgreSQL có thể thu thập thông tin dependencies cho nhiều cột theo hỗ trợ của phiên bản và dạng thống kê, nhưng không nên giả định mọi biểu thức truy vấn phức tạp sẽ được planner áp dụng các hệ số này.

## 6. dependencies giúp sửa lỗi nhân xác suất như thế nào?

Giả sử hai cột thực tế biểu diễn cùng phân loại. Planner không có thống kê mở rộng:

~~~text
P(category_id=7)             ≈ 0,01
P(category_code='CAT-007')   ≈ 0,01

Không có phụ thuộc:
P(cả hai) ≈ 0,0001
~~~

Nếu planner biết `category_id</BT> xác định `category_code</BT>, điều kiện thứ hai **không làm tập hàng co nhỏ thêm 100 lần** khi cặp điều kiện tương thích.

Mô hình khái niệm:

~~~text
Có dependency mạnh:
P(category_id=7 AND category_code='CAT-007')
xấp xỉ P(category_id=7)
≈ 0,01
~~~

Thực tế thuật toán PostgreSQL dùng hệ số phụ thuộc và các quy tắc ước lượng tương ứng, không đơn giản thay mọi phép nhân bằng một điều kiện duy nhất.

### 6.1. Một dependency hoàn hảo không khiến query nhanh tự thân

Điều thay đổi đầu tiên là **dự đoán số hàng**. Một query vẫn có thể cần scan 100.000 hàng nếu không có index và không có cách truy cập khác.

### 6.2. Planner không “học một công thức đúng tuyệt đối”

Extended statistics dựa trên dữ liệu được ANALYZE. Nó không phải theorem prover, không bảo đảm mọi hàng tương lai tuân thủ quan hệ, và không luôn phát hiện chính xác các điều kiện mâu thuẫn.

Ví dụ:

~~~sql
WHERE category_id = 7
  AND category_code = 'CAT-008'
~~~

Nếu dữ liệu thật chỉ có `category_id=7 -> CAT-007</BT>, kết quả là 0 hàng. Tuy nhiên, **dependency statistics có thể vẫn ước lượng một số hàng dương** vì cách sử dụng hệ số phụ thuộc thường giả định các điều kiện tương thích và bị dư thừa, chứ không suy luận đầy đủ rằng cặp điều kiện sai.

Đây là một **giới hạn quan trọng** của `dependencies`.

## 7. Khi nào functional dependencies được planner sử dụng?

Extended dependencies hữu ích nhất cho những câu WHERE có **các điều kiện đơn giản so sánh cột với hằng**.

Ví dụ phù hợp về hình thức:

~~~sql
SELECT *
FROM catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

Hoặc các điều kiện danh sách hằng số theo mức hỗ trợ:

~~~sql
SELECT *
FROM catalog
WHERE category_id IN (7, 8, 9)
  AND category_code = 'CAT-007';
~~~

Đừng mặc định kết quả ước lượng của hai ví dụ giống nhau; selectivity của IN và các tổ hợp phụ thuộc phức tạp hơn so với equality đơn.

### 7.1. Những trường hợp không nên trông chờ dependencies trực tiếp

Các giới hạn đã được mô tả trong PostgreSQL cho functional dependencies bao gồm:

- Điều kiện dạng cột = cột khác thay vì cột = hằng.
- So sánh cột với biểu thức không phải một hằng phù hợp.
- Range predicates như `x > 10</BT> hoặc `x BETWEEN ...</BT>.
- Điều kiện pattern như `LIKE 'ABC%'</BT>.
- Các phép join nhiều bảng mà tương quan cần xử lý ở phía join.

Ví dụ:

~~~sql
SELECT *
FROM catalog
WHERE category_id > 50
  AND category_code LIKE 'CAT-0%';
~~~

Không được kỳ vọng `dependencies` tự sửa mọi ước lượng của câu này chỉ vì hai cột có quan hệ.

### 7.2. Functional dependencies không giải mọi trường hợp AND/OR

Một điều kiện `AND</BT> nhiều equality constants là kịch bản điển hình. Những biểu thức phức tạp với OR, range, hàm biến đổi hoặc join cần xem dạng thống kê khác, cách planner xử lý và EXPLAIN thực tế.

### 7.3. JOIN là giới hạn cần ghi nhớ

~~~sql
SELECT *
FROM orders AS o
JOIN customers AS c
  ON o.customer_id = c.customer_id
WHERE o.country_code = c.country_code;
~~~

Dù hai cột trên mỗi bảng có thể có phụ thuộc về mặt dữ liệu, **extended statistics trên cột của một bảng không trở thành một loại thống kê đa bảng được planner dùng đầy đủ cho mọi join selectivity**.

Đặc biệt, PostgreSQL vẫn có giới hạn về cách áp dụng extended statistics vào **join selectivity estimation**. Không nên hứa CREATE STATISTICS sẽ tự sửa mọi nested loop sai do JOIN.

## 8. Lab: tạo dữ liệu với hai cột phụ thuộc hoàn hảo

Bài lab dùng database **thử nghiệm** và schema riêng. Nếu schema `extstats_lab` đã tồn tại, hãy chọn tên mới thay vì xóa dữ liệu không thuộc bài.

### 8.1. Tạo schema

~~~sql
CREATE SCHEMA extstats_lab;
~~~

### 8.2. Tạo bảng sản phẩm

~~~sql
CREATE TABLE extstats_lab.catalog (
    product_id BIGINT PRIMARY KEY,
    category_id INTEGER NOT NULL,
    category_code TEXT NOT NULL,
    status TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL
);
~~~

### 8.3. Nạp 100.000 hàng

~~~sql
INSERT INTO extstats_lab.catalog (
    product_id,
    category_id,
    category_code,
    status,
    price
)
SELECT
    n AS product_id,
    (n % 100) + 1 AS category_id,
    'CAT-' || lpad(((n % 100) + 1)::text, 3, '0')
        AS category_code,
    CASE
        WHEN ((n / 100) % 10) < 8 THEN 'active'
        ELSE 'archived'
    END AS status,
    (10 + (n % 400))::NUMERIC(12, 2) AS price
FROM generate_series(1, 100000) AS gs(n);
~~~

Trong dữ liệu này:

- Có đúng 100 giá trị `category_id`.
- Mỗi category có 1.000 sản phẩm.
- `category_id=7` luôn đi cùng `category_code='CAT-007'`.
- `category_id=8` luôn đi cùng `'CAT-008'`.
- Status gồm `active` và `archived`, được tạo từ công thức khác để làm bài tập tổ hợp sau.

Đây là dữ liệu tổng hợp, không phản ánh đầy đủ phân phối của một hệ thống sản phẩm thật.

### 8.4. Kiểm tra quan hệ dữ liệu

~~~sql
SELECT
    category_id,
    COUNT(DISTINCT category_code) AS distinct_codes,
    COUNT(*) AS row_count
FROM extstats_lab.catalog
GROUP BY category_id
ORDER BY category_id
LIMIT 10;
~~~

Với dữ liệu lab nguyên vẹn, mỗi category_id chỉ có **một category_code** và có **1.000 hàng**.

### 8.5. Không lẫn phép kiểm tra với constraint

Câu SELECT trên cho biết quan hệ đúng **trong dữ liệu hiện tại**. Nó không bắt PostgreSQL tiếp tục bảo vệ invariant cho các INSERT về sau.

Trong schema production, nếu `category_code` là thuộc tính của danh mục, một mô hình chuẩn hóa thành bảng `categories</BT> và FK từ `catalog.category_id</BT> có thể tự nhiên hơn việc lặp mã ở mọi sản phẩm. Extended statistics giúp planner khi dữ liệu đã có cột phụ thuộc, không thay quyết định mô hình hóa.

## 9. Baseline: ANALYZE và EXPLAIN trước khi tạo extended statistics

Trước khi đo ước lượng, thu thập thống kê từng cột:

~~~sql
ANALYZE extstats_lab.catalog;
~~~

### 9.1. Kiểm tra điều kiện một cột

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7;
~~~

Số hàng thực tế dự kiến khoảng 1.000. Planner có thể ước lượng gần số đó khi statistics đã được cập nhật.

### 9.2. Kiểm tra điều kiện hai cột

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

Trong trường hợp planner dựa trên giả định độc lập:

~~~text
Selectivity category_id=7          ~1/100
Selectivity category_code=CAT-007  ~1/100
Estimated combined rows            ~10
Actual rows                        1000
~~~

Kết quả estimate chính xác phụ thuộc sampling, phiên bản, cấu hình và dữ liệu hiện có. Đây là **kỳ vọng minh họa**, không phải cam kết output `rows=10` trên mọi máy.

### 9.3. Ghi nhận những gì cần đối chiếu

Khi chạy lab, hãy ghi:

| Tiêu chí | Trước extended statistics |
|---|---|
| Kế hoạch truy cập | Seq Scan, Index Scan hay Bitmap Scan? |
| `rows=...` | Bao nhiêu hàng planner dự đoán? |
| `actual rows=...` | Bao nhiêu hàng thực tế? |
| `loops=...` | Node được thực thi mấy lần? |
| Thời gian | Chỉ để tham khảo trong môi trường thử nghiệm |
| Buffers | Mức đọc từ shared/hệ thống cache nếu được hiển thị |

Mục tiêu chính của bài là **sai lệch cardinality**, không phải so tốc độ một câu query quá nhỏ với vài mili-giây biến động.

## 10. Tạo dependencies statistics

Tạo đối tượng cho đúng hai cột trong cùng bảng:

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

Sau đó **phải chạy ANALYZE** để thống kê được thu thập:

~~~sql
ANALYZE extstats_lab.catalog;
~~~

### 10.1. Vì sao cần ANALYZE lại?

`CREATE STATISTICS` khai báo PostgreSQL **nên thu thập loại thống kê nào**. Nó không tự đi quét dữ liệu và xây toàn bộ phân phối vào cùng thời điểm DDL hoàn tất.

Do vậy nếu chỉ CREATE rồi lập tức EXPLAIN, planner có thể chưa có dữ liệu extended statistics mới để dùng.

### 10.2. Chạy lại cùng EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-007';
~~~

Với hai cột phụ thuộc rất mạnh, planner có thể dự đoán số hàng **gần thực tế hơn nhiều** so với baseline chưa có dependencies.

### 10.3. Hình dung khác biệt

| Điều kiện | Không có dependencies | Có dependencies | Thực tế lab |
|---|---:|---:|---:|
| `category_id=7` | Khoảng 1.000 | Khoảng 1.000 | 1.000 |
| `category_code='CAT-007'` | Khoảng 1.000 | Khoảng 1.000 | 1.000 |
| Cả hai điều kiện | Có thể khoảng 10 | Có thể gần 1.000 | 1.000 |

Các ước lượng trong bảng nhằm minh họa xu hướng. PostgreSQL không bảo đảm một con số cụ thể do sampling và chi tiết planner.

### 10.4. Kế hoạch có thể vẫn là Seq Scan

Trên bảng 100.000 hàng chưa có index cho `category_id`, planner có thể chọn Seq Scan cả trước và sau thống kê. Điều đó **không có nghĩa dependencies không có tác dụng**: hãy nhìn `rows estimate` trước khi phán xét tên plan node.

## 11. Trường hợp điều kiện mâu thuẫn

Thử:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM extstats_lab.catalog
WHERE category_id = 7
  AND category_code = 'CAT-008';
~~~

Trong dữ liệu lab, không có hàng nào thỏa hai điều kiện.

### 11.1. Dependencies không phải constraint solver

Functional dependencies trong planner được dùng để sửa ước lượng selectivity của điều kiện tương quan. Nó không nhất thiết hiểu rằng `7</BT> chỉ đi với `'CAT-007'</BT> rồi suy ra cặp `(7,'CAT-008')</BT> là không thể.

Vì vậy estimator **có thể vẫn dự đoán số hàng dương** dù `actual rows=0</BT>.

### 11.2. Khi cần phân biệt cặp hợp lệ và bất hợp lệ

Nếu các tổ hợp giá trị có tần suất rất khác nhau hoặc nhiều cặp gần như không tồn tại, **multivariate MCV** có thể hữu ích hơn dependencies cho một số dạng truy vấn.

Tuy vậy, ngay cả thống kê MCV cũng không phải bảo đảm logic tuyệt đối cho mọi tổ hợp. Để ngăn dữ liệu sai, dùng constraint hoặc mô hình hóa đúng.

## 12. Đọc thông tin trong pg_stats_ext

PostgreSQL có system view `pg_stats_ext` để xem thông tin extended statistics đã thu thập, trong phạm vi quyền phù hợp.

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    dependencies
FROM pg_stats_ext
WHERE schemaname = 'extstats_lab'
  AND tablename = 'catalog'
ORDER BY statistics_name;
~~~

Các cột thường hữu ích:

| Cột | Nội dung |
|---|---|
| `schemaname` | Schema của bảng |
| `tablename` | Tên bảng |
| `statistics_name` | Tên đối tượng statistics |
| `attnames` | Danh sách cột liên quan |
| `kinds` | Những loại statistics đang thu thập |
| `dependencies` | Dữ liệu dependency đã phân tích, ở dạng hiển thị phù hợp |
| `n_distinct` | Thông tin distinct tổ hợp khi có ndistinct |
| `most_common_vals` | Các tổ hợp phổ biến khi có mcv |

### 12.1. Một ví dụ biểu diễn dependency

Trong một số đầu ra, dữ liệu dependency có dạng giống:

~~~text
{"2 => 3": 1.000000, "3 => 2": 1.000000}
~~~

Đây chỉ là **ví dụ định dạng**, không phải kết quả bắt buộc của lab hay số attnum cố định. Các số biểu thị cột theo thuộc tính nội bộ và hệ số quan hệ, không đơn giản là tên cột.

Không sao chép một chuỗi dependency từ bảng này sang bảng khác rồi dùng như metadata có nghĩa chung.

### 12.2. Không hiểu hệ số là độ chính xác dự đoán tuyệt đối

Một hệ số dependency gần 1 cho thấy quan hệ rất mạnh trong mẫu thống kê, không phải cam kết mọi query sẽ có cardinality estimation chính xác và không phải một database constraint.

### 12.3. Quyền truy cập

View `pg_stats_ext` có cơ chế hiển thị dựa trên quyền đối với dữ liệu thống kê. Một role không đủ quyền có thể không nhìn thấy mọi thông tin; không cấp quyền superuser cho ứng dụng chỉ để debug query plan.

## 13. Catalog pg_statistic_ext và pg_statistic_ext_data

PostgreSQL lưu định nghĩa thống kê mở rộng trong catalog:

- `pg_statistic_ext`: metadata của đối tượng thống kê như tên, bảng, loại statistics và các cột/biểu thức.
- `pg_statistic_ext_data`: dữ liệu thống kê được thu thập, có thể có giới hạn quyền truy cập.

Ví dụ xem metadata:

~~~sql
SELECT
    s.oid,
    n.nspname AS statistics_schema,
    s.stxname AS statistics_name,
    s.stxrelid::regclass AS target_table,
    s.stxkind
FROM pg_statistic_ext AS s
JOIN pg_namespace AS n
  ON n.oid = s.stxnamespace
WHERE s.stxrelid = 'extstats_lab.catalog'::regclass;
~~~

### 13.1. Những mã kiểu thống kê

Các loại thông tin thống kê được lưu/biểu diễn bằng metadata riêng. Đối với thao tác quản trị thường ngày, `pg_stats_ext.kinds` và lệnh `CREATE STATISTICS</BT> thường dễ hiểu hơn việc phụ thuộc vào chi tiết layout catalog nội bộ.

### 13.2. Không đọc catalog nội bộ như API ổn định của ứng dụng

Hệ thống thông tin của PostgreSQL có thể thay đổi cấu trúc chi tiết qua phiên bản. Khi viết migration và tài liệu monitoring dài hạn, ưu tiên view/cú pháp chính thức phù hợp hơn việc parse trực tiếp dạng lưu trữ nội bộ của `stxddependencies`.

### 13.3. Thống kê không chứa dữ liệu hàng để truy vấn

`pg_statistic_ext_data` mô tả mô hình thống kê/ước lượng, không phải một bảng ánh xạ đầy đủ `category_id -> category_code` cho ứng dụng truy vấn ra từng bản ghi.

## 14. Loại ndistinct: khi GROUP BY hai cột ước lượng sai

`dependencies` giải quyết một lớp vấn đề của WHERE. Một loại khác, **`ndistinct`**, tập trung vào số tổ hợp giá trị phân biệt.

Giả sử một bảng có:

~~~text
category_id: 100 giá trị phân biệt
category_code: 100 giá trị phân biệt
Quan hệ: mỗi category_id gắn với đúng một category_code
~~~

Số tổ hợp `(category_id, category_code)</BT> thực tế chỉ khoảng **100**, không phải 100 × 100 = 10.000.

### 14.1. Vấn đề cho GROUP BY

~~~sql
SELECT
    category_id,
    category_code,
    COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

Nếu planner ước lượng sai số nhóm, quyết định về phương pháp aggregate, kích thước hash table hay bộ nhớ có thể kém tối ưu.

### 14.2. Tạo ndistinct

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

Sau đó:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    category_id,
    category_code,
    COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

Quan sát ước lượng số nhóm tại node Aggregate/HashAggregate/GroupAggregate, không chỉ ước lượng đầu vào scan.

### 14.3. Vì sao dependencies không thay được ndistinct?

Một loại statistics phục vụ mô hình selectivity của các điều kiện, loại kia phục vụ ước lượng số **tổ hợp phân biệt**. Chúng có thể dựa trên cùng cặp cột nhưng dùng ở các ngữ cảnh planner khác nhau.

### 14.4. COUNT(DISTINCT) và số nhóm

Có thể kiểm tra số tổ hợp thực tế bằng:

~~~sql
SELECT COUNT(*) AS actual_groups
FROM (
    SELECT category_id, category_code
    FROM extstats_lab.catalog
    GROUP BY category_id, category_code
) AS grouped;
~~~

Dữ liệu lab nguyên vẹn sẽ có **100 nhóm**.

## 15. Loại mcv: hiểu những tổ hợp phổ biến

`mcv` là **multivariate most-common-values statistics**: mô tả những tổ hợp giá trị xảy ra thường xuyên và tần suất của chúng.

Giả sử:

~~~text
region='north', status='active'   rất phổ biến
region='north', status='archived' hiếm
region='south', status='active'   bình thường
~~~

Tỷ lệ riêng lẻ của `region</BT> và `status</BT> không mô tả đầy đủ phân phối đồng thời.

### 15.1. Tạo mcv

~~~sql
CREATE STATISTICS extstats_lab.catalog_category_mcv
    (mcv)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

Tùy giới hạn target và phân phối, MCV có thể ghi nhận những cặp phổ biến. Với 100 cặp phân bố đều trong lab, đây không phải môi trường tạo lệch mạnh nhất; một bảng dữ liệu thật có skew thường thể hiện lợi ích MCV rõ hơn.

### 15.2. Đọc MCV qua view

~~~sql
SELECT
    statistics_name,
    most_common_vals,
    most_common_freqs,
    most_common_base_freqs
FROM pg_stats_ext
WHERE schemaname = 'extstats_lab'
  AND tablename = 'catalog'
  AND statistics_name = 'catalog_category_mcv';
~~~

- `most_common_vals`: các tổ hợp giá trị phổ biến.
- `most_common_freqs`: tần suất thực tế ước lượng của tổ hợp.
- `most_common_base_freqs`: tần suất cơ sở giả định độc lập cho tổ hợp, giúp nhìn thấy khác biệt.

### 15.3. MCV và dependency có phải một?

Không.

- `dependencies` mô tả sức mạnh quan hệ xác định/phụ thuộc; có thể điều chỉnh selectivity của nhiều equality predicates.
- `mcv` mô tả **tổ hợp cụ thể** nào phổ biến và tần suất tương ứng.
- `ndistinct` mô tả số tổ hợp khác nhau, đặc biệt hữu ích cho grouping.

### 15.4. Khi nào MCV đáng ưu tiên?

Khi query lọc các giá trị cụ thể và phân phối chéo có độ lệch lớn, kể cả một số tổ hợp hiếm hoặc gần như không tồn tại. Tuy nhiên, cách planner tận dụng MCV còn phụ thuộc dạng điều kiện, phiên bản và mẫu thống kê.

## 16. Có nên tạo cả ba loại statistics?

Có thể khai báo:

~~~sql
CREATE STATISTICS extstats_lab.catalog_composite_stats
    (dependencies, ndistinct, mcv)
ON category_id, category_code, status
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

Nhưng **không phải cứ có nhiều loại và nhiều cột là luôn tốt hơn**.

### 16.1. Chi phí khi tạo nhiều đối tượng

- Tốn thời gian ANALYZE.
- Tăng kích thước metadata statistics.
- Có thể tăng chi phí planner sử dụng thống kê.
- Tăng công bảo trì khi schema/logic truy vấn đổi.
- Dễ thu thập những cột không mang lại cải thiện rõ ràng.

### 16.2. Một đối tượng cho ba cột không bảo đảm mọi query ba cột sẽ tốt hơn

Phụ thuộc được phát hiện từ dữ liệu; planner còn phải nhận diện clause phù hợp. Nếu query chủ yếu là range, LIKE hoặc join, một đối tượng lớn không nhất thiết giải quyết sai lệch gốc.

### 16.3. Làm theo workload

Nếu ứng dụng chỉ lọc `category_id=... AND category_code=...</BT>, một đối tượng `dependencies` nhỏ và rõ mục đích có thể là đủ. Nếu báo cáo GROUP BY nhiều cột, `ndistinct` là yêu cầu khác.

## 17. Một bài lab GROUP BY có và không có ndistinct

Để quan sát khác biệt trực tiếp:

### 17.1. Trước khi thêm ndistinct

Nếu chưa tạo đối tượng `catalog_category_nd`, chạy:

~~~sql
ANALYZE extstats_lab.catalog;

EXPLAIN (ANALYZE, BUFFERS)
SELECT category_id, category_code, COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

Ghi lại estimated rows tại Aggregate và actual rows.

### 17.2. Sau khi thêm ndistinct

~~~sql
CREATE STATISTICS extstats_lab.catalog_pair_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;

EXPLAIN (ANALYZE, BUFFERS)
SELECT category_id, category_code, COUNT(*)
FROM extstats_lab.catalog
GROUP BY category_id, category_code;
~~~

**Chú ý:** nếu đã tạo `catalog_category_nd` ở phần trước, đối tượng mới có thể trùng mục đích. Trong bài thực hành hãy **chọn một** đối tượng ndistinct để tránh tạo hai thống kê tương tự không cần thiết.

### 17.3. Đánh giá điều gì?

- Estimated number of groups có sát 100 hơn không?
- Planner dùng HashAggregate hay GroupAggregate?
- Memory Usage, Sort Method, Disk usage nếu có.
- Tổng thời gian có biến động không?

Một plan có thể vẫn giữ cùng node dù cardinality chính xác hơn. Đừng coi đó là thất bại khi mục tiêu chỉ là sửa estimate.

## 18. Extended statistics và index nhiều cột khác nhau

Một index như:

~~~sql
CREATE INDEX catalog_category_idx
ON extstats_lab.catalog (category_id, category_code);
~~~

và một thống kê như:

~~~sql
CREATE STATISTICS extstats_lab.catalog_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

phục vụ mục tiêu khác nhau.

| Đặc điểm | Multicolumn index | Extended statistics |
|---|---|---|
| Cấu trúc dữ liệu vật lý | Có | Không phải index |
| Hỗ trợ tìm hàng nhanh | Có, nếu điều kiện phù hợp | Không trực tiếp |
| Hỗ trợ planner chọn plan | Có qua access path/cost | Có qua ước lượng |
| Có thể thay đổi chi phí UPDATE/INSERT | Có do duy trì index | Không duy trì index theo từng row theo cách đó |
| Cần ANALYZE để có dữ liệu thống kê | Index có metadata và các stats liên quan | **Cần ANALYZE sau CREATE STATISTICS** |
| Dùng cho GROUP BY distinct combinations | Có thể giúp đường truy cập | `ndistinct` giúp ước lượng nhóm |
| Bảo đảm UNIQUE | Chỉ nếu tạo UNIQUE index | Không |

### 18.1. Một index không tự giải quyết hết cardinality

Nếu index cho phép truy cập hàng nhanh nhưng planner nghĩ chỉ có 10 hàng thay vì 1.000, estimate ở JOIN phía trên vẫn có thể sai. Dependencies có thể bổ trợ index.

### 18.2. Statistics không thay access path

Nếu query cần trả 1.000 hàng trên bảng có hàng trăm triệu dòng, chỉ thêm thống kê mà không có index phù hợp vẫn có thể phải quét lượng lớn dữ liệu.

### 18.3. Multicolumn index cũng có thứ tự cột

Với B-tree, thứ tự cột có thể ảnh hưởng hiệu quả của predicate. `CREATE STATISTICS</BT> không có ý nghĩa “leading column” giống index B-tree. Không sao chép cách chọn thứ tự index sang thiết kế statistics một cách máy móc.

## 19. Dữ liệu thay đổi: tại sao ANALYZE quan trọng?

Thống kê là ảnh chụp/tóm tắt ước lượng tại thời điểm được thu thập. Sau khi nhiều hàng được thêm/sửa/xóa, phân phối có thể thay đổi.

Ví dụ:

- Trước đây `status='active'` chiếm 90%.
- Sau chiến dịch archival, active còn 30%.
- Category mới được thêm hàng triệu sản phẩm.
- Mối quan hệ giữa mã và tên bị thay đổi do migration.

Nếu statistics chưa được cập nhật, planner có thể tiếp tục dựa trên phân phối cũ.

### 19.1. ANALYZE thủ công

~~~sql
ANALYZE extstats_lab.catalog;
~~~

Có thể dùng khi vừa nạp lượng dữ liệu lớn vào bảng thử nghiệm hoặc sau migration dữ liệu đã kiểm soát.

### 19.2. Autovacuum có thể chạy autoanalyze

PostgreSQL thường tự thu thập statistics thông qua cơ chế autoanalyze dựa trên ngưỡng thay đổi. Tuy nhiên, sau một bulk load hoặc thay đổi phân phối mạnh, thời điểm autoanalyze có thể chưa phù hợp với lúc query cần kế hoạch tốt.

### 19.3. CREATE STATISTICS không tự khởi tạo dữ liệu

Kể cả khi bảng đã được ANALYZE nhiều lần **trước** khi tạo thống kê, sau khi `CREATE STATISTICS</BT> mới vẫn cần chạy ANALYZE lại để có dữ liệu cho đối tượng mới.

### 19.4. Thống kê không chính xác tuyệt đối vì lấy mẫu

ANALYZE thường dựa trên sampling, không tính full census mọi tổ hợp giá trị ở mọi bảng. Những nhóm hiếm, sự tương quan ở tail và phân phối thay đổi nhanh có thể vẫn có sai số.

## 20. statistics target: độ chi tiết và chi phí

PostgreSQL dùng **statistics target** để điều chỉnh lượng thông tin thống kê được thu thập. Với extended statistics, có thể thay target của đối tượng:

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS 500;

ANALYZE extstats_lab.catalog;
~~~

Cú pháp này giả định đối tượng `catalog_category_dep` tồn tại.

### 20.1. Tăng target có lợi khi nào?

- MCV cần giữ thêm tổ hợp phổ biến.
- Phân phối phức tạp hoặc nhiều giá trị phân biệt.
- Sample mặc định chưa đại diện tốt.
- Estimates của query trọng yếu vẫn quá lệch sau ANALYZE.

### 20.2. Tăng target không tự sửa mọi hạn chế

Nếu vấn đề là join selectivity đa bảng mà PostgreSQL chưa dùng extended dependencies theo cách bạn mong đợi, tăng target từ 100 lên 1000 không nhất thiết giúp.

Nếu query dùng LIKE/range mà dependency estimator không áp dụng, target lớn hơn cũng không biến nó thành hỗ trợ đầy đủ cho mọi predicate.

### 20.3. Chi phí tăng

Target lớn hơn có thể tăng lượng mẫu, thời gian ANALYZE, kích thước statistics và chi phí lập kế hoạch. Đừng đặt giá trị rất cao cho mọi đối tượng một cách mặc định.

### 20.4. default_statistics_target và thống kê cột

Ngoài `ALTER STATISTICS</BT>, PostgreSQL còn có `default_statistics_target</BT> và khả năng đặt target riêng cho cột. Chúng liên quan nhưng không đồng nhất về mục tiêu đo:

- Stats từng cột: histogram, MCV đơn cột, n_distinct...
- Stats mở rộng: sự phụ thuộc/tổ hợp giá trị giữa cột.

Nên xem **đối tượng nào thiếu thông tin** trước khi tăng target.

## 21. Quy trình chẩn đoán cardinality estimation sai

Một quy trình thực tế:

1. Chọn **một query chậm cụ thể**, có tham số gần với workload thật.
2. Chạy `EXPLAIN (ANALYZE, BUFFERS)</BT> trong môi trường phù hợp; cẩn thận vì ANALYZE thực thi.
3. Tìm **node đầu tiên** có estimated rows lệch lớn so với actual rows.
4. Xem clause tại node đó: một cột hay nhiều cột?
5. Kiểm tra index, kiểu dữ liệu, casts và điều kiện WHERE/JOIN.
6. Kiểm tra statistics từng cột trong `pg_stats</BT>.
7. Kiểm tra phân phối và quan hệ phụ thuộc trong dữ liệu đại diện.
8. Xác định vấn đề thuộc **WHERE dependencies**, **GROUP BY ndistinct** hay **skew MCV**.
9. Tạo đúng đối tượng `CREATE STATISTICS</BT> ở **bảng chứa các cột**.
10. Chạy `ANALYZE</BT>.
11. So sánh estimated rows, plan và thời gian một cách cẩn thận.
12. Nếu vẫn sai, xem giới hạn planner và các nguyên nhân khác.
13. Đo chi phí ANALYZE/memory/statistics, tránh thừa đối tượng.
14. Triển khai qua migration phù hợp, có cách rollback.
15. Theo dõi khi phân phối dữ liệu thay đổi về sau.

### 21.1. Không bắt đầu bằng “tăng mọi statistics target”

Nếu nguyên nhân thật là stale statistics, một `ANALYZE</BT> bình thường có thể đủ. Nếu nguyên nhân là thiếu index hoặc query expression không sargable, extended stats có thể không giải quyết được.

### 21.2. Đối chiếu cùng tham số

Một query với category phổ biến có thể có estimated rows khác query với category hiếm. Không so EXPLAIN trước/ sau trên hai giá trị khác nhau rồi quy nguyên nhân cho statistics.

### 21.3. EXPLAIN ANALYZE có tác dụng thực

Với INSERT/UPDATE/DELETE, `EXPLAIN ANALYZE</BT> **chạy câu lệnh**, có thể thay dữ liệu. Chỉ chạy DML trong transaction thử nghiệm có rollback hoặc trên môi trường có kế hoạch phù hợp.

## 22. Ước lượng sai lan truyền qua JOIN như thế nào?

Xem query khái niệm:

~~~sql
SELECT c.product_id, s.quantity
FROM extstats_lab.catalog AS c
JOIN extstats_lab.stock AS s
  ON s.product_id = c.product_id
WHERE c.category_id = 7
  AND c.category_code = 'CAT-007';
~~~

Đây là ví dụ cấu trúc; bảng `extstats_lab.stock` sẽ cần được tạo nếu muốn chạy.

### 22.1. Nếu planner tưởng chỉ 10 sản phẩm

Nó có thể chọn nested loop, dự kiến lookup stock 10 lần.

### 22.2. Nếu thực tế 1.000 sản phẩm

Thực tế phải lookup 1.000 lần. Nested loop vẫn có thể hợp lý nếu index lookup rất rẻ, nhưng trong một số workload, hash join hoặc cách truy cập khác tốt hơn.

### 22.3. Dependencies có thể sửa estimate ở phía lọc

Extended stats trên catalog giúp ước lượng số hàng **sau WHERE trong cùng bảng** tốt hơn, từ đó có thể tác động đến lựa chọn JOIN ở phía trên.

### 22.4. Không đồng nghĩa sửa mọi join selectivity

Điều chỉnh base-relation estimate và tính chính xác selectivity của điều kiện **join giữa hai bảng** là hai vấn đề khác nhau. PostgreSQL có những giới hạn về việc áp dụng extended statistics trực tiếp cho join clauses. Không hứa một thống kê trên catalog sẽ hiểu toàn bộ quan hệ với stock hoặc orders.

## 23. Ví dụ bổ sung: district_id xác định province_id

Giả sử bảng `addresses` có:

~~~text
district_id   province_id
-----------   -----------
1001          10
1002          10
1003          10
2001          20
2002          20
~~~

Trong dữ liệu này:

~~~text
district_id -> province_id
~~~

Nhưng:

~~~text
province_id -/-> district_id
~~~

Một câu WHERE:

~~~sql
SELECT *
FROM addresses
WHERE district_id = 1001
  AND province_id = 10;
~~~

có hai điều kiện có tính phụ thuộc. Planner không có dependencies có thể đánh giá mỗi điều kiện như một bộ lọc độc lập, dự đoán ít hàng hơn thực tế.

### 23.1. Phân biệt hướng phụ thuộc

Nếu một tỉnh có rất nhiều huyện, chỉ biết `province_id=10` không cho phép suy ra một district cụ thể.

### 23.2. Kiểm tra chất lượng dữ liệu

Một địa chỉ nhập sai `district_id=1001, province_id=20` khiến quan hệ không còn tuyệt đối. Statistics phản ánh xu hướng từ dữ liệu, không phát hiện/loại bỏ bản ghi sai giúp bạn.

### 23.3. Khi nào nên chuẩn hóa?

Nếu district luôn thuộc một province, có thể thiết kế:

~~~text
districts(district_id PRIMARY KEY, province_id REFERENCES provinces)
addresses(address_id, district_id REFERENCES districts)
~~~

và suy ra province qua JOIN khi cần, tránh lưu dữ liệu dư thừa.

Nhưng khi bảng lớn vẫn lưu cả hai vì workload, extended statistics có thể hỗ trợ query planner; điều đó không loại bỏ trách nhiệm đảm bảo dữ liệu đồng nhất.

## 24. Ví dụ nhiều tenant: phụ thuộc trong khóa tổng hợp

Một hệ thống nhiều tenant có `tenant_id</BT>, `tenant_region</BT> và `service_tier</BT>.

Ví dụ:

~~~text
tenant_id -> tenant_region
tenant_id -> service_tier  (nếu tier chỉ thuộc tính tenant)
~~~

Câu truy vấn:

~~~sql
SELECT *
FROM tenant_events
WHERE tenant_id = 42
  AND tenant_region = 'ap-southeast'
  AND service_tier = 'premium';
~~~

có thể bị đánh giá quá chọn lọc nếu ba điều kiện được nhân độc lập.

### 24.1. Statistics trên nhiều cột trong cùng bảng

~~~sql
CREATE STATISTICS tenant_events_dep
    (dependencies)
ON tenant_id, tenant_region, service_tier
FROM tenant_events;
~~~

Đây là cú pháp ví dụ; cần bảng thực tế phù hợp mới chạy được.

### 24.2. Phụ thuộc có thay đổi theo thời gian?

Nếu `service_tier` nằm trên **event tại thời điểm phát sinh** chứ không phải tier hiện tại của tenant, một tenant có thể có nhiều tier trong lịch sử. Khi đó quan hệ `tenant_id -> service_tier` không hoàn hảo.

Phải hiểu **ngữ nghĩa cột** và phân phối thực tế, không chỉ tên gọi giống nhau.

### 24.3. Multi-tenant không tự an toàn nhờ statistics

Extended stats không ngăn lộ dữ liệu tenant và không thay Row-Level Security, tenant scoping hoặc authorization trong API.

## 25. Phụ thuộc mạnh nhưng không đồng nghĩa tương quan Pearson cao

Người học đôi khi dùng từ “correlation” để chỉ mọi dạng liên quan. Cần phân biệt:

- **Functional dependency**: giá trị cột A xác định hoặc phần lớn xác định B.
- **Tương quan tuyến tính** (Pearson): mức độ hai số biến thiên tuyến tính với nhau.
- **`pg_stats.correlation`**: thống kê liên quan thứ tự giá trị cột với **thứ tự vật lý của hàng** trong bảng, hữu ích cho ước lượng chi phí access path.
- **Multivariate MCV**: tần suất của những tổ hợp giá trị cụ thể.

### 25.1. Ví dụ

`category_id=7 -> category_code='CAT-007'</BT> là dependency mạnh, nhưng `category_code</BT> là text, không có ý nghĩa Pearson numeric trực tiếp nếu không định nghĩa phép biến đổi.

### 25.2. pg_stats.correlation không phải extended dependency

Một cột có `correlation</BT> cao trong `pg_stats</BT> có thể do dữ liệu được ghi gần theo thứ tự của cột đó. Điều này **khác hoàn toàn** việc hai cột có quan hệ phụ thuộc về giá trị.

### 25.3. Không chọn statistics bằng một con số correlation lẻ

Nếu query sai vì hai equality predicates trùng ý nghĩa, kiểm tra dependencies; nếu index scan đắt vì hàng rải trên heap, xem physical correlation và access pattern; nếu group count sai, xem ndistinct.

## 26. Phụ thuộc và các biểu thức trong WHERE

Nếu query dùng:

~~~sql
SELECT *
FROM catalog
WHERE lower(category_code) = 'cat-007'
  AND category_id = 7;
~~~

điều kiện nằm trên `lower(category_code)</BT>, không còn đúng một reference đơn giản tới cột theo cùng hình thức equality clause.

### 26.1. Không tự suy luận dependency cột gốc luôn áp dụng

Functional dependency statistics tạo trên hai cột gốc không bảo đảm PostgreSQL sẽ áp dụng nó trực tiếp vào mọi biểu thức bao quanh cột.

### 26.2. Expression statistics trên phiên bản hỗ trợ

Các PostgreSQL hiện đại hỗ trợ thống kê trên biểu thức qua cú pháp `CREATE STATISTICS</BT> phù hợp. Ví dụ khái niệm:

~~~sql
CREATE STATISTICS catalog_lower_code_stats
ON (lower(category_code))
FROM catalog;
~~~

Cú pháp này cần bảng `catalog</BT> tồn tại và phiên bản hỗ trợ expression statistics. Nó **không giống** khai báo `(dependencies)</BT> giữa hai cột gốc.

### 26.3. Expression index cũng khác

~~~sql
CREATE INDEX catalog_lower_code_idx
ON extstats_lab.catalog (lower(category_code));
~~~

Index cho đường truy cập theo biểu thức. Statistics mô tả phân phối/quan hệ để ước lượng. Dùng cách nào còn phụ thuộc query shape và kế hoạch thực tế.

## 27. Parameterized queries và generic plans

Trong ứng dụng, điều kiện thường dùng tham số:

~~~sql
SELECT *
FROM extstats_lab.catalog
WHERE category_id = $1
  AND category_code = $2;
~~~

Tùy cách chuẩn bị query/driver và việc PostgreSQL chọn **custom plan** hay **generic plan**, planner có thể hoặc không có đầy đủ giá trị cụ thể của tham số để sử dụng thống kê MCV/selectivity theo cách tối ưu nhất.

### 27.1. Tại sao EXPLAIN literal khác ứng dụng?

Một câu EXPLAIN với `category_id=7</BT> và `category_code='CAT-007'</BT> có hằng số rõ ràng, trong khi generic prepared plan cần phục vụ nhiều bộ tham số.

### 27.2. Kiểm tra đúng workload

Đừng kết luận “statistics không tác dụng” chỉ từ một câu query literal nếu ứng dụng thực chạy prepared statements/generic plans; cũng đừng chỉ tối ưu một bộ tham số hiếm.

### 27.3. Kỹ thuật quan sát

PostgreSQL có hỗ trợ `PREPARE</BT>, `EXPLAIN EXECUTE</BT> và cấu hình chẩn đoán `plan_cache_mode</BT> ở phiên bản phù hợp. Dùng trên môi trường thử nghiệm để hiểu custom/generic behavior nếu query plan trong ứng dụng khác kế hoạch SQL thủ công.

### 27.4. Không ép custom plan toàn hệ thống chỉ vì một query

Việc này có thể tăng chi phí planning. Cần đánh giá tập truy vấn, parameter skew và tổng workload.

## 28. Statistics target, sample size và phân phối hiếm

Một query chậm có thể lọc các tổ hợp cực hiếm:

~~~sql
WHERE status = 'fraud'
  AND region = 'rare-region'
~~~

Nếu giá trị hiếm chiếm tỷ lệ rất nhỏ, sample của ANALYZE có thể không chứa đủ ví dụ để planner ước lượng chính xác.

### 28.1. MCV không thể ghi mọi tổ hợp

Một MCV list có giới hạn kích thước. Nó nhắm các tổ hợp phổ biến; những tổ hợp hiếm có thể vẫn phải ước lượng từ phần phân phối còn lại.

### 28.2. Dependencies phản ánh xu hướng, không danh mục đầy đủ

Quan hệ phụ thuộc mạnh nhưng có một số ngoại lệ vẫn có thể tạo dự đoán sai ở các điều kiện hiếm.

### 28.3. Nếu tăng target

Đo trước/sau:

- Số estimated rows.
- Tần suất chọn plan không tốt.
- Chi phí ANALYZE.
- Dung lượng statistics.
- Planning time.
- Execution time trên dữ liệu đại diện.

Không chỉ xem một hệ số mới “đẹp hơn” rồi mặc định production nhanh hơn.

## 29. ALTER STATISTICS và DROP STATISTICS

### 29.1. Tăng target

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS 250;

ANALYZE extstats_lab.catalog;
~~~

### 29.2. Trở về target mặc định

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_dep
SET STATISTICS DEFAULT;

ANALYZE extstats_lab.catalog;
~~~

### 29.3. Bỏ một đối tượng thống kê

~~~sql
DROP STATISTICS extstats_lab.catalog_category_dep;
~~~

Lệnh DROP xóa đối tượng thống kê, **không xóa hàng** của bảng catalog và không xóa index.

### 29.4. Migration nên có cách rollback

Nếu vừa tạo statistics và plan xấu đi ở workload thực, có thể DROP đối tượng, chạy ANALYZE khi cần hoặc điều chỉnh target/loại thống kê phù hợp.

Nhưng sau khi CREATE nhiều đối tượng cùng cặp cột, chỉ DROP một đối tượng có thể không quay về baseline vì những statistics khác vẫn tồn tại.

### 29.5. Không DROP bừa trong lab đã dùng ở phần sau

Nếu bạn muốn thử từng loại stats ở các phần trước, tạo trên một database lab riêng hoặc ghi lại danh sách đối tượng đã có. Đừng chạy DROP trên hệ thống đang có người khác phụ thuộc vào query plan hiện tại.

## 30. Ước lượng cardinality và chi phí thực thi là hai vấn đề riêng

Một query có thể:

- Estimated rows đúng nhưng vẫn chậm vì đĩa chậm.
- Estimated rows sai nhưng planner vẫn chọn plan phù hợp.
- Estimated rows đúng sau CREATE STATISTICS nhưng chưa có index tốt.
- Estimated rows đúng ở scan nhưng sai ở JOIN do các giới hạn khác.
- Có index tối ưu nhưng planning time tăng vì quá nhiều phương án.

### 30.1. Không đo một lần duy nhất

Thời gian EXPLAIN ANALYZE chịu ảnh hưởng cache ấm/lạnh, I/O, CPU contention, background maintenance và dữ liệu đã đổi. Cần nhiều lần đo trên dữ liệu đại diện trước khi kết luận cải thiện.

### 30.2. Đúng mục tiêu trước

Nếu bạn thêm dependencies để sửa lỗi underestimate 100 lần, bằng chứng trực tiếp là **ước lượng rows ở filter node tiến gần actual**. Kế hoạch có thay đổi hay không là kết quả thứ cấp.

### 30.3. Đừng cố ép planner bằng cách tắt join types khi chưa cần

Các tham số như `enable_nestloop` có thể hữu ích để thăm dò lựa chọn trong môi trường debug, nhưng không nên coi việc tắt một phương pháp join toàn hệ thống là giải pháp thay cho thống kê, index và SQL đúng.

## 31. Khi nào extended statistics không giúp được?

Một số trường hợp:

1. Query chỉ lọc **một cột**, thống kê đơn cột đã đủ.
2. Cột thuộc **hai bảng khác nhau**, muốn ước lượng mối quan hệ liên bảng trực tiếp.
3. Query dùng **range, LIKE hoặc biểu thức** mà functional dependencies không được áp dụng như mong muốn.
4. Điều kiện mâu thuẫn yêu cầu suy luận logic chính xác nhưng dependencies chỉ điều chỉnh xác suất.
5. Cột có phân phối thay đổi nhanh, statistics đã stale.
6. Predicate tham số dẫn đến generic plan không thể tối ưu theo giá trị cụ thể.
7. Query chậm do I/O/network hoặc thiếu index, không chủ yếu vì cardinality estimate.
8. Cột được chỉ định trong statistics không phù hợp với WHERE/GROUP BY đang cần tối ưu.
9. Số liệu có quá nhiều tổ hợp hiếm mà sample không đại diện.
10. Planner có các heuristic/cost settings khác quyết định plan dù estimate đã tốt hơn.

### 31.1. Không tự sửa bằng tạo statistics cho mọi cặp cột

Với bảng có 50 cột, số cặp cột là:

\[
\binom{50}{2} = 1{,}225
\]

Tạo 1.225 statistics objects chỉ vì có thể làm tăng thời gian ANALYZE và công quản trị mà không có bằng chứng lợi ích.

### 31.2. Ưu tiên theo workload

Một vài query quan trọng lọc `country_id</BT> và `country_name</BT> thường xuyên có thể đáng một đối tượng dependencies. Hàng trăm cặp cột không hề được dùng chung thì không có lý do rõ.

## 32. Lỗi và hiểu lầm thường gặp

### 32.1. “Tạo CREATE STATISTICS là planner dùng ngay”

**Sai.** Cần `ANALYZE` để thu thập dữ liệu cho đối tượng mới.

### 32.2. “Extended statistics giống composite index”

**Sai.** Statistics cung cấp ước lượng; index cung cấp access path vật lý.

### 32.3. “dependencies bảo đảm hai cột không thể mâu thuẫn”

**Sai.** Nó không phải constraint và không làm thay logic kiểm tra dữ liệu khi ghi.

### 32.4. “Hai cột correlated nghĩa là có functional dependency hai chiều”

**Sai.** Quan hệ có thể một chiều, ví dụ district xác định province nhưng province không xác định district.

### 32.5. “Một dependency hoàn hảo suy ra WHERE mâu thuẫn luôn estimate 0”

**Sai.** Estimator không phải bộ suy luận constraint đầy đủ và có thể overestimate cặp không phù hợp.

### 32.6. “dependencies xử lý tốt mọi LIKE, range, expression, JOIN”

**Sai.** Có giới hạn cụ thể về clause types và join selectivity.

### 32.7. “ndistinct là thống kê tối ưu mọi WHERE equality”

**Sai.** Nó chủ yếu giúp ước lượng số nhóm/tổ hợp phân biệt trong những ngữ cảnh thích hợp.

### 32.8. “mcv và dependencies là cùng dữ liệu”

**Sai.** Một loại ghi tổ hợp phổ biến/tần suất, một loại mô tả sức mạnh phụ thuộc.

### 32.9. “Có index thì cardinality estimate tự đúng”

**Sai.** Index không bảo đảm planner hiểu phụ thuộc giữa các cột.

### 32.10. “Một plan không đổi chứng minh statistics vô dụng”

**Sai.** Estimated rows có thể cải thiện nhưng lựa chọn access path vẫn hợp lý như cũ.

### 32.11. “ANALYZE cho kết quả chính xác tuyệt đối”

**Sai.** Đây là thống kê ước lượng, thường dựa trên sampling.

### 32.12. “Tăng target sẽ chữa mọi query chậm”

**Sai.** Chỉ hữu ích nếu vấn đề bắt nguồn từ giới hạn độ chi tiết thống kê phù hợp.

### 32.13. “pg_stats.correlation là tương quan giữa hai cột”

**Sai.** Nó liên quan thứ tự vật lý của một cột với bảng, khác extended dependencies.

### 32.14. “Extended stats biến dữ liệu dư thừa thành thiết kế tốt”

**Sai.** Nó không thay chuẩn hóa, constraints, khóa ngoại và quản lý dữ liệu lặp.

### 32.15. “Có thể CREATE STATISTICS một đối tượng trực tiếp trên cột hai bảng”

**Không theo hình thức multivariate statistics thông thường.** Đối tượng được tạo trên một quan hệ; không mô tả toàn bộ joint distribution của hai bảng khác nhau.

### 32.16. “EXPLAIN ANALYZE chỉ xem kế hoạch, không chạy query”

**Sai.** Nó thực sự chạy query. Cần cẩn thận với DML.

### 32.17. “Nếu actual rows=1000 và rows=10, chắc chắn phải tạo stats”

**Chưa chắc.** Cần xác định nguyên nhân, xem index, sampling, predicate và chi phí thực tế trước.

### 32.18. “Tạo statistics trên mọi cột làm optimizer luôn nhanh hơn”

**Sai.** Có chi phí ANALYZE/planning và nhiều đối tượng có thể không mang lại lợi ích.

### 32.19. “Query literal và generic prepared plan luôn chọn cùng kế hoạch”

**Sai.** Giá trị tham số khả kiến ở planning time có thể làm thay đổi ước lượng và lựa chọn plan.

### 32.20. “Nếu statistics stale, index vẫn sẽ luôn cứu được query”

**Sai.** Planner có thể chọn kế hoạch chưa tối ưu vì đánh giá sai số hàng, ngay cả khi access path tốt tồn tại.

## 33. Bài tập thực hành

### Bài 1 — Bài toán nhân xác suất

Một bảng có 200.000 hàng. Cột A có 100 giá trị đều nhau, cột B cũng vậy. Nếu planner giả định độc lập, ước lượng cho `A=7 AND B='X'</BT> là bao nhiêu?

**Gợi ý:** `200000 × 0,01 × 0,01 = 20</BT> hàng.

### Bài 2 — Dependency thực tế

Nếu A=7 luôn đồng nghĩa B='X', thực tế tổ hợp đó có khoảng bao nhiêu hàng trong bài 1?

**Gợi ý:** Khoảng 2.000 hàng nếu A phân bố đều.

### Bài 3 — Độ lệch

Tính hệ số underestimated trong hai bài trên.

**Gợi ý:** `2000 / 20 = 100</BT> lần.

### Bài 4 — Chọn thống kê

Query thường xuyên:

~~~sql
WHERE category_id = 7
  AND category_code = 'CAT-007'
~~~

Loại extended statistics nào đáng thử trước?

**Đáp án:** `dependencies`.

### Bài 5 — Viết CREATE STATISTICS

Viết lệnh tạo dependencies giữa `category_id</BT> và `category_code</BT> trong `extstats_lab.catalog</BT>.

~~~sql
CREATE STATISTICS extstats_lab.my_dep
    (dependencies)
ON category_id, category_code
FROM extstats_lab.catalog;
~~~

### Bài 6 — Sau CREATE

Phải chạy thao tác nào để planner có dữ liệu thống kê mới?

**Đáp án:** `ANALYZE extstats_lab.catalog;`.

### Bài 7 — Kiểm tra actual rows

Lệnh nào vừa trình bày kế hoạch vừa chạy query để xem actual rows?

**Đáp án:** `EXPLAIN (ANALYZE, BUFFERS) SELECT ...;`.

### Bài 8 — Mâu thuẫn

Vì sao `category_id=7 AND category_code='CAT-008'</BT> có thể nhận estimated rows dương dù lab có 0 hàng thực?

**Gợi ý:** Dependency estimator không nhất thiết suy luận điều kiện mâu thuẫn như constraint solver.

### Bài 9 — Phụ thuộc một chiều

Nếu `district_id -> province_id</BT>, liệu `province_id -> district_id</BT> luôn đúng không?

**Đáp án:** Không.

### Bài 10 — ndistinct

Hai cột riêng có 100 giá trị khác nhau nhưng chỉ có 100 cặp hợp lệ. Query GROUP BY cả hai ước lượng số nhóm sai. Nên tạo loại statistics nào?

**Đáp án:** `ndistinct`.

### Bài 11 — Viết ndistinct

~~~sql
CREATE STATISTICS extstats_lab.my_nd
    (ndistinct)
ON category_id, category_code
FROM extstats_lab.catalog;

ANALYZE extstats_lab.catalog;
~~~

### Bài 12 — MCV

Khi những cặp (region,status) có tần suất rất không đều, loại nào có thể hữu ích?

**Đáp án:** `mcv`.

### Bài 13 — MCV vs dependency

Nêu khác nhau giữa mô tả “A quyết định B” và “tổ hợp (A=7,B='X') rất phổ biến”.

**Gợi ý:** Mô hình phụ thuộc vs tần suất của giá trị cụ thể.

### Bài 14 — Composite index

Vì sao CREATE STATISTICS không tự làm giảm số trang đọc của một Seq Scan khi không có access path tốt hơn?

**Gợi ý:** Nó không tạo index, chỉ cải thiện estimate/plan decision.

### Bài 15 — Unique constraint

Nếu category_code cần luôn đúng với category_id, CREATE STATISTICS có đủ bảo vệ không?

**Đáp án:** Không. Cần mô hình dữ liệu/constraint hoặc protocol ghi phù hợp.

### Bài 16 — pg_stats_ext

Viết câu SELECT lấy `statistics_name</BT>, `attnames</BT>, `kinds</BT> và `dependencies</BT>.

**Gợi ý:** Dùng `pg_stats_ext</BT> và WHERE schemaname/tablename.

### Bài 17 — Catalog nội bộ

Hai catalog nào chứa định nghĩa và dữ liệu extended statistics?

**Đáp án:** `pg_statistic_ext` và `pg_statistic_ext_data`.

### Bài 18 — Range

Một query chỉ dùng `category_id BETWEEN 10 AND 20</BT>. Có nên khẳng định dependencies sẽ tự cải thiện cardinality không?

**Gợi ý:** Không; các giới hạn clause type phải được xem xét.

### Bài 19 — JOIN

Có nên bảo đảm extended stats tự tính đúng selectivity cho điều kiện `t1.a=t2.b</BT> giữa hai bảng không?

**Đáp án:** Không; hỗ trợ trực tiếp cho join selectivity còn hạn chế.

### Bài 20 — Correlation

`pg_stats.correlation</BT> của cột A có phải hệ số dependency giữa A và B không?

**Đáp án:** Không.

### Bài 21 — Target

Nếu MCV có quá ít cặp so với phân phối, có thể cân nhắc lệnh gì?

~~~sql
ALTER STATISTICS extstats_lab.catalog_category_mcv
SET STATISTICS 500;

ANALYZE extstats_lab.catalog;
~~~

### Bài 22 — Chi phí target

Vì sao không đặt target rất cao cho mọi statistics?

**Gợi ý:** Tăng chi phí ANALYZE, lưu trữ/planning và không chữa giới hạn khác.

### Bài 23 — Stale stats

Sau nạp thêm 5 triệu hàng với phân phối mới, nên kiểm tra thao tác gì?

**Gợi ý:** ANALYZE/autoanalyze và ước lượng plan mới.

### Bài 24 — Prepared statement

Vì sao EXPLAIN với hằng số có thể khác generic plan của câu SQL parameterized?

**Gợi ý:** Giá trị tham số có/không được biết khi planner chọn plan.

### Bài 25 — Sai lệch và plan

Nếu estimated rows tốt hơn nhưng vẫn Seq Scan, có thể thống kê vẫn đã làm việc không?

**Đáp án:** Có; lựa chọn plan không nhất thiết đổi.

### Bài 26 — Loops

Tại sao phải chú ý `loops</BT> khi so actual rows ở nested loop?

**Gợi ý:** Actual rows được trình bày theo mỗi lần chạy node.

### Bài 27 — DML và EXPLAIN

Có nên chạy EXPLAIN ANALYZE UPDATE trên production chỉ để “xem plan” không?

**Đáp án:** Không khi chưa có kiểm soát; ANALYZE thực thi UPDATE.

### Bài 28 — Statistics object quá rộng

Một đối tượng trên 20 cột có luôn tốt hơn đối tượng trên đúng 2 cột thường lọc cùng nhau không?

**Gợi ý:** Không; chỉ chọn các cột phù hợp workload và giới hạn phiên bản.

### Bài 29 — DROP

Lệnh DROP STATISTICS có xóa hàng trong catalog không?

**Đáp án:** Không; nó xóa metadata statistics, không xóa dữ liệu bảng.

### Bài 30 — Chọn nguyên nhân

Một query chậm vì network truyền 10 triệu hàng cho client. Dependencies có phải công cụ chữa nguyên nhân chính không?

**Gợi ý:** Không; xét kích thước kết quả/pagination/network.

### Bài 31 — Dữ liệu lịch sử

Tenant thay đổi tier qua thời gian. Có thể coi tenant_id -> service_tier là phụ thuộc tuyệt đối trên bảng sự kiện lịch sử không?

**Gợi ý:** Không nhất thiết; một tenant có nhiều tier ở các thời điểm khác nhau.

### Bài 32 — Hai cột từ hai bảng

Có thể định nghĩa một `CREATE STATISTICS</BT> multivariate thông thường trên `orders.country_id</BT> và `countries.code</BT> khác bảng không?

**Đáp án:** Không theo cú pháp một quan hệ của CREATE STATISTICS.

### Bài 33 — Dữ liệu phân phối hiếm

Nếu MCV bỏ sót một cặp cực hiếm, có thể suy ra cặp đó không tồn tại không?

**Đáp án:** Không. MCV không ghi mọi giá trị.

### Bài 34 — Phân tích WHERE

Query có một điều kiện equality trên hai cột phụ thuộc và một điều kiện LIKE. Nên kỳ vọng dependencies sửa được toàn bộ ba điều kiện không?

**Gợi ý:** Không. Cần xem clause nào thực sự được áp dụng và kế hoạch thực tế.

### Bài 35 — Đề xuất quy trình

Một query chậm có estimated rows 20 nhưng actual 5.000 tại base filter. Hãy đề xuất thứ tự điều tra.

**Gợi ý:** Kiểm tra stale stats, predicate/casts, quan hệ cột, CREATE STATISTICS phù hợp, ANALYZE, EXPLAIN lại, sau đó index/JOIN/cost nếu cần.

## 34. Bảng tra cứu nhanh

| Câu hỏi | Câu trả lời |
|---|---|
| Extended statistics dùng để làm gì? | Cải thiện ước lượng phân phối nhiều cột/biểu thức |
| Lệnh tạo | `CREATE STATISTICS ... ON ... FROM ...` |
| Bước sau CREATE | `ANALYZE table` |
| Khi equality predicates bị đánh giá độc lập | Thử `dependencies` |
| Khi số nhóm GROUP BY nhiều cột sai | Thử `ndistinct` |
| Khi tổ hợp giá trị phổ biến lệch mạnh | Thử `mcv` |
| Dependencies có thể một chiều? | Có |
| Có bảo vệ constraint không? | Không |
| Có tạo index không? | Không |
| Có sửa mọi JOIN selectivity không? | Không |
| Có tự giải mâu thuẫn `A=7 AND B='wrong'`? | Không bảo đảm |
| Có giúp mọi LIKE/range không? | Không bảo đảm |
| Xem đối tượng đã tạo | `pg_stats_ext`, `pg_statistic_ext` |
| Xem dữ liệu thống kê | `pg_stats_ext` với quyền phù hợp |
| Định nghĩa catalog | `pg_statistic_ext` |
| Dữ liệu catalog | `pg_statistic_ext_data` |
| Đổi statistics target | `ALTER STATISTICS ... SET STATISTICS ...` |
| Bỏ thống kê | `DROP STATISTICS ...` |
| Đánh giá kế hoạch trước/sau | `EXPLAIN (ANALYZE, BUFFERS)` |
| Cẩn thận với EXPLAIN ANALYZE DML? | Có, nó thực thi lệnh |
| Statistics stale? | ANALYZE/autoanalyze |
| Bảng có cặp cột phụ thuộc hoàn hảo | Dependencies thường hữu ích cho equality |
| Statistics target càng lớn càng tốt? | Không |
| Stats và index có bổ trợ nhau không? | Có |
| pg_stats.correlation là dependency giữa cột? | Không |
| Generic prepared plan có thể khác literal plan? | Có |
| Plan không đổi sau stats có nghĩa thất bại? | Không, kiểm tra estimated rows |
| Đối tượng statistics trên hai bảng? | Không theo dạng CREATE STATISTICS đa cột thông thường |
| Quyết định tối ưu cuối cùng | Dựa trên EXPLAIN, workload và thử nghiệm có kiểm soát |

---

## Kết luận

Extended statistics giúp PostgreSQL hiểu những quan hệ giữa nhiều cột mà **thống kê từng cột riêng lẻ** không thể phản ánh đầy đủ. Khi hai điều kiện WHERE gần như cùng diễn đạt một thông tin, giả định độc lập có thể khiến planner nhân selectivity quá mức và đánh giá số hàng thấp hơn thực tế nhiều lần. **`dependencies`** được thiết kế để cải thiện kiểu ước lượng đó, nhất là với những điều kiện equality đơn giản và cột có phụ thuộc hàm mạnh.

Tuy nhiên, **dependencies không phải giải pháp cho mọi cardinality problem**: nó không phải constraint, không tạo index, không tự chứng minh hai điều kiện mâu thuẫn và có giới hạn với range, LIKE, biểu thức và JOIN. Khi sai lệch nằm ở số nhóm GROUP BY, hãy xem **`ndistinct`**. Khi phân phối những tổ hợp cụ thể bị lệch, hãy xem **`mcv`**.

Quy trình đáng tin cậy là **đo estimated rows và actual rows**, xác định vị trí sai lệch trong plan, kiểm tra quan hệ dữ liệu, tạo loại statistics đúng mục tiêu, **chạy ANALYZE**, rồi đo lại. Một CREATE STATISTICS chỉ có ý nghĩa khi nó phản ánh điều kiện truy vấn thật; nhiều thống kê hơn không tự động đồng nghĩa truy vấn nhanh hơn.

Nắm rõ cách functional dependencies tương tác với planner giúp bạn nhìn thấy nguyên nhân sâu xa của những kế hoạch JOIN/scan/aggregate không hợp lý, thay vì chỉ tăng timeout hoặc ép PostgreSQL dùng một index. Đây là một phần thiết yếu của việc tối ưu truy vấn bằng **thông tin dữ liệu chính xác hơn** chứ không chỉ bằng thêm phần cứng.
