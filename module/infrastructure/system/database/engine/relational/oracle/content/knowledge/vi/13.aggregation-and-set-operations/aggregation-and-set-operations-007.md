# GROUPING, GROUPING_ID và phân biệt dòng tổng với NULL dữ liệu trong Oracle

Khi tạo báo cáo tổng hợp, Oracle có thể sinh thêm dòng subtotal và grand total bằng các phần mở rộng của GROUP BY như ROLLUP, CUBE và GROUPING SETS. Trong những dòng tổng hợp này, một chiều dữ liệu bị loại khỏi cấp nhóm sẽ được hiển thị bằng NULL. Nhưng dữ liệu nguồn cũng có thể chứa NULL thật, chẳng hạn một giao dịch chưa biết khu vực hoặc sản phẩm chưa được phân loại.

Vì vậy, nhìn vào cột kết quả thấy NULL chưa đủ để kết luận đó là “chưa biết dữ liệu” hay “tất cả giá trị”. Oracle cung cấp hai hàm để phân biệt:

- GROUPING(expression) cho biết NULL ở biểu thức nhóm có phải do Oracle tạo ra khi tổng hợp hay không.
- GROUPING_ID(expression, ...) mã hóa trạng thái GROUPING của nhiều biểu thức thành một số nguyên, giúp nhận diện cấp tổng hợp.

Bài học giải thích cách hai hàm hoạt động, cách đọc bitmask của GROUPING_ID, cách đặt nhãn bằng CASE, lọc dòng tổng bằng HAVING và tổ chức kết quả cho báo cáo. Các ví dụ sử dụng một bảng bán hàng nhỏ có cả NULL thật trong dữ liệu.

## 1. Vấn đề: NULL trong dữ liệu và NULL do tổng hợp

Giả sử có bảng SALES với các cột REGION, PRODUCT và AMOUNT. Một số dòng nguồn có thể thiếu khu vực hoặc tên sản phẩm:

| REGION | PRODUCT | AMOUNT |
|---|---|---:|
| North | Laptop | 100 |
| North | Phone | 50 |
| South | Laptop | 80 |
| NULL | Laptop | 30 |
| North | NULL | 20 |

Trong bảng này:

- REGION NULL ở dòng thứ tư là dữ liệu nguồn: giao dịch có doanh thu nhưng chưa biết hoặc chưa ghi nhận khu vực.
- PRODUCT NULL ở dòng thứ năm là dữ liệu nguồn: mặt hàng chưa được xác định.

Bây giờ tạo báo cáo tổng hợp:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount
FROM sales
GROUP BY ROLLUP(region, product);
~~~

ROLLUP tạo nhiều cấp nhóm, bao gồm nhóm chi tiết theo REGION và PRODUCT, subtotal theo REGION và grand total. Oracle dùng NULL ở cột bị loại khỏi cấp nhóm. Kết quả có thể chứa những dòng như:

| REGION | PRODUCT | TOTAL_AMOUNT | Ý nghĩa |
|---|---|---:|---|
| NULL | Laptop | 30 | Dòng chi tiết, REGION NULL trong dữ liệu |
| North | NULL | 20 | Dòng chi tiết, PRODUCT NULL trong dữ liệu |
| North | NULL | 170 | Subtotal của North, PRODUCT được tổng hợp |
| South | NULL | 80 | Subtotal của South, PRODUCT được tổng hợp |
| NULL | NULL | 30 | Subtotal của REGION NULL, PRODUCT được tổng hợp |
| NULL | NULL | 280 | Grand total, cả hai chiều được tổng hợp |

Hai cặp giá trị NULL cho thấy vấn đề:

- North / NULL / 20 là dòng chi tiết có PRODUCT thực sự NULL.
- North / NULL / 170 là subtotal của North, trong đó PRODUCT bị bỏ khỏi cấp nhóm.
- NULL / NULL / 30 là subtotal của khu vực chưa biết.
- NULL / NULL / 280 là grand total.

Chỉ dựa vào REGION và PRODUCT, ứng dụng không thể phân biệt chắc chắn các dòng này. Nếu hiển thị tất cả NULL thành “Tất cả”, báo cáo sẽ biến dữ liệu chưa biết thành tổng hợp. Nếu hiển thị tất cả NULL thành “Chưa xác định”, grand total và subtotal sẽ bị gắn nhãn sai.

Đây chính là mục đích của GROUPING và GROUPING_ID.

## 2. GROUPING: xác định NULL có phải do tổng hợp

### 2.1 Cú pháp

~~~sql
GROUPING(expression)
~~~

GROUPING nhận một biểu thức thuộc danh sách nhóm của GROUP BY mở rộng và trả về:

- 0 nếu giá trị của biểu thức trong dòng kết quả là giá trị nhóm thông thường, bao gồm cả NULL có thật trong dữ liệu nguồn.
- 1 nếu Oracle đã tạo NULL cho biểu thức đó vì biểu thức bị loại khỏi cấp nhóm hiện tại trong ROLLUP, CUBE hoặc GROUPING SETS.

GROUPING trả về NUMBER 0 hoặc 1. Nó không thay đổi giá trị cột; nó cung cấp metadata về nguồn gốc của NULL trong dòng tổng hợp.

### 2.2 Ví dụ với ROLLUP

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product
FROM sales
GROUP BY ROLLUP(region, product)
ORDER BY GROUPING_ID(region, product), region, product;
~~~

Đọc hai cột GROUPING:

| G_REGION | G_PRODUCT | Ý nghĩa |
|---:|---:|---|
| 0 | 0 | Dòng chi tiết; cả REGION và PRODUCT đều là giá trị nhóm, có thể là NULL thật |
| 0 | 1 | REGION vẫn là chiều nhóm; PRODUCT bị tổng hợp thành NULL |
| 1 | 1 | Cả REGION và PRODUCT bị tổng hợp; đây là grand total |

Với ROLLUP(region, product), không có cấp nhóm chỉ theo PRODUCT, nên trạng thái 1 / 0 không được sinh ra bởi cấu trúc ROLLUP này.

Điểm quan trọng: GROUPING(region) không hỏi “REGION có NULL hay không?”. Nó hỏi “NULL ở REGION có phải là NULL do thao tác tổng hợp tạo ra hay không?”.

### 2.3 NULL nguồn trả GROUPING bằng 0

Một dòng chi tiết có REGION NULL trong bảng nguồn vẫn thuộc nhóm chi tiết theo REGION và PRODUCT. Do đó:

~~~sql
GROUPING(region) = 0
~~~

Nếu Oracle sinh subtotal bằng cách bỏ REGION khỏi grouping set, GROUPING(region) trả 1. Hai dòng có cùng giá trị hiển thị NULL nhưng cờ GROUPING khác nhau.

### 2.4 Dùng GROUPING để đặt nhãn

Có thể kết hợp CASE:

~~~sql
SELECT CASE
         WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
         WHEN region IS NULL THEN 'UNKNOWN REGION'
         ELSE region
       END AS region_label,
       CASE
         WHEN GROUPING(product) = 1 THEN 'ALL PRODUCTS'
         WHEN product IS NULL THEN 'UNKNOWN PRODUCT'
         ELSE product
       END AS product_label,
       SUM(amount) AS total_amount
FROM sales
GROUP BY ROLLUP(region, product)
ORDER BY GROUPING_ID(region, product), region, product;
~~~

Thứ tự WHEN là có chủ đích:

1. Kiểm tra GROUPING trước để nhận diện NULL do tổng hợp.
2. Chỉ khi GROUPING bằng 0 mới kiểm tra giá trị nguồn có NULL thật không.
3. Nếu không phải hai trường hợp trên thì hiển thị giá trị dimension.

Nếu đảo hai điều kiện, dòng subtotal có NULL cũng có thể bị gắn nhãn “UNKNOWN REGION” hoặc “UNKNOWN PRODUCT”.

Trong báo cáo đa ngôn ngữ, có thể thay nhãn bằng tiếng Việt:

~~~sql
CASE
  WHEN GROUPING(region) = 1 THEN 'Tất cả khu vực'
  WHEN region IS NULL THEN 'Chưa xác định khu vực'
  ELSE region
END
~~~

Nhãn hiển thị không làm thay đổi NULL gốc trong bảng và cũng không ghi dữ liệu tổng hợp trở lại bảng nguồn.

## 3. GROUPING_ID: mã hóa nhiều cờ GROUPING

### 3.1 Cú pháp và ý nghĩa

~~~sql
GROUPING_ID(expr [, expr] ...)
~~~

GROUPING_ID nhận một hoặc nhiều biểu thức nhóm và trả về một số nguyên đại diện cho vector các giá trị GROUPING tương ứng. Có thể hiểu đây là một bitmask:

- Bit 0 tương ứng với biểu thức cuối cùng trong danh sách đối số.
- Biểu thức đứng trước có trọng số bit cao hơn.
- GROUPING bằng 1 nghĩa là chiều đó bị tổng hợp ở cấp nhóm hiện tại.
- GROUPING bằng 0 nghĩa là chiều đó vẫn tham gia cấp nhóm hiện tại.

Với hai biểu thức:

~~~sql
GROUPING_ID(region, product)
~~~

trạng thái bit được diễn giải theo thứ tự REGION rồi PRODUCT:

| GROUPING(region) | GROUPING(product) | Vector bit | GROUPING_ID(region, product) |
|---:|---:|---|---:|
| 0 | 0 | 00 | 0 |
| 0 | 1 | 01 | 1 |
| 1 | 0 | 10 | 2 |
| 1 | 1 | 11 | 3 |

Với ROLLUP(region, product), các cấp nhóm được tạo ra là:

- (region, product): GROUPING_ID bằng 0.
- (region): GROUPING_ID bằng 1.
- (): GROUPING_ID bằng 3.

Giá trị 2 không xuất hiện trong ROLLUP này vì không có grouping set chỉ gồm PRODUCT.

### 3.2 Ví dụ ROLLUP với GROUPING_ID

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       GROUPING_ID(region, product) AS grouping_level
FROM sales
GROUP BY ROLLUP(region, product)
ORDER BY grouping_level, region, product;
~~~

GROUPING_ID giúp báo cáo có một cột mã cấp nhóm:

| GROUPING_LEVEL | Cấp nhóm trong ROLLUP(region, product) |
|---:|---|
| 0 | Chi tiết theo region và product |
| 1 | Subtotal theo region |
| 3 | Grand total |

Nhiều dòng có thể có cùng GROUPING_ID. Ví dụ tất cả tổ hợp REGION/PRODUCT ở cấp chi tiết đều có ID 0. Vì vậy GROUPING_ID là **mã cấp tổng hợp**, không phải khóa duy nhất của dòng.

### 3.3 Thứ tự đối số ảnh hưởng giá trị

Hai biểu thức sau không nhất thiết cho cùng mã:

~~~sql
GROUPING_ID(region, product)
GROUPING_ID(product, region)
~~~

Với trạng thái GROUPING(region)=1 và GROUPING(product)=0:

- GROUPING_ID(region, product) có vector 10, giá trị 2.
- GROUPING_ID(product, region) có vector 01, giá trị 1.

Do đó, thứ tự đối số là một phần của hợp đồng báo cáo. Khi lưu mã cấp tổng hợp, tài liệu hóa thứ tự biểu thức để code phía ứng dụng không diễn giải sai.

### 3.4 GROUPING_ID cho ba chiều

Với REGION, PRODUCT và CHANNEL:

~~~sql
GROUPING_ID(region, product, channel)
~~~

có ba bit, nên các trạng thái có thể biểu diễn từ 0 đến 7:

| GROUPING(region) | GROUPING(product) | GROUPING(channel) | Vector | GROUPING_ID |
|---:|---:|---:|---|---:|
| 0 | 0 | 0 | 000 | 0 |
| 0 | 0 | 1 | 001 | 1 |
| 0 | 1 | 0 | 010 | 2 |
| 0 | 1 | 1 | 011 | 3 |
| 1 | 0 | 0 | 100 | 4 |
| 1 | 0 | 1 | 101 | 5 |
| 1 | 1 | 0 | 110 | 6 |
| 1 | 1 | 1 | 111 | 7 |

Không phải mọi GROUP BY mở rộng đều tạo đủ tám trạng thái. Các grouping set thực tế quyết định những cấp nào xuất hiện; bảng trên mô tả khả năng mã hóa của ba cờ.

### 3.5 Đặt nhãn cấp báo cáo bằng GROUPING_ID

Với ROLLUP hai chiều:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid,
       CASE GROUPING_ID(region, product)
         WHEN 0 THEN 'DETAIL'
         WHEN 1 THEN 'REGION SUBTOTAL'
         WHEN 3 THEN 'GRAND TOTAL'
         ELSE 'OTHER GROUPING LEVEL'
       END AS row_type
FROM sales
GROUP BY ROLLUP(region, product)
ORDER BY gid, region, product;
~~~

Với CUBE hai chiều, có thể có thêm mã 2:

- 0: chi tiết REGION + PRODUCT.
- 1: subtotal theo REGION.
- 2: subtotal theo PRODUCT.
- 3: grand total.

Không dùng CASE của ROLLUP cho CUBE mà bỏ qua mã 2 nếu truy vấn có thể được đổi từ ROLLUP sang CUBE.

## 4. ROLLUP, CUBE và GROUPING SETS tạo các cấp nhóm nào?

GROUPING và GROUPING_ID thường được dùng cùng các phần mở rộng GROUP BY. Để đọc kết quả đúng, cần hiểu nguồn gốc các grouping set.

### 4.1 GROUP BY ROLLUP

~~~sql
GROUP BY ROLLUP(region, product)
~~~

Tạo các grouping set tương đương:

~~~sql
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    ()
)
~~~

Đây là chuỗi tổng hợp từ chi tiết đến tổng lớn:

~~~text
(REGION, PRODUCT)  chi tiết
        |
        v
(REGION)           subtotal theo khu vực
        |
        v
()                 grand total
~~~

Với ba chiều:

~~~sql
GROUP BY ROLLUP(region, product, channel)
~~~

các cấp là (region, product, channel), (region, product), (region), và (). ROLLUP bỏ dần các biểu thức từ phải sang trái.

### 4.2 GROUP BY CUBE

~~~sql
GROUP BY CUBE(region, product)
~~~

Tạo mọi tổ hợp grouping set:

~~~sql
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    (product),
    ()
)
~~~

Với hai chiều, CUBE có bốn cấp:

| Grouping set | GROUPING(region) | GROUPING(product) | GROUPING_ID(region, product) |
|---|---:|---:|---:|
| (region, product) | 0 | 0 | 0 |
| (region) | 0 | 1 | 1 |
| (product) | 1 | 0 | 2 |
| () | 1 | 1 | 3 |

CUBE hữu ích khi báo cáo cần subtotal theo từng chiều và grand total. Số grouping set tăng theo hàm mũ của số chiều: với n biểu thức, cube có thể tạo 2^n grouping set. Vì vậy cần cân nhắc số chiều và lượng dữ liệu.

### 4.3 GROUP BY GROUPING SETS

GROUPING SETS cho phép chỉ định chính xác các cấp nhóm cần:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM sales
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    ()
);
~~~

Truy vấn này tạo chi tiết, subtotal theo REGION và grand total, giống các cấp của ROLLUP hai chiều. Nếu muốn subtotal theo PRODUCT thay vì theo REGION:

~~~sql
GROUP BY GROUPING SETS (
    (region, product),
    (product),
    ()
)
~~~

GROUPING_ID vẫn phân biệt được cấp nhóm, nhưng mã sẽ phụ thuộc thứ tự đối số của chính GROUPING_ID, không phụ thuộc thứ tự dòng kết quả.

### 4.4 Vì sao cần GROUPING_ID khi có nhiều grouping set?

Khi báo cáo có nhiều chiều, chỉ nhìn một cột NULL khó nhận diện cấp nhóm. GROUPING_ID nén trạng thái của nhiều chiều vào một mã, có thể dùng để:

- Đặt nhãn cấp dòng.
- Chọn format hoặc style cho subtotal và grand total ở tầng báo cáo.
- Lọc một cấp tổng hợp trong HAVING.
- Sắp xếp các cấp nhóm theo một quy tắc rõ.
- Truyền metadata cấp nhóm sang ứng dụng mà không suy luận từ NULL.

Nó không thay thế các cột dimension, cũng không thay thế khóa nhóm của dòng chi tiết.

## 5. Phân biệt NULL nguồn và NULL do tổng hợp bằng ví dụ đầy đủ

### 5.1 Tạo bảng minh họa

Trong schema lab riêng, tạo bảng:

~~~sql
CREATE TABLE lab_sales_grouping (
    sale_id  NUMBER PRIMARY KEY,
    region   VARCHAR2(30),
    product  VARCHAR2(30),
    amount   NUMBER(12,2) NOT NULL
);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO lab_sales_grouping VALUES (1, 'North', 'Laptop', 100);
INSERT INTO lab_sales_grouping VALUES (2, 'North', 'Phone', 50);
INSERT INTO lab_sales_grouping VALUES (3, 'South', 'Laptop', 80);
INSERT INTO lab_sales_grouping VALUES (4, NULL, 'Laptop', 30);
INSERT INTO lab_sales_grouping VALUES (5, 'North', NULL, 20);
COMMIT;
~~~

Hai NULL nguồn được cố ý đưa vào:

- SALE_ID 4 có REGION NULL.
- SALE_ID 5 có PRODUCT NULL.

### 5.2 Truy vấn ROLLUP có cả GROUPING và GROUPING_ID

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
ORDER BY gid, region, product;
~~~

Kết quả về mặt nhóm (thứ tự dòng cụ thể do ORDER BY quyết định):

| REGION | PRODUCT | TOTAL_AMOUNT | G_REGION | G_PRODUCT | GID | Diễn giải |
|---|---|---:|---:|---:|---:|---|
| NULL | Laptop | 30 | 0 | 0 | 0 | Chi tiết, khu vực nguồn NULL |
| North | NULL | 20 | 0 | 0 | 0 | Chi tiết, sản phẩm nguồn NULL |
| North | Laptop | 100 | 0 | 0 | 0 | Chi tiết |
| North | Phone | 50 | 0 | 0 | 0 | Chi tiết |
| South | Laptop | 80 | 0 | 0 | 0 | Chi tiết |
| NULL | NULL | 30 | 0 | 1 | 1 | Subtotal của nhóm REGION nguồn NULL |
| North | NULL | 170 | 0 | 1 | 1 | Subtotal của North |
| South | NULL | 80 | 0 | 1 | 1 | Subtotal của South |
| NULL | NULL | 280 | 1 | 1 | 3 | Grand total |

Hai dòng NULL / NULL được phân biệt bởi GID và các cờ:

- Subtotal khu vực NULL: G_REGION=0, G_PRODUCT=1, GID=1.
- Grand total: G_REGION=1, G_PRODUCT=1, GID=3.

Hai dòng North / NULL cũng có thể phân biệt:

- Dòng chi tiết có PRODUCT nguồn NULL: G_PRODUCT=0, GID=0.
- Subtotal của North: G_PRODUCT=1, GID=1.

Đây là lý do không nên viết báo cáo chỉ dựa trên điều kiện REGION IS NULL hoặc PRODUCT IS NULL để đoán dòng tổng.

### 5.3 Gắn nhãn không nhập nhằng

~~~sql
SELECT CASE
         WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
         WHEN region IS NULL THEN 'UNKNOWN REGION'
         ELSE region
       END AS region_label,
       CASE
         WHEN GROUPING(product) = 1 THEN 'ALL PRODUCTS'
         WHEN product IS NULL THEN 'UNKNOWN PRODUCT'
         ELSE product
       END AS product_label,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
ORDER BY gid, region, product;
~~~

Kết quả hiển thị:

| REGION_LABEL | PRODUCT_LABEL | TOTAL_AMOUNT | GID |
|---|---|---:|---:|
| UNKNOWN REGION | Laptop | 30 | 0 |
| North | UNKNOWN PRODUCT | 20 | 0 |
| North | Laptop | 100 | 0 |
| North | Phone | 50 | 0 |
| South | Laptop | 80 | 0 |
| UNKNOWN REGION | ALL PRODUCTS | 30 | 1 |
| North | ALL PRODUCTS | 170 | 1 |
| South | ALL PRODUCTS | 80 | 1 |
| ALL REGIONS | ALL PRODUCTS | 280 | 3 |

Nhãn UNKNOWN chỉ xuất hiện cho NULL nguồn. Nhãn ALL chỉ xuất hiện khi GROUPING xác nhận chiều bị tổng hợp.

### 5.4 Vì sao không dùng NVL để phân biệt?

Một cách thường thấy:

~~~sql
NVL(region, 'ALL REGIONS')
~~~

không đủ chính xác. Nó biến cả NULL nguồn lẫn NULL subtotal thành cùng một chuỗi. Nếu muốn thay nhãn, phải kiểm tra GROUPING trước:

~~~sql
CASE
  WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
  WHEN region IS NULL THEN 'UNKNOWN REGION'
  ELSE region
END
~~~

NVL vẫn hữu ích cho NULL nguồn khi nghiệp vụ muốn thay thế, nhưng không phải công cụ nhận diện nguồn gốc NULL do ROLLUP/CUBE.

## 6. GROUPING_ID với CUBE

### 6.1 Truy vấn CUBE

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY CUBE(region, product)
ORDER BY gid, region, product;
~~~

Với CUBE(region, product), ngoài các nhóm chi tiết, Oracle tạo:

- Subtotal theo REGION (PRODUCT được tổng hợp), GID 1.
- Subtotal theo PRODUCT (REGION được tổng hợp), GID 2.
- Grand total, GID 3.

Ví dụ các dòng subtotal theo PRODUCT sẽ có REGION NULL và GROUPING(region)=1, còn PRODUCT vẫn là giá trị nhóm và GROUPING(product)=0. Nếu PRODUCT nguồn NULL, nó vẫn có GROUPING(product)=0.

### 6.2 Đặt nhãn bốn cấp

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       CASE GROUPING_ID(region, product)
         WHEN 0 THEN 'DETAIL'
         WHEN 1 THEN 'REGION SUBTOTAL'
         WHEN 2 THEN 'PRODUCT SUBTOTAL'
         WHEN 3 THEN 'GRAND TOTAL'
       END AS grouping_level
FROM lab_sales_grouping
GROUP BY CUBE(region, product)
ORDER BY GROUPING_ID(region, product), region, product;
~~~

CASE này phù hợp với CUBE hai chiều. Nếu đổi sang ROLLUP, mã 2 không xuất hiện; nếu đổi danh sách dimension hoặc thứ tự đối số, phải cập nhật cách diễn giải mã.

### 6.3 CUBE có thể tăng số dòng đáng kể

Với n chiều, CUBE có thể tạo 2^n grouping sets. Ví dụ 5 chiều có 32 grouping sets, 8 chiều có 256. Số dòng kết quả thực tế còn phụ thuộc số tổ hợp giá trị ở từng cấp, nhưng lượng nhóm cần tổng hợp có thể tăng đáng kể.

Chỉ dùng CUBE khi báo cáo thực sự cần các tổ hợp subtotal đó. Nếu chỉ cần vài cấp cụ thể, GROUPING SETS có thể rõ ràng và tiết kiệm hơn.

## 7. GROUPING SETS và mã hóa cấp nhóm

### 7.1 Chỉ yêu cầu những cấp cần thiết

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    ()
)
ORDER BY gid, region, product;
~~~

Các mã giống ROLLUP hai chiều: 0, 1 và 3. Nhưng GROUPING SETS cho phép chỉ định chính xác grouping set, không bắt buộc tạo chuỗi prefix như ROLLUP.

Ví dụ chỉ cần chi tiết và tổng theo PRODUCT, không cần subtotal theo REGION:

~~~sql
GROUP BY GROUPING SETS (
    (region, product),
    (product),
    ()
)
~~~

### 7.2 GROUPING_ID cho cấp nhóm tùy chỉnh

Giả sử truy vấn có các dimension REGION, PRODUCT và CHANNEL:

~~~sql
SELECT region,
       product,
       channel,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product, channel) AS gid
FROM sales_by_channel
GROUP BY GROUPING SETS (
    (region, product, channel),
    (region, product),
    (region),
    (channel),
    ()
);
~~~

GROUPING_ID tạo mã theo các cờ của ba biểu thức, dù các grouping set không bao gồm mọi tổ hợp. Khi thiết kế CASE cho gid, cần liệt kê đúng các grouping set truy vấn thực sự tạo ra.

### 7.3 Tránh lặp grouping set không cần thiết

Nếu GROUPING SETS chỉ định cùng một grouping set nhiều lần, kết quả có thể có các nhóm trùng theo cấu trúc grouping. Trong tình huống cần xử lý grouping set trùng lặp, phải hiểu rõ yêu cầu và cơ chế phân biệt nhóm. GROUPING_ID chỉ mã hóa trạng thái grouping của biểu thức; nó không phải mã duy nhất cho từng bản ghi kết quả và không thay thế các cơ chế xử lý duplicate group.

## 8. Lọc và sắp xếp theo cấp tổng hợp

### 8.1 HAVING để giữ subtotal hoặc grand total

GROUPING có thể được dùng trong HAVING để chọn các cấp nhóm:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
HAVING GROUPING(product) = 1;
~~~

Điều kiện này giữ các dòng mà PRODUCT bị tổng hợp, tức subtotal theo REGION và grand total trong ROLLUP hai chiều. Nó không giữ dòng chi tiết chỉ vì PRODUCT nguồn NULL, bởi GROUPING(product) ở dòng đó bằng 0.

Chỉ lấy grand total:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
HAVING GROUPING_ID(region, product) = 3;
~~~

Chỉ lấy các dòng chi tiết:

~~~sql
HAVING GROUPING_ID(region, product) = 0
~~~

### 8.2 Lọc một cấp subtotal cụ thể

Với CUBE:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount
FROM lab_sales_grouping
GROUP BY CUBE(region, product)
HAVING GROUPING_ID(region, product) = 2;
~~~

GID 2 tương ứng GROUPING(region)=1 và GROUPING(product)=0, tức tổng theo PRODUCT, không phân tách REGION.

### 8.3 ORDER BY theo GROUPING_ID

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
ORDER BY gid, region, product;
~~~

Sắp xếp theo gid giúp nhóm chi tiết (0), subtotal (1) và grand total (3) thành các khối. Trong từng cấp, region/product tiếp tục được sắp xếp. Thứ tự NULL cụ thể còn phụ thuộc NULLS FIRST/LAST và quy tắc ORDER BY; có thể khai báo rõ:

~~~sql
ORDER BY gid,
         region NULLS LAST,
         product NULLS LAST;
~~~

ORDER BY là yêu cầu sắp xếp kết quả. Không dựa vào thứ tự ngẫu nhiên mà GROUP BY hoặc execution plan đang trả về.

### 8.4 Lọc ở WHERE khác lọc cấp nhóm ở HAVING

WHERE lọc dòng nguồn trước khi tổng hợp:

~~~sql
WHERE amount > 0
~~~

HAVING lọc nhóm sau khi tổng hợp, có thể dựa vào GROUPING:

~~~sql
HAVING GROUPING_ID(region, product) IN (0, 3)
~~~

Nếu muốn loại subtotal theo REGION nhưng vẫn giữ chi tiết và grand total, HAVING phù hợp. Không thể dùng WHERE để kiểm tra GROUPING của dòng tổng hợp trước khi các dòng đó được tạo.

## 9. GROUPING và GROUPING_ID không phải các hàm đếm

### 9.1 GROUPING không đếm NULL

GROUPING(region) trả 0 hoặc 1 dựa trên việc REGION có bị tổng hợp khỏi grouping set hay không. Nó không trả số lượng NULL nguồn, không đếm dòng và không kiểm tra xem cột có NULL hay không.

Muốn đếm NULL nguồn ở bảng gốc, có thể dùng:

~~~sql
SELECT COUNT(*) AS total_rows,
       COUNT(region) AS known_region_rows,
       COUNT(*) - COUNT(region) AS null_region_rows
FROM lab_sales_grouping;
~~~

Đây là truy vấn trên dữ liệu nguồn, không có subtotal. COUNT(region) bỏ qua NULL, còn COUNT(*) đếm mọi dòng.

### 9.2 GROUPING_ID không phải khóa dòng

Ví dụ nhiều tổ hợp chi tiết đều có GID 0. Do đó không thể dùng GROUPING_ID một mình làm primary key hoặc định danh duy nhất cho kết quả.

Để nhận diện một dòng báo cáo, cần kết hợp:

- Các giá trị dimension.
- GROUPING_ID hoặc các cờ GROUPING.
- Có thể thêm khóa nhóm/khóa nguồn nếu báo cáo cần định danh chi tiết.

### 9.3 GROUPING_ID không phải GROUP_ID

Oracle còn có hàm GROUP_ID trong ngữ cảnh GROUP BY mở rộng. GROUP_ID và GROUPING_ID là hai hàm khác nhau:

- GROUPING_ID mã hóa trạng thái tổng hợp của các biểu thức nhóm.
- GROUP_ID phân biệt các nhóm trùng được tạo ra bởi các grouping set trùng lặp.

Đừng thay hai hàm cho nhau. Trong báo cáo thông thường cần phân biệt NULL nguồn với subtotal, GROUPING/GROUPING_ID là các hàm phù hợp.

## 10. Kết hợp với nhiều dimension và biểu thức nhóm

### 10.1 Ba dimension

Ví dụ bảng có REGION, PRODUCT, CHANNEL:

~~~sql
SELECT region,
       product,
       channel,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       GROUPING(channel) AS g_channel,
       GROUPING_ID(region, product, channel) AS gid
FROM sales_by_channel
GROUP BY ROLLUP(region, product, channel)
ORDER BY gid, region, product, channel;
~~~

ROLLUP tạo các cấp:

1. Chi tiết theo REGION, PRODUCT, CHANNEL: GID 0.
2. Subtotal theo REGION, PRODUCT: CHANNEL bị tổng hợp, GID 1.
3. Subtotal theo REGION: PRODUCT và CHANNEL bị tổng hợp, GID 3.
4. Grand total: cả ba bị tổng hợp, GID 7.

### 10.2 Biểu thức nhóm

Nếu GROUP BY dùng biểu thức, GROUPING/GROUPING_ID phải tham chiếu biểu thức nhóm tương ứng:

~~~sql
SELECT TRUNC(sold_at, 'MM') AS sales_month,
       region,
       SUM(amount) AS total_amount,
       GROUPING(TRUNC(sold_at, 'MM')) AS g_month,
       GROUPING(region) AS g_region,
       GROUPING_ID(TRUNC(sold_at, 'MM'), region) AS gid
FROM sales
GROUP BY ROLLUP(TRUNC(sold_at, 'MM'), region);
~~~

Ở đây dimension thời gian là biểu thức đầu tháng, không phải toàn bộ giá trị SOLD_AT. Dòng tổng hợp có thể được phân biệt với NULL nguồn của REGION bằng GROUPING(region).

Đối với biểu thức phức tạp, nên giữ cách viết nhất quán giữa SELECT, GROUP BY và các hàm GROUPING. Alias trong SELECT không thay thế tùy ý biểu thức gốc ở mọi vị trí.

### 10.3 GROUPING trên biểu thức không phải grouping expression

GROUPING chỉ có ý nghĩa cho biểu thức tham gia GROUP BY mở rộng. Không dùng GROUPING trên một cột không thuộc grouping key rồi mong Oracle suy ra nguồn gốc NULL. Nếu cần đánh dấu dimension, đưa dimension đó vào GROUP BY thích hợp và dùng chính biểu thức nhóm làm đối số.

## 11. Thiết kế nhãn báo cáo an toàn

### 11.1 Phân biệt ba trạng thái

Một dimension có thể có ít nhất ba trạng thái hiển thị:

1. Có giá trị cụ thể, ví dụ North.
2. NULL trong dữ liệu nguồn, ví dụ chưa biết khu vực.
3. NULL do tổng hợp, nghĩa là mọi khu vực trong cấp tổng.

CASE nên biểu diễn đủ ba trạng thái:

~~~sql
CASE
  WHEN GROUPING(region) = 1 THEN 'ALL REGIONS'
  WHEN region IS NULL THEN 'UNKNOWN REGION'
  ELSE region
END
~~~

Nếu nghiệp vụ còn phân biệt “không áp dụng” với “chưa nhập”, cần có mã trạng thái hoặc cột nguồn riêng. GROUPING chỉ phân biệt NULL do tổng hợp với giá trị NULL trong dữ liệu; nó không tự giải thích vì sao dữ liệu nguồn bị NULL.

### 11.2 Không thay NULL bằng chuỗi sentinel trong bảng nguồn

Một số thiết kế dùng giá trị giả như 'ALL' hoặc 'UNKNOWN' để thay NULL. Cách này có thể xung đột với dữ liệu hợp lệ, làm sai tổng hợp và gây khó khăn khi đổi ngôn ngữ hiển thị.

Tốt hơn là giữ NULL theo semantics dữ liệu và dùng GROUPING/CASE ở lớp truy vấn để trình bày:

- NULL nguồn: UNKNOWN REGION.
- NULL do tổng hợp: ALL REGIONS.

Nếu nghiệp vụ yêu cầu phân loại NULL nguồn chi tiết hơn, lưu thêm trạng thái hoặc dimension key rõ ràng.

### 11.3 Đừng chỉ dựa vào chuỗi nhãn để xử lý logic

Ứng dụng có thể dùng GID làm metadata cấp nhóm và dùng nhãn chỉ cho hiển thị. Không nên gửi chuỗi 'GRAND TOTAL' rồi sau đó dùng so sánh văn bản để quyết định dòng tổng, vì nhãn có thể đổi ngôn ngữ hoặc wording.

Ví dụ result set có:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS grouping_level,
       CASE GROUPING_ID(region, product)
         WHEN 0 THEN 'DETAIL'
         WHEN 1 THEN 'REGION_SUBTOTAL'
         WHEN 3 THEN 'GRAND_TOTAL'
       END AS row_label
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product);
~~~

Ứng dụng có thể dựa vào GROUPING_LEVEL để định dạng, còn ROW_LABEL phục vụ con người đọc.

## 12. Những lưu ý về kết quả và hiệu năng

### 12.1 ROLLUP/CUBE làm tăng số nhóm

Mỗi grouping set tạo một cấp tổng hợp. CUBE có thể tạo 2^n grouping sets cho n chiều; nhiều chiều có thể làm số nhóm và chi phí tính toán tăng nhanh. Chỉ tạo các cấp báo cáo thực sự cần.

### 12.2 GROUPING_ID có chi phí diễn giải thấp nhưng không miễn phí toàn truy vấn

Tính GROUPING_ID là cách biểu diễn trạng thái grouping. Chi phí lớn thường đến từ đọc dữ liệu, tạo nhóm, sort/hash và các grouping set được yêu cầu. Tối ưu phải xem toàn bộ truy vấn và plan, không chỉ đếm số lần gọi GROUPING_ID.

### 12.3 Đặt điều kiện nguồn ở WHERE, điều kiện nhóm ở HAVING

Ví dụ chỉ tổng hợp dữ liệu một năm:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
WHERE amount > 0
GROUP BY ROLLUP(region, product)
HAVING GROUPING_ID(region, product) IN (0, 1, 3);
~~~

WHERE giảm tập dòng nguồn trước khi tổng hợp; HAVING chọn các cấp nhóm sau khi tổng hợp. Ví dụ HAVING ở trên giữ cả ba cấp của ROLLUP nên chủ yếu minh họa vị trí sử dụng; có thể đổi danh sách mã để chỉ giữ các cấp cần báo cáo.

### 12.4 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN cho biết kế hoạch dự kiến, không phải số liệu runtime. Với dữ liệu lớn, cần xem actual execution plan, cardinality, sort/hash operation, I/O, memory và số grouping set.

## 13. Lỗi thường gặp

| Lỗi/ngộ nhận | Vì sao sai | Cách xử lý |
|---|---|---|
| Thấy REGION NULL là dòng grand total | NULL có thể có trong dữ liệu nguồn hoặc do tổng hợp | Dùng GROUPING(region) |
| Dùng NVL(region, 'ALL') để đặt nhãn | Gộp NULL nguồn và NULL subtotal thành một nhãn | CASE GROUPING trước, rồi kiểm tra region IS NULL |
| GROUPING(region)=1 nghĩa là region nguồn NULL | Nó báo dimension bị tổng hợp khỏi cấp nhóm | Đọc GROUPING như metadata grouping |
| GROUPING_ID là mã duy nhất mỗi dòng | Nhiều nhóm chi tiết có cùng mã 0 | Kết hợp dimension values và metadata |
| Đổi thứ tự đối số GROUPING_ID nhưng giữ nguyên CASE | Bit trọng số thay đổi | Tài liệu hóa thứ tự biểu thức |
| Dùng CASE chỉ có mã 0, 1, 3 cho CUBE | CUBE hai chiều còn có cấp chỉ theo PRODUCT, mã 2 | Liệt kê mọi grouping set thực tế |
| Dùng GROUPING cho cột không thuộc GROUP BY | Không có metadata grouping hợp lệ cho biểu thức đó | Dùng đúng grouping expression |
| Lọc subtotal trong WHERE | WHERE chạy trước khi tạo nhóm | Dùng HAVING |
| CUBE nhiều chiều mà không tính số cấp | Số grouping set tăng theo 2^n | Chọn GROUPING SETS nếu chỉ cần một số cấp |
| Nghĩ GID 3 luôn là grand total trong mọi truy vấn | Mã phụ thuộc số và thứ tự đối số | Đọc bitmask và grouping set của query |
| Nhãn ALL/UNKNOWN được lưu vào cột nguồn | Làm lẫn dữ liệu và presentation | Giữ dữ liệu nguồn, tạo nhãn trong SELECT |

## 14. Bài tập thực hành

### Bài 1: nhận diện NULL nguồn

Chạy:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product);
~~~

Tìm dòng chi tiết có REGION NULL và giải thích vì sao G_REGION bằng 0.

Gợi ý: REGION NULL nằm trong dữ liệu nguồn; nó vẫn là giá trị của dimension ở grouping set chi tiết.

### Bài 2: nhận diện subtotal của khu vực NULL

Trong kết quả ROLLUP, tìm dòng subtotal có REGION NULL và PRODUCT NULL, tổng bằng 30. Vì sao nó khác dòng chi tiết REGION NULL / PRODUCT Laptop?

Gợi ý: Subtotal có G_REGION=0 và G_PRODUCT=1; dòng chi tiết có cả hai bằng 0.

### Bài 3: tìm grand total

Viết truy vấn chỉ trả grand total:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount
FROM lab_sales_grouping
GROUP BY ROLLUP(region, product)
HAVING GROUPING_ID(region, product) = 3;
~~~

Kết quả là 280 trong dữ liệu lab.

### Bài 4: so sánh thứ tự bit

Với một dòng có GROUPING(region)=1 và GROUPING(product)=0, hãy tính:

~~~sql
GROUPING_ID(region, product)
GROUPING_ID(product, region)
~~~

Gợi ý: Lần lượt là 2 và 1 vì biểu thức cuối cùng tương ứng bit thấp nhất.

### Bài 5: nhận diện các cấp CUBE

Chạy:

~~~sql
SELECT region,
       product,
       SUM(amount) AS total_amount,
       GROUPING_ID(region, product) AS gid
FROM lab_sales_grouping
GROUP BY CUBE(region, product)
ORDER BY gid, region, product;
~~~

Liệt kê dòng chi tiết, subtotal theo REGION, subtotal theo PRODUCT và grand total.

Gợi ý: Các mã lần lượt là 0, 1, 2 và 3.

### Bài 6: đặt nhãn đúng

Viết CASE cho REGION:

~~~sql
CASE
  WHEN GROUPING(region) = 1 THEN 'Tất cả khu vực'
  WHEN region IS NULL THEN 'Chưa xác định khu vực'
  ELSE region
END
~~~

Giải thích vì sao phải kiểm tra GROUPING trước IS NULL.

### Bài 7: chỉ lấy dòng chi tiết và grand total

Viết HAVING để giữ cấp GID 0 và 3:

~~~sql
HAVING GROUPING_ID(region, product) IN (0, 3)
~~~

Kiểm tra rằng subtotal theo REGION có GID 1 bị loại.

### Bài 8: mở rộng ba chiều

Thêm CHANNEL vào bảng lab khác và dùng GROUPING_ID(region, product, channel). Tạo bảng ánh xạ mã 0 đến 7 theo vector bit. Sau đó chọn GROUPING SETS chỉ tạo chi tiết, subtotal theo REGION/PRODUCT và grand total.

Gợi ý: Không cần mọi mã 0..7 xuất hiện; grouping sets quyết định các cấp thực tế.

## 15. Dọn môi trường lab

Các bảng lab là đối tượng do người học tạo trong schema thực hành. Nếu muốn xóa sau khi học, chỉ thực hiện với đúng bảng đã tạo và sau khi xác nhận không còn dữ liệu cần giữ. DDL như DROP TABLE có implicit commit; không dựa vào ROLLBACK để khôi phục.

~~~sql
-- Chỉ chạy trong schema lab của bạn nếu thực sự muốn dọn bảng:
DROP TABLE lab_sales_grouping;
~~~

Không xóa hoặc sửa SYS.DUAL, bảng nghiệp vụ hay đối tượng schema khác để thực hành GROUPING.

## 16. Quy trình đọc một dòng tổng hợp

Khi ứng dụng nhận một dòng từ báo cáo ROLLUP/CUBE, hãy đọc theo trình tự:

1. Xem GROUPING_ID và thứ tự biểu thức đã dùng để hiểu cấp tổng hợp.
2. Dùng từng GROUPING(expression) để xác định dimension nào bị bỏ khỏi grouping set.
3. Với dimension có GROUPING bằng 0, nếu giá trị là NULL thì đó là NULL nguồn trong nhóm.
4. Với dimension có GROUPING bằng 1, NULL là ký hiệu cho chiều được tổng hợp.
5. Tạo nhãn hiển thị bằng CASE, không ghi đè dữ liệu nguồn.
6. Nếu lọc hoặc sắp xếp theo cấp, dùng GROUPING_ID trong HAVING/ORDER BY theo hợp đồng mã đã tài liệu hóa.

Ví dụ một dòng có REGION=NULL, PRODUCT=NULL:

| G_REGION | G_PRODUCT | GID | Diễn giải |
|---:|---:|---:|---|
| 0 | 0 | 0 | Dòng chi tiết mà cả hai dimension nguồn đều NULL |
| 0 | 1 | 1 | Subtotal của nhóm REGION nguồn NULL |
| 1 | 0 | 2 | Subtotal của nhóm PRODUCT nguồn NULL |
| 1 | 1 | 3 | Grand total |

Không phải mọi dòng trên đều nhất thiết xuất hiện trong cùng một truy vấn. Chúng minh họa bốn trạng thái grouping có thể mã hóa cho hai chiều khi các grouping set tương ứng được yêu cầu.

## 17. Tổng kết

Trong báo cáo Oracle dùng ROLLUP, CUBE hoặc GROUPING SETS, NULL có thể đến từ hai nguồn: dữ liệu gốc thật sự thiếu giá trị hoặc Oracle tạo NULL để biểu diễn một dimension bị tổng hợp khỏi cấp nhóm. **GROUPING(expression)** phân biệt hai trường hợp: 0 là giá trị nhóm bình thường, kể cả NULL nguồn; 1 là NULL do tổng hợp. **GROUPING_ID(expr, ...)** mã hóa nhiều cờ GROUPING thành một số nguyên dạng bitmask, hữu ích để nhận diện và xử lý cấp nhóm.

Hãy nhớ:

- Luôn kiểm tra GROUPING trước khi kiểm tra IS NULL trong CASE tạo nhãn.
- Đọc GROUPING_ID theo đúng thứ tự đối số; biểu thức cuối cùng ứng với bit thấp nhất.
- GID nhận diện cấp grouping, không phải khóa duy nhất của dòng.
- ROLLUP tạo các cấp theo chuỗi; CUBE tạo mọi tổ hợp; GROUPING SETS cho phép chỉ định các cấp cần.
- Dùng HAVING để lọc cấp nhóm, ORDER BY để sắp xếp kết quả, và giữ NULL nguồn trong dữ liệu theo đúng semantics.

Khi hiểu rõ nguồn gốc của NULL, báo cáo subtotal và grand total sẽ không còn nhầm với dữ liệu thiếu, đồng thời ứng dụng có thể hiển thị các nhãn “Chưa xác định”, “Tất cả” và “Tổng cộng” một cách chính xác.
