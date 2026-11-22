# ROLLUP, CUBE và GROUPING SETS

Trong Oracle Database, GROUP BY thông thường tạo một hàng kết quả cho mỗi nhóm dữ liệu. Nhưng báo cáo nghiệp vụ thường cần nhiều cấp tổng hợp cùng lúc: doanh thu theo khu vực và sản phẩm, tổng doanh thu của từng khu vực, tổng theo từng sản phẩm và tổng toàn công ty. Nếu viết riêng một câu GROUP BY cho từng cấp rồi ghép bằng UNION ALL, SQL sẽ dài và dễ lặp lại logic.

Oracle cung cấp ba mở rộng quan trọng của GROUP BY:

- **ROLLUP**: tạo các mức tổng phụ theo một thứ tự phân cấp, từ chi tiết đến tổng của các tiền tố nhóm và tổng toàn bộ.
- **CUBE**: tạo các tổ hợp tổng hợp cho mọi tập con của các chiều được chọn.
- **GROUPING SETS**: chỉ định chính xác những nhóm nào cần tính.

Hai hàm đi cùng thường xuyên là **GROUPING** và **GROUPING_ID**. Chúng giúp phân biệt NULL thật trong dữ liệu với NULL được Oracle tạo ra để biểu diễn một mức tổng phụ. **GROUP_ID** có thể nhận diện những nhóm bị tạo trùng khi danh sách grouping sets chứa cùng một nhóm nhiều lần.

Bài học tập trung vào cú pháp, kết quả từng loại, cách sắp xếp và lọc các cấp tổng hợp, cách dùng trong báo cáo, cùng ví dụ SQL có thể chạy trong schema thực hành.

## 1. Từ GROUP BY thông thường đến nhiều cấp tổng hợp

Giả sử bảng doanh thu có các chiều:

- **REGION**: khu vực bán hàng.
- **PRODUCT**: nhóm sản phẩm.
- **CHANNEL**: kênh bán.
- **AMOUNT**: doanh thu.

GROUP BY thông thường:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
GROUP BY region, product;
~~~

trả về doanh thu cho từng cặp khu vực và sản phẩm. Nếu muốn thêm tổng theo khu vực, tổng theo sản phẩm và tổng toàn công ty, ta cần các nhóm khác nhau:

~~~text
Chi tiết:
  North / Laptop
  North / Phone
  South / Laptop
  South / Phone

Tổng theo khu vực:
  North / tất cả sản phẩm
  South / tất cả sản phẩm

Tổng theo sản phẩm:
  Tất cả khu vực / Laptop
  Tất cả khu vực / Phone

Tổng toàn bộ:
  Tất cả khu vực / tất cả sản phẩm
~~~

Ba mở rộng GROUP BY giúp biểu diễn những cấp này trong một câu truy vấn. Về mặt kết quả, mỗi cấp tổng hợp là một **grouping set**: tập các biểu thức dùng để tạo nhóm.

Ví dụ:

| Grouping set | Ý nghĩa |
| --- | --- |
| (REGION, PRODUCT) | Doanh thu chi tiết theo khu vực và sản phẩm |
| (REGION) | Tổng theo khu vực |
| (PRODUCT) | Tổng theo sản phẩm |
| () | Tổng toàn bộ dữ liệu |

Dấu ngoặc rỗng **()** là grouping set không có chiều phân nhóm; nó tạo một nhóm tổng hợp trên toàn bộ tập hàng sau WHERE.

## 2. ROLLUP: tổng hợp theo cấp phân cấp

Cú pháp:

~~~sql
GROUP BY ROLLUP (expr1, expr2, ..., exprN)
~~~

ROLLUP tạo các grouping sets theo thứ tự từ đầy đủ đến các tiền tố ngắn dần, rồi đến tổng toàn bộ.

Với hai biểu thức:

~~~sql
GROUP BY ROLLUP (region, product)
~~~

tương đương về các nhóm được tạo với:

~~~sql
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    ()
)
~~~

Với ba biểu thức:

~~~sql
GROUP BY ROLLUP (region, product, channel)
~~~

các grouping sets là:

1. (REGION, PRODUCT, CHANNEL)
2. (REGION, PRODUCT)
3. (REGION)
4. ()

Số grouping sets do một ROLLUP có N biểu thức tạo ra là **N + 1**.

### 2.1. Khi nào ROLLUP phù hợp?

ROLLUP thích hợp khi các chiều tạo thành một thứ tự phân cấp mà báo cáo muốn tổng hợp lần lượt từ chi tiết lên cấp cao hơn. Ví dụ:

~~~text
Năm
  └── Quý
       └── Tháng
            └── Ngày
~~~

Truy vấn:

~~~sql
SELECT nam,
       quy,
       thang,
       SUM(doanh_thu) AS tong_doanh_thu
FROM doanh_thu_thang
GROUP BY ROLLUP (nam, quy, thang);
~~~

tạo doanh thu theo năm/quý/tháng, tổng theo năm/quý và tổng toàn bộ. Lưu ý thứ tự biểu thức có ý nghĩa: ROLLUP(NAM, QUY, THANG) không giống ROLLUP(THANG, QUY, NAM).

### 2.2. ROLLUP hai chiều

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product);
~~~

Kết quả gồm:
- Các cặp REGION và PRODUCT.
- Tổng PRODUCT bên trong từng REGION, tức tổng theo REGION.
- Tổng toàn bộ.

ROLLUP không tự tạo tổng theo PRODUCT trên tất cả REGION, vì PRODUCT không phải một tiền tố độc lập trong thứ tự (REGION, PRODUCT). Nếu cần thêm cấp đó, dùng CUBE hoặc GROUPING SETS.

### 2.3. ROLLUP ba chiều

~~~sql
SELECT region,
       product,
       channel,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product, channel);
~~~

Các mức được tạo:

| Mức | Các cột phân nhóm | Ý nghĩa |
| --- | --- | --- |
| Chi tiết | REGION, PRODUCT, CHANNEL | Theo từng khu vực, sản phẩm và kênh |
| Tổng kênh | REGION, PRODUCT | Gộp mọi kênh trong từng cặp khu vực/sản phẩm |
| Tổng sản phẩm | REGION | Gộp mọi sản phẩm và kênh trong từng khu vực |
| Tổng chung | Không có | Toàn bộ dữ liệu |

ROLLUP chỉ tạo các tiền tố theo danh sách. Nó không tạo một nhóm tổng riêng theo CHANNEL trên toàn bộ REGION và PRODUCT.

## 3. CUBE: mọi tổ hợp của các chiều

Cú pháp:

~~~sql
GROUP BY CUBE (expr1, expr2, ..., exprN)
~~~

CUBE tạo grouping set cho **mọi tập con** của các biểu thức được đưa vào, kể cả tập đầy đủ và tập rỗng.

Với hai biểu thức:

~~~sql
GROUP BY CUBE (region, product)
~~~

các grouping sets gồm:

- (REGION, PRODUCT)
- (REGION)
- (PRODUCT)
- ()

Đây là bốn tổ hợp, tương ứng 2².

Với ba biểu thức:

~~~sql
GROUP BY CUBE (region, product, channel)
~~~

có 2³ = **8 grouping sets**:

| Grouping set | Ý nghĩa |
| --- | --- |
| (REGION, PRODUCT, CHANNEL) | Chi tiết cả ba chiều |
| (REGION, PRODUCT) | Tổng theo khu vực và sản phẩm |
| (REGION, CHANNEL) | Tổng theo khu vực và kênh |
| (PRODUCT, CHANNEL) | Tổng theo sản phẩm và kênh |
| (REGION) | Tổng theo khu vực |
| (PRODUCT) | Tổng theo sản phẩm |
| (CHANNEL) | Tổng theo kênh |
| () | Tổng toàn bộ |

Với N biểu thức, CUBE có thể tạo **2^N grouping sets**. Số tổ hợp tăng rất nhanh: 5 chiều tạo 32 nhóm cấu trúc, 10 chiều tạo 1.024. Mỗi grouping set có thể sinh nhiều nhóm dữ liệu thực tế, nên CUBE trên nhiều chiều có cardinality lớn có thể tốn tài nguyên đáng kể.

### 3.1. Khi nào CUBE phù hợp?

CUBE phù hợp với phân tích đa chiều khi người dùng cần nhìn tổng hợp theo nhiều hướng khác nhau:

- Doanh thu theo khu vực.
- Doanh thu theo sản phẩm.
- Doanh thu theo kênh.
- Doanh thu theo khu vực và sản phẩm.
- Doanh thu theo sản phẩm và kênh.
- Doanh thu toàn bộ.

Ví dụ:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
GROUP BY CUBE (region, product);
~~~

Truy vấn tạo cả tổng theo REGION và tổng theo PRODUCT. Đây là điểm khác với ROLLUP(REGION, PRODUCT).

### 3.2. CUBE không có nghĩa là sắp xếp theo thứ tự chiều

CUBE tạo các grouping sets, nhưng **không cam kết thứ tự hàng trả về**. Thứ tự các nhóm trong kết quả cần được quy định riêng bằng ORDER BY. Cũng không nên dựa vào thứ tự mà một công cụ SQL hiển thị trong lần chạy thử.

## 4. GROUPING SETS: chỉ định chính xác cấp tổng hợp

Cú pháp:

~~~sql
GROUP BY GROUPING SETS (
    (expr_a, expr_b),
    (expr_a),
    (expr_b),
    ()
)
~~~

GROUPING SETS cho phép chỉ định trực tiếp các tập biểu thức cần tổng hợp. Nó không tự thêm những cấp trung gian ngoài danh sách.

Ví dụ:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    ()
);
~~~

Truy vấn chỉ tạo:
- Chi tiết theo REGION và PRODUCT.
- Tổng theo REGION.
- Tổng toàn bộ.

Nó **không tạo tổng theo PRODUCT** vì (PRODUCT) không có trong danh sách.

### 4.1. GROUPING SETS tránh tạo những tổng không cần thiết

Nếu báo cáo chỉ cần:
- Doanh thu theo tháng và khu vực.
- Doanh thu theo khu vực.
- Tổng toàn bộ.

có thể viết:

~~~sql
SELECT thang,
       region,
       SUM(amount) AS revenue
FROM sales_by_month
GROUP BY GROUPING SETS (
    (thang, region),
    (region),
    ()
);
~~~

Không cần CUBE(THANG, REGION), vì CUBE sẽ thêm cả grouping set (THANG), có thể không phục vụ báo cáo.

### 4.2. Thứ tự grouping set không phải thứ tự hiển thị

Dù liệt kê grouping sets theo một thứ tự nhất định, kết quả cuối cùng vẫn không có thứ tự được bảo đảm nếu thiếu ORDER BY. Danh sách GROUPING SETS mô tả **những cách tạo nhóm**, không phải một hợp đồng sắp xếp các hàng.

### 4.3. So sánh ba cấu trúc

| Tiêu chí | ROLLUP | CUBE | GROUPING SETS |
| --- | --- | --- | --- |
| Cách tạo nhóm | Các tiền tố từ đầy đủ đến rỗng | Mọi tập con của các chiều | Đúng các tập được liệt kê |
| Thích hợp | Phân cấp | Phân tích đa chiều | Báo cáo có yêu cầu cụ thể |
| Số nhóm cấu trúc | N + 1 | 2^N | Số grouping set được khai báo |
| Có tổng toàn bộ mặc định | Có | Có | Chỉ khi liệt kê () |
| Có tổng từng chiều đơn lẻ | Chỉ theo tiền tố phù hợp | Có | Chỉ khi liệt kê |
| Kiểm soát đầu ra | Theo thứ tự chiều | Bao phủ mọi tổ hợp | Chính xác nhất |

## 5. GROUPING: phân biệt NULL dữ liệu và NULL tổng phụ

Một hàng tổng phụ thường hiển thị NULL ở những cột đã được gộp. Nhưng dữ liệu nguồn cũng có thể chứa NULL thật. Chỉ nhìn giá trị cột không thể biết NULL đó mang ý nghĩa nào.

Ví dụ, REGION của một giao dịch có thể NULL vì không xác định khu vực. Trong khi đó, hàng tổng toàn bộ do ROLLUP tạo cũng có REGION = NULL vì không phân nhóm theo REGION. Hai hàng có cùng giá trị hiển thị nhưng ý nghĩa khác nhau.

Hàm **GROUPING(expr)** giải quyết vấn đề này:

- Trả **0** nếu biểu thức đang là một phần của grouping set, kể cả giá trị dữ liệu thực tế của nó là NULL.
- Trả **1** nếu biểu thức bị loại khỏi grouping set và NULL được tạo ra để biểu diễn mức tổng hợp.

Cú pháp:

~~~sql
GROUPING(expr)
~~~

Ví dụ:

~~~sql
SELECT region,
       product,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product);
~~~

Diễn giải:
- Chi tiết theo REGION/PRODUCT: G_REGION = 0, G_PRODUCT = 0.
- Tổng theo REGION: G_REGION = 0, G_PRODUCT = 1.
- Tổng toàn bộ: G_REGION = 1, G_PRODUCT = 1.
- Một giao dịch có REGION NULL nhưng vẫn là nhóm chi tiết: G_REGION = 0, không phải 1.

**GROUPING không kiểm tra dữ liệu cột có NULL hay không.** Nó kiểm tra cột có bị gộp khỏi grouping set hiện tại hay không.

### 5.1. Vì sao IS NULL không đủ để nhận diện hàng tổng?

Giả sử kết quả:

| REGION | PRODUCT | REVENUE |
| --- | --- | ---: |
| NULL | TABLET | 25 |
| NULL | NULL | 25 |
| NULL | NULL | 425 |

Hai hàng cuối cùng đều có REGION và PRODUCT hiển thị NULL, nhưng một hàng có thể là tổng theo REGION NULL, hàng còn lại là tổng toàn bộ. Nếu dữ liệu còn có nhóm REGION/PRODUCT thực sự NULL, số hàng cùng hiển thị NULL có thể nhiều hơn.

Dùng GROUPING để nhận diện:

~~~sql
SELECT region,
       product,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product);
~~~

Có thể hiển thị nhãn:

~~~sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'TAT CA KHU VUC'
        WHEN region IS NULL THEN 'KHONG XAC DINH KHU VUC'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(product) = 1 THEN 'TAT CA SAN PHAM'
        WHEN product IS NULL THEN 'KHONG XAC DINH SAN PHAM'
        ELSE product
    END AS product_label,
    SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product);
~~~

Ở đây cần kiểm tra GROUPING trước, rồi mới xét NULL thật. Nếu đảo thứ tự, hàng tổng hợp có NULL do Oracle tạo ra có thể bị gắn nhãn “không xác định” sai ý nghĩa.

## 6. GROUPING_ID: mã hóa nhiều cờ GROUPING

Khi có nhiều chiều, việc xuất từng cờ GROUPING có thể dài. **GROUPING_ID(expr1, expr2, ...)** trả về một số đại diện cho tổ hợp các bit GROUPING của các biểu thức.

Cú pháp:

~~~sql
GROUPING_ID(expr1 [, expr2 ...])
~~~

Mỗi biểu thức có một cờ GROUPING:
- 0: biểu thức có tham gia grouping set hiện tại.
- 1: biểu thức đã được gộp.

GROUPING_ID ghép các cờ theo thứ tự đối số thành một bit vector rồi trả số tương ứng. Với hai đối số REGION, PRODUCT, có thể hiểu như sau:

| GROUPING(REGION) | GROUPING(PRODUCT) | Bit | GROUPING_ID(REGION, PRODUCT) |
| ---: | ---: | --- | ---: |
| 0 | 0 | 00 | 0 |
| 0 | 1 | 01 | 1 |
| 1 | 0 | 10 | 2 |
| 1 | 1 | 11 | 3 |

Ví dụ:

~~~sql
SELECT region,
       product,
       GROUPING_ID(region, product) AS grouping_level,
       SUM(amount) AS revenue
FROM sales
GROUP BY CUBE (region, product)
ORDER BY grouping_level, region, product;
~~~

GROUPING_ID giúp:
- Nhận diện cấp tổng hợp bằng một giá trị số.
- Lọc đúng loại subtotal trong HAVING hoặc query block ngoài.
- Gắn mã cấp tổng hợp vào dữ liệu báo cáo/API.
- Sắp xếp các cấp tổng hợp theo ý muốn.

### 6.1. Thứ tự đối số ảnh hưởng mã

GROUPING_ID(REGION, PRODUCT) không giống GROUPING_ID(PRODUCT, REGION), vì vị trí bit gắn với thứ tự biểu thức truyền vào. Khi ứng dụng lưu mã grouping level hoặc dùng nó trong CASE, phải giữ thứ tự đối số ổn định.

Với nhiều biểu thức, không nên tự đoán giá trị mã. Hãy liệt kê các cờ GROUPING, lập bảng bit tương ứng và kiểm tra bằng truy vấn nhỏ.

### 6.2. GROUPING_ID phải dùng biểu thức thuộc GROUP BY

Nếu nhóm theo một biểu thức:

~~~sql
SELECT TRUNC(order_date, 'MM') AS month_start,
       GROUPING(TRUNC(order_date, 'MM')) AS g_month,
       SUM(amount) AS revenue
FROM orders
GROUP BY ROLLUP (TRUNC(order_date, 'MM'));
~~~

Biểu thức trong GROUPING phải tương ứng với biểu thức được dùng trong GROUP BY. Không thay bằng GROUPING(ORDER_DATE) chỉ vì ORDER_DATE là cột nguồn; grouping đang được thực hiện theo kết quả TRUNC(ORDER_DATE,'MM').

## 7. GROUP_ID: nhận diện grouping set bị lặp

GROUPING SETS cho phép khai báo cùng một grouping set nhiều lần. Điều này có thể tạo các nhóm kết quả trùng nhau về khóa nhóm và aggregate.

**GROUP_ID()** trả một số nhận diện bản sao của nhóm được tạo bởi các grouping sets trùng:
- Nhóm đầu tiên trong tập nhóm trùng nhận 0.
- Những bản sao tiếp theo nhận số 1, 2, ...

Ví dụ cố ý khai báo grouping set chi tiết hai lần:

~~~sql
SELECT region,
       product,
       GROUP_ID() AS duplicate_group,
       SUM(amount) AS revenue
FROM sales
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    (region, product),
    ()
)
ORDER BY duplicate_group, region, product;
~~~

Các nhóm chi tiết theo REGION/PRODUCT được tạo từ hai grouping set giống nhau. GROUP_ID phân biệt lần xuất hiện. Nếu mục tiêu là loại bỏ bản sao, có thể dùng:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
GROUP BY GROUPING SETS (
    (region, product),
    (region),
    (region, product),
    ()
)
HAVING GROUP_ID() = 0;
~~~

Tuy nhiên, giải pháp tốt hơn thường là **không khai báo grouping set trùng ngay từ đầu**. GROUP_ID hữu ích khi cấu trúc grouping được tạo động hoặc khi cần chẩn đoán một danh sách grouping phức tạp. Nó không phải công cụ thay thế DISTINCT cho mọi loại kết quả.

## 8. Kết hợp ROLLUP, CUBE và GROUPING SETS với các chiều ghép

Oracle hỗ trợ **composite columns**: một nhóm nhiều biểu thức được đặt trong ngoặc để được coi như một đơn vị trong một số grouping operation.

Ví dụ:

~~~sql
SELECT region,
       product,
       channel,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP ((region, product), channel);
~~~

Ở đây (REGION, PRODUCT) được coi là một đơn vị tổng hợp; ROLLUP tạo:
- (REGION, PRODUCT, CHANNEL)
- (REGION, PRODUCT)
- ()

Nó không tạo riêng (REGION) hoặc (PRODUCT). Điều này hữu ích khi báo cáo coi cặp REGION/PRODUCT là một cấp không được tách nhỏ.

Một ví dụ với CUBE:

~~~sql
SELECT region,
       product,
       channel,
       SUM(amount) AS revenue
FROM sales
GROUP BY CUBE ((region, product), channel);
~~~

Hai đơn vị grouping là cặp (REGION, PRODUCT) và CHANNEL, nên CUBE tạo bốn tổ hợp:
- (REGION, PRODUCT, CHANNEL)
- (REGION, PRODUCT)
- (CHANNEL)
- ()

Khi dùng composite columns, phải hiểu **đơn vị grouping** trước khi đếm số grouping sets. CUBE trên hai đơn vị tạo 2² = 4 nhóm cấu trúc, dù cặp đầu chứa hai cột.

## 9. WHERE, HAVING và lọc cấp tổng hợp

WHERE và HAVING hoạt động ở các giai đoạn khác nhau:

- **WHERE** lọc hàng nguồn trước khi GROUP BY tạo nhóm.
- **HAVING** lọc nhóm sau khi tổng hợp.
- GROUPING và GROUPING_ID giúp điều kiện HAVING nhận diện cấp subtotal/grand total.

Ví dụ:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
WHERE amount > 0
GROUP BY ROLLUP (region, product)
HAVING SUM(amount) >= 100;
~~~

WHERE bỏ các giao dịch không dương trước khi tổng hợp. HAVING giữ những nhóm có tổng doanh thu ít nhất 100, bao gồm cả các mức tổng phụ nếu thỏa điều kiện.

### 9.1. Chỉ lấy tổng theo khu vực, bỏ chi tiết và grand total

Với ROLLUP(REGION, PRODUCT), GROUPING(PRODUCT)=1 ở hàng tổng theo REGION và cả grand total. Để chỉ lấy subtotal khu vực:

~~~sql
SELECT region,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product)
HAVING GROUPING(region) = 0
   AND GROUPING(product) = 1;
~~~

Điều kiện:
- REGION chưa bị gộp: đây là một khu vực cụ thể hoặc giá trị NULL thật.
- PRODUCT đã bị gộp: hàng là subtotal theo khu vực.

### 9.2. Chỉ lấy grand total

~~~sql
SELECT SUM(amount) AS total_revenue
FROM sales
GROUP BY ROLLUP (region, product)
HAVING GROUPING_ID(region, product) = 3;
~~~

Với hai biểu thức theo đúng thứ tự REGION, PRODUCT, mã 3 đại diện cả hai biểu thức đã được gộp.

Có thể dùng GROUPING(region)=1 và GROUPING(product)=1 thay cho mã nếu muốn điều kiện dễ đọc hơn.

### 9.3. WHERE có thể làm thay đổi cả grand total

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
WHERE region = 'NORTH'
GROUP BY ROLLUP (region, product);
~~~

Câu này tính các mức tổng hợp chỉ từ giao dịch NORTH. Grand total của kết quả cũng chỉ là doanh thu NORTH, không phải toàn bộ doanh thu công ty.

Nếu báo cáo cần chi tiết NORTH nhưng grand total toàn công ty, không thể đơn giản đặt WHERE REGION='NORTH' rồi kỳ vọng ROLLUP giữ dữ liệu đã lọc. Cần thiết kế các grouping set/biểu thức điều kiện hoặc query block riêng để thể hiện rõ tập dữ liệu của từng cấp.

### 9.4. HAVING lọc từng nhóm tổng hợp

~~~sql
SELECT region,
       product,
       GROUPING_ID(region, product) AS gid,
       SUM(amount) AS revenue
FROM sales
GROUP BY CUBE (region, product)
HAVING SUM(amount) >= 100;
~~~

HAVING áp dụng trên mỗi nhóm do CUBE tạo. Một subtotal theo REGION có thể qua điều kiện trong khi nhóm chi tiết nhỏ hơn bị loại. Nếu muốn giữ grand total bất kể doanh thu, có thể kết hợp điều kiện với GROUPING_ID:

~~~sql
HAVING SUM(amount) >= 100
    OR GROUPING_ID(region, product) = 3
~~~

## 10. ORDER BY cho kết quả có nhiều cấp tổng hợp

ROLLUP, CUBE và GROUPING SETS không bảo đảm thứ tự trả về. Hơn nữa, cột NULL trong subtotal có thể bị nhầm với NULL thật nếu chỉ sắp theo giá trị dimension.

Ví dụ:

~~~sql
SELECT region,
       product,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product)
ORDER BY GROUPING(region),
         region NULLS LAST,
         GROUPING(product),
         product NULLS LAST;
~~~

Thứ tự:
1. Nhóm chưa gộp REGION đứng trước hàng grand total.
2. Trong mỗi REGION, các nhóm chi tiết PRODUCT đứng trước subtotal của REGION.
3. Giá trị NULL thật được xử lý theo NULLS LAST.
4. Hàng tổng toàn bộ được nhận diện bằng GROUPING(REGION)=1 và nằm sau.

Nếu cần thứ tự báo cáo tùy chỉnh, có thể dùng CASE trên GROUPING_ID hoặc GROUPING:

~~~sql
ORDER BY
    CASE GROUPING_ID(region, product)
        WHEN 0 THEN 1
        WHEN 1 THEN 2
        WHEN 3 THEN 3
        ELSE 4
    END,
    region NULLS LAST,
    product NULLS LAST;
~~~

Với CUBE có cả subtotal theo PRODUCT (GROUPING_ID=2), CASE phải định nghĩa cả cấp đó. Không dùng mã GROUPING_ID từ một thứ tự biểu thức khác với thứ tự đang khai báo.

## 11. Bộ dữ liệu mẫu để thực hành

Các ví dụ sau dùng bảng sandbox riêng. Chạy trong schema có quyền CREATE TABLE, INSERT và SELECT. Dữ liệu có một hàng REGION NULL thật để thấy cách GROUPING phân biệt giá trị nguồn với hàng subtotal.

### 11.1. Tạo bảng

~~~sql
CREATE TABLE sales_group_demo (
    sale_id NUMBER(6)
        CONSTRAINT pk_sales_group_demo PRIMARY KEY,
    region  VARCHAR2(30 CHAR),
    product VARCHAR2(30 CHAR),
    channel VARCHAR2(20 CHAR),
    amount  NUMBER(12,2) NOT NULL
);
~~~

### 11.2. Nạp dữ liệu

~~~sql
INSERT INTO sales_group_demo VALUES
    (1, 'NORTH', 'LAPTOP', 'ONLINE', 100);

INSERT INTO sales_group_demo VALUES
    (2, 'NORTH', 'LAPTOP', 'STORE', 50);

INSERT INTO sales_group_demo VALUES
    (3, 'NORTH', 'PHONE', 'ONLINE', 80);

INSERT INTO sales_group_demo VALUES
    (4, 'SOUTH', 'LAPTOP', 'ONLINE', 70);

INSERT INTO sales_group_demo VALUES
    (5, 'SOUTH', 'PHONE', 'STORE', 60);

INSERT INTO sales_group_demo VALUES
    (6, 'SOUTH', 'PHONE', 'ONLINE', 40);

INSERT INTO sales_group_demo VALUES
    (7, NULL, 'TABLET', 'ONLINE', 25);

COMMIT;
~~~

Tổng dữ liệu nguồn là **425**:
- NORTH: 230.
- SOUTH: 170.
- REGION NULL: 25.
- LAPTOP: 220.
- PHONE: 180.
- TABLET: 25.

### 11.3. GROUP BY thông thường

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY region, product
ORDER BY region NULLS LAST, product;
~~~

Kết quả chi tiết:

| REGION | PRODUCT | REVENUE |
| --- | --- | ---: |
| NORTH | LAPTOP | 150 |
| NORTH | PHONE | 80 |
| SOUTH | LAPTOP | 70 |
| SOUTH | PHONE | 100 |
| NULL | TABLET | 25 |

Chỉ có các cặp REGION/PRODUCT; chưa có subtotal hoặc grand total.

### 11.4. ROLLUP theo khu vực và sản phẩm

~~~sql
SELECT region,
       product,
       GROUPING(region) AS g_region,
       GROUPING(product) AS g_product,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY ROLLUP (region, product)
ORDER BY GROUPING(region),
         region NULLS LAST,
         GROUPING(product),
         product NULLS LAST;
~~~

Các nhóm tổng hợp mong đợi:

| REGION | PRODUCT | G_REGION | G_PRODUCT | REVENUE | Ý nghĩa |
| --- | --- | ---: | ---: | ---: | --- |
| NORTH | LAPTOP | 0 | 0 | 150 | Chi tiết |
| NORTH | PHONE | 0 | 0 | 80 | Chi tiết |
| NORTH | NULL | 0 | 1 | 230 | Tổng NORTH |
| SOUTH | LAPTOP | 0 | 0 | 70 | Chi tiết |
| SOUTH | PHONE | 0 | 0 | 100 | Chi tiết |
| SOUTH | NULL | 0 | 1 | 170 | Tổng SOUTH |
| NULL | TABLET | 0 | 0 | 25 | Chi tiết có REGION thật là NULL |
| NULL | NULL | 0 | 1 | 25 | Tổng của REGION NULL |
| NULL | NULL | 1 | 1 | 425 | Grand total |

Ba hàng cuối có REGION hiển thị NULL ở hai trường hợp khác nhau. Cặp cờ GROUPING giúp xác định:
- (0,0): NULL thuộc dữ liệu chi tiết.
- (0,1): subtotal theo REGION, kể cả REGION thật là NULL.
- (1,1): grand total.

### 11.5. CUBE theo khu vực và sản phẩm

~~~sql
SELECT region,
       product,
       GROUPING_ID(region, product) AS gid,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY CUBE (region, product)
ORDER BY gid,
         region NULLS LAST,
         product NULLS LAST;
~~~

CUBE tạo các nhóm chi tiết, subtotal theo REGION, subtotal theo PRODUCT và grand total. Các tổng theo PRODUCT:

| REGION | PRODUCT | GID | REVENUE | Ý nghĩa |
| --- | --- | ---: | ---: | --- |
| NULL | LAPTOP | 2 | 220 | Tổng LAPTOP mọi khu vực |
| NULL | PHONE | 2 | 180 | Tổng PHONE mọi khu vực |
| NULL | TABLET | 2 | 25 | Tổng TABLET mọi khu vực |
| NULL | NULL | 3 | 425 | Grand total |

Các hàng REGION NULL có GID=2 là subtotal theo PRODUCT, không phải nhóm dữ liệu REGION NULL. Nhóm chi tiết REGION NULL/TABLET có GID=0. GROUPING_ID làm rõ sự khác nhau.

### 11.6. GROUPING SETS chỉ chọn ba cấp

~~~sql
SELECT region,
       product,
       GROUPING_ID(region, product) AS gid,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY GROUPING SETS (
    (region, product),
    (product),
    ()
)
ORDER BY gid,
         region NULLS LAST,
         product NULLS LAST;
~~~

Kết quả gồm:
- Chi tiết theo REGION/PRODUCT.
- Tổng theo PRODUCT trên mọi khu vực.
- Grand total.

Không có subtotal theo REGION vì grouping set (REGION) không được liệt kê.

### 11.7. ROLLUP ba chiều

~~~sql
SELECT region,
       product,
       channel,
       GROUPING_ID(region, product, channel) AS gid,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY ROLLUP (region, product, channel)
ORDER BY gid,
         region NULLS LAST,
         product NULLS LAST,
         channel NULLS LAST;
~~~

Các cấp được tạo là:
- REGION/PRODUCT/CHANNEL.
- REGION/PRODUCT.
- REGION.
- Grand total.

GROUPING_ID giúp phân biệt cấp tổng hợp. Với ba đối số, mỗi cờ GROUPING đóng góp một bit; giá trị cụ thể phụ thuộc thứ tự REGION, PRODUCT, CHANNEL.

### 11.8. Lọc riêng tổng theo khu vực

~~~sql
SELECT region,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY ROLLUP (region, product)
HAVING GROUPING(region) = 0
   AND GROUPING(product) = 1
ORDER BY region NULLS LAST;
~~~

Kết quả gồm:
- NORTH: 230.
- SOUTH: 170.
- REGION NULL: 25.

Grand total bị loại vì GROUPING(REGION)=1. Các nhóm chi tiết bị loại vì GROUPING(PRODUCT)=0.

### 11.9. Dọn bảng thực hành

~~~sql
DROP TABLE sales_group_demo PURGE;
~~~

Chỉ xóa bảng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP TABLE là DDL có quy tắc implicit commit; PURGE bỏ qua recycle bin theo hành vi thông thường.

## 12. ROLLUP/CUBE/GROUPING SETS và UNION ALL

Nhiều cấp tổng hợp có thể được viết bằng nhiều câu SELECT rồi ghép bằng UNION ALL:

~~~sql
SELECT region, product, SUM(amount) AS revenue
FROM sales
GROUP BY region, product

UNION ALL

SELECT region, CAST(NULL AS VARCHAR2(30)) AS product,
       SUM(amount) AS revenue
FROM sales
GROUP BY region

UNION ALL

SELECT CAST(NULL AS VARCHAR2(30)) AS region,
       CAST(NULL AS VARCHAR2(30)) AS product,
       SUM(amount) AS revenue
FROM sales;
~~~

Đây là một cách biểu diễn các grouping sets (REGION, PRODUCT), (REGION), (). Nhưng có một số điểm cần lưu ý:

- Mỗi nhánh có thể lặp lại logic FROM/WHERE và có thể khiến dữ liệu nguồn được truy cập nhiều lần.
- Phải CAST NULL về kiểu phù hợp để các nhánh UNION tương thích.
- UNION ALL giữ các hàng trùng, đúng với tính chất grouping sets; UNION sẽ loại trùng và có thể làm thay đổi kết quả.
- Các hàng NULL tổng phụ vẫn cần cờ nhận diện nếu dữ liệu nguồn có NULL thật.
- Optimizer có thể tối ưu các dạng truy vấn khác nhau; không khẳng định ROLLUP luôn nhanh hơn UNION ALL hoặc luôn chỉ quét bảng một lần.

Khi logic là nhiều cấp tổng hợp trên cùng một tập dữ liệu, GROUPING SETS thường diễn đạt trực tiếp hơn. Khi các cấp có điều kiện nguồn khác nhau, UNION ALL hoặc query block riêng có thể rõ ràng hơn.

## 13. Hiệu năng và lựa chọn số chiều

ROLLUP, CUBE và GROUPING SETS không miễn phí. Mỗi grouping set có thể tạo nhiều nhóm thực tế; dữ liệu lớn và chiều có cardinality cao có thể làm tăng CPU, PGA, TEMP và thời gian tổng hợp.

### 13.1. ROLLUP thường ít nhóm cấu trúc hơn CUBE

Với 5 biểu thức:
- ROLLUP tạo 6 grouping sets.
- CUBE tạo 32 grouping sets.

Với 10 biểu thức:
- ROLLUP tạo 11 grouping sets.
- CUBE tạo 1.024 grouping sets.

Nếu báo cáo chỉ cần chi tiết, tổng theo khu vực và tổng chung, dùng GROUPING SETS hoặc ROLLUP phù hợp hơn CUBE toàn bộ chiều.

### 13.2. Cardinality của từng chiều quan trọng

Một grouping set theo REGION có thể tạo vài chục nhóm; grouping set theo CUSTOMER_ID có thể tạo hàng triệu nhóm. Khi CUBE nhiều chiều định danh có cardinality cao, số nhóm đầu ra và bộ nhớ cần thiết có thể tăng mạnh.

Trước khi dùng CUBE:
- Xác định những chiều thực sự cần phân tích.
- Đánh giá số giá trị khác nhau của từng chiều.
- Tránh đưa khóa chi tiết như transaction ID vào CUBE nếu không có lý do.
- Chỉ tạo grouping sets cần cho báo cáo.
- Đo execution plan và runtime trên dữ liệu đại diện.

### 13.3. WHERE giảm dữ liệu trước khi tổng hợp

Nếu chỉ báo cáo một khoảng thời gian, lọc trước:

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue
FROM sales
WHERE sale_date >= DATE '2024-01-01'
  AND sale_date <  DATE '2025-01-01'
GROUP BY ROLLUP (region, product);
~~~

WHERE giới hạn tập hàng đầu vào cho mọi cấp tổng hợp. Dùng khoảng nửa kín giúp bao gồm mọi thời điểm trong năm 2024 khi SALE_DATE có thành phần giờ.

Nhưng nếu muốn grand total toàn thời gian còn chi tiết chỉ trong năm 2024, không thể dùng WHERE đơn giản như trên; phải biểu diễn rõ điều kiện riêng cho các cấp tổng hợp.

### 13.4. HAVING giảm số nhóm đầu ra, không thay thế WHERE

~~~sql
HAVING SUM(amount) >= 100
~~~

lọc sau khi tổng hợp. Nếu điều kiện chỉ áp dụng cho dữ liệu nguồn, nên đặt trong WHERE để giảm đầu vào. Nếu điều kiện dựa trên kết quả aggregate, dùng HAVING.

### 13.5. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT region,
       product,
       GROUPING_ID(region, product) AS gid,
       SUM(amount) AS revenue
FROM sales_group_demo
GROUP BY CUBE (region, product);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Plan có thể thể hiện hoạt động như SORT GROUP BY, HASH GROUP BY hoặc các bước xử lý grouping tùy phiên bản và optimizer. EXPLAIN PLAN là ước lượng; với hệ thống thật, cần xem cursor plan và runtime statistics khi có quyền.

Không tạo index chỉ vì truy vấn có ROLLUP hoặc CUBE. Index có ích cho điều kiện lọc, truy cập dữ liệu hoặc một số đường thực thi; aggregate vẫn có thể cần xử lý nhiều hàng. Quyết định dựa trên workload và đo đạc.

## 14. Các lưu ý về biểu thức, alias và kiểu dữ liệu

### 14.1. GROUP BY theo biểu thức

Có thể nhóm theo biểu thức:

~~~sql
SELECT TRUNC(sale_date, 'MM') AS month_start,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (TRUNC(sale_date, 'MM'));
~~~

Nếu muốn nhận diện subtotal:

~~~sql
SELECT TRUNC(sale_date, 'MM') AS month_start,
       GROUPING(TRUNC(sale_date, 'MM')) AS g_month,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (TRUNC(sale_date, 'MM'));
~~~

GROUPING cần tham chiếu biểu thức tương ứng đã được dùng trong GROUP BY.

### 14.2. Không chọn tùy tiện cột không được nhóm hoặc tổng hợp

~~~sql
-- Không hợp lệ nếu TEN_SAN_PHAM không thuộc nhóm và không được tổng hợp.
SELECT region,
       product,
       product_name,
       SUM(amount)
FROM sales
GROUP BY ROLLUP (region, product);
~~~

Oracle yêu cầu biểu thức select list phù hợp với các quy tắc GROUP BY. Nếu PRODUCT_NAME phụ thuộc vào PRODUCT theo khóa dữ liệu, SQL vẫn cần thể hiện quan hệ theo cú pháp được Oracle chấp nhận, ví dụ thêm PRODUCT_NAME vào grouping set thích hợp hoặc join với bảng dimension sau khi tổng hợp.

### 14.3. Alias không thay thế biểu thức trong GROUPING

Alias trong SELECT giúp đặt tên cột kết quả, nhưng GROUPING/GROUPING_ID cần biểu thức group tương ứng, không nên thay bằng alias như thể alias là cột nguồn:

~~~sql
SELECT TRUNC(sale_date, 'MM') AS month_start,
       GROUPING(TRUNC(sale_date, 'MM')) AS g_month,
       SUM(amount)
FROM sales
GROUP BY ROLLUP (TRUNC(sale_date, 'MM'));
~~~

Đây là cách rõ ràng để Oracle xác định chính xác biểu thức đang được gộp.

### 14.4. Kiểu NULL của hàng tổng hợp

NULL do ROLLUP/CUBE/GROUPING SETS tạo ra là một dấu hiệu biểu diễn cấp tổng hợp, không phải một giá trị dữ liệu mới được ghi vào bảng. Không UPDATE bảng nguồn để “điền NULL subtotal”. Nếu cần nhãn hiển thị, dùng CASE kết hợp GROUPING/GROUPING_ID trong SELECT.

## 15. Ứng dụng Java và báo cáo

Một báo cáo từ Oracle có thể trả về cả dòng chi tiết và dòng tổng hợp. Tầng Java cần nhận biết loại hàng thay vì chỉ nhìn REGION hoặc PRODUCT có NULL hay không.

Ví dụ truy vấn API/report:

~~~sql
SELECT region,
       product,
       GROUPING_ID(region, product) AS grouping_level,
       SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region, product)
ORDER BY GROUPING_ID(region, product),
         region NULLS LAST,
         product NULLS LAST;
~~~

Trong Java/JDBC, có thể đọc:
- REGION và PRODUCT dưới dạng String, có thể là null.
- GROUPING_LEVEL dưới dạng số nguyên.
- REVENUE dưới dạng BigDecimal.

Ví dụ:

~~~java
int groupingLevel = rs.getInt("GROUPING_LEVEL");
String region = rs.getString("REGION");
String product = rs.getString("PRODUCT");
BigDecimal revenue = rs.getBigDecimal("REVENUE");

switch (groupingLevel) {
    case 0 -> {
        // Chi tiết theo khu vực và sản phẩm.
    }
    case 1 -> {
        // Tổng theo khu vực.
    }
    case 3 -> {
        // Tổng toàn bộ.
    }
    default -> {
        // Xử lý cấp tổng hợp khác nếu truy vấn được mở rộng.
    }
}
~~~

Với CUBE hai chiều, GID=2 đại diện subtotal theo PRODUCT; GID=1 đại diện subtotal theo REGION. Với ROLLUP hai chiều, chỉ các mã 0, 1, 3 xuất hiện. **Không dùng chung cách diễn giải GID giữa các truy vấn nếu thứ tự biểu thức hoặc tập grouping sets khác nhau.**

Khi đọc primitive getInt, SQL NULL cũng có thể được ánh xạ thành 0; GROUPING_ID không NULL trong các hàng kết quả thông thường, nhưng với những cột dimension, dùng getString/getObject để giữ trạng thái NULL. Nếu API cần phân biệt NULL thật với subtotal, trả thêm GROUPING/GROUPING_ID hoặc một trường loại hàng rõ ràng.

### 15.1. Không ghép SQL động từ tên chiều không kiểm soát

Nếu báo cáo cho phép người dùng chọn chiều như REGION, PRODUCT, CHANNEL, không nối trực tiếp chuỗi gửi từ client vào GROUP BY CUBE hoặc ORDER BY. Tên cột không thể truyền bằng bind variable. Hãy ánh xạ lựa chọn qua whitelist biểu thức SQL cố định, đồng thời giới hạn số chiều để tránh CUBE tạo quá nhiều grouping sets.

## 16. Quy trình chọn cấu trúc

Khi thiết kế một báo cáo nhiều cấp, có thể chọn theo thứ tự:

1. Liệt kê từng cấp dữ liệu cần xuất: chi tiết, tổng theo vùng, tổng theo sản phẩm, grand total.
2. Xác định các chiều nào tạo thành một thứ tự phân cấp tự nhiên.
3. Nếu cần tổng theo tiền tố phân cấp, dùng ROLLUP.
4. Nếu cần mọi tổ hợp của một số chiều nhỏ, dùng CUBE.
5. Nếu chỉ cần một số tổ hợp cụ thể, dùng GROUPING SETS.
6. Nếu nguồn dữ liệu có NULL thật, thêm GROUPING hoặc GROUPING_ID để phân biệt subtotal.
7. Nếu grouping set có thể bị lặp, loại trùng ở định nghĩa hoặc xem GROUP_ID.
8. Đặt ORDER BY rõ ràng cho thứ tự báo cáo.
9. Dùng WHERE cho điều kiện trên hàng nguồn và HAVING cho điều kiện trên nhóm.
10. Kiểm tra số grouping sets, cardinality, execution plan và TEMP trên dữ liệu đại diện.
11. Trong JDBC, trả một mã cấp tổng hợp để tầng ứng dụng nhận biết dòng chi tiết/tổng.
12. Nếu quy tắc nghiệp vụ của subtotal khác nhau về tập dữ liệu, cân nhắc query block riêng thay vì một WHERE chung.

## 17. Những nhầm lẫn thường gặp

**ROLLUP và CUBE giống nhau.** Không đúng. ROLLUP tạo các tiền tố theo thứ tự biểu thức; CUBE tạo mọi tập con.

**ROLLUP(A,B) tạo tổng theo A và tổng theo B.** Không đúng. Nó tạo (A,B), (A) và (). Muốn tổng theo B riêng, dùng CUBE hoặc GROUPING SETS.

**GROUPING SETS tự thêm subtotal trung gian.** Không đúng. Nó chỉ tạo đúng các grouping set được liệt kê.

**GROUPING(expr)=1 nghĩa là cột nguồn NULL.** Không đúng. Nó nghĩa là biểu thức đã bị gộp khỏi grouping set hiện tại.

**WHERE cột IS NULL có thể lấy mọi hàng tổng.** Không đúng. Nó có thể lấy NULL thật và subtotal; dùng GROUPING để phân biệt.

**CUBE ba chiều chỉ tạo ba tổng.** Không đúng. Ba chiều tạo 2³ = 8 grouping sets.

**Thứ tự trong danh sách GROUPING SETS cũng là thứ tự hiển thị.** Không đúng. Cần ORDER BY.

**GROUPING_ID luôn có cùng mã cho cùng một cấp trong mọi truy vấn.** Không đúng. Mã phụ thuộc danh sách và thứ tự đối số cũng như cấu trúc grouping sets.

**GROUP_ID giống GROUPING_ID.** Không đúng. GROUPING_ID mã hóa cờ gộp; GROUP_ID nhận diện nhóm trùng được sinh bởi grouping sets lặp.

**CUBE luôn tốt hơn UNION ALL.** Không đúng. CUBE có thể tạo nhiều nhóm không cần thiết; UNION ALL có thể phù hợp khi từng nhánh có logic nguồn riêng. Cần chọn theo yêu cầu và đo plan.

**GROUP BY ROLLUP bảo đảm thứ tự hàng.** Không đúng. ORDER BY cuối cùng mới xác định thứ tự trả về.

**NULL trong dòng subtotal là dữ liệu được ghi vào bảng.** Không đúng. Đó là cách biểu diễn cột đã được gộp trong kết quả truy vấn.

**Chỉ cần thêm GROUPING_ID là đủ cho API.** Chưa chắc. Tầng ứng dụng vẫn cần biết quy ước mã, thứ tự chiều, kiểu NULL thật và các cấp tổng hợp có mặt trong truy vấn.

## 18. Bài tập tự luyện

1. Với ROLLUP(REGION, PRODUCT), hãy liệt kê tất cả grouping sets được tạo và giải thích vì sao không có subtotal theo PRODUCT riêng.
2. Với CUBE(REGION, PRODUCT), hãy liệt kê bốn grouping sets và so sánh với ROLLUP hai chiều.
3. Viết GROUPING SETS chỉ tạo chi tiết theo REGION/PRODUCT, subtotal theo PRODUCT và grand total.
4. CUBE ba chiều YEAR, REGION, PRODUCT tạo bao nhiêu grouping sets? Liệt kê chúng.
5. Bảng nguồn có một hàng REGION NULL. Làm sao phân biệt hàng chi tiết đó với subtotal có REGION NULL?
6. Viết GROUPING_ID cho ROLLUP(REGION, PRODUCT) và lập bảng mã 0, 1, 2, 3 tương ứng các cờ.
7. Vì sao GROUPING_ID(REGION, PRODUCT) khác GROUPING_ID(PRODUCT, REGION)?
8. Dùng HAVING để chỉ giữ subtotal theo REGION, không giữ chi tiết và grand total.
9. Dùng HAVING để chỉ giữ grand total trong CUBE hai chiều.
10. Một GROUPING SETS liệt kê (REGION, PRODUCT) hai lần. GROUP_ID có thể giúp nhận diện kết quả nào?
11. Giải thích tác dụng của composite column trong ROLLUP((REGION, PRODUCT), CHANNEL).
12. Vì sao WHERE REGION='NORTH' làm grand total chỉ còn tổng NORTH?
13. Thiết kế truy vấn giữ grand total toàn công ty nhưng chỉ hiển thị chi tiết cho NORTH. Nêu cách tổ chức query block hoặc biểu thức phù hợp.
14. Với CUBE 8 chiều, có bao nhiêu grouping sets? Những rủi ro tài nguyên nào cần đánh giá?
15. Vì sao không nên đưa CUSTOMER_ID vào CUBE nếu báo cáo chỉ cần tổng theo vùng, sản phẩm và kênh?
16. So sánh ROLLUP, CUBE và GROUPING SETS theo cấu trúc báo cáo cần tổng theo năm/quý/tháng.
17. Viết ORDER BY để chi tiết đứng trước subtotal khu vực và grand total, đồng thời đặt NULL thật cuối.
18. Vì sao ORDER BY vẫn cần thiết dù truy vấn đã dùng ROLLUP?
19. Trong Java, vì sao nên trả GROUPING_ID cho client khi kết quả chứa cả dòng chi tiết và tổng?
20. Khi nào một số câu SELECT ghép UNION ALL có thể rõ ràng hơn một câu CUBE hoặc GROUPING SETS?

**ROLLUP tạo tổng theo cấp phân cấp, CUBE tạo tổng theo mọi tổ hợp chiều, còn GROUPING SETS cho phép chọn chính xác những cấp cần thiết. GROUPING và GROUPING_ID phân biệt NULL do dữ liệu với NULL do tổng hợp; GROUP_ID nhận diện nhóm trùng.** Khi chọn đúng cấu trúc, đặt WHERE/HAVING đúng giai đoạn và dùng ORDER BY tường minh, một truy vấn Oracle có thể tạo báo cáo nhiều cấp vừa dễ hiểu vừa kiểm soát được chi phí thực thi.
