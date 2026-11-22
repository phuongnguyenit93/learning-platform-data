# Ước lượng số hàng (cardinality) và vai trò đối với lựa chọn kế hoạch

Khi nhận một câu SQL, bộ tối ưu của hệ quản trị cơ sở dữ liệu cần dự đoán mỗi thao tác sẽ đọc và tạo ra bao nhiêu hàng. Dự đoán này gọi là ước lượng cardinality. Nó ảnh hưởng trực tiếp đến cách hệ quản trị truy cập bảng, thứ tự join, thuật toán nối, cách tổng hợp và lượng bộ nhớ cấp cho các thao tác trung gian.

Trong tối ưu hiệu năng cơ sở dữ liệu, đọc execution plan mà không xem chất lượng ước lượng số hàng sẽ bỏ sót một nguyên nhân phổ biến của kế hoạch kém. Một Nested Loop có thể hợp lý khi đầu vào chỉ có vài hàng nhưng rất tốn kém nếu thực tế có hàng trăm nghìn hàng. Một Hash Join có thể chạy tốt khi bộ nhớ đủ, nhưng sẽ phát sinh I/O tạm nếu số hàng hoặc kích thước dữ liệu lớn hơn dự kiến. Vì vậy, cần hiểu bộ tối ưu ước lượng như thế nào, thống kê cung cấp thông tin gì và cách so sánh ước lượng với số hàng thực tế.

## 1. Cardinality là gì?

Trong ngữ cảnh kế hoạch truy vấn, cardinality thường chỉ số hàng mà một quan hệ hoặc operator dự kiến tạo ra. Ví dụ:

- Bảng orders có 10 triệu hàng.
- Điều kiện WHERE lọc theo trạng thái có thể giữ lại khoảng 2 triệu hàng.
- Join orders với customers có thể tạo ra 2 triệu hàng nếu mỗi đơn thuộc về một khách hàng.
- GROUP BY theo khu vực có thể tạo ra 12 nhóm.

Các con số này là đầu vào quan trọng để bộ tối ưu đánh giá chi phí của những kế hoạch khác nhau.

Phân biệt hai khái niệm thường bị gọi chung:

- **Cardinality của kết quả:** số hàng của bảng, quan hệ hoặc operator.
- **NDV (number of distinct values):** số giá trị phân biệt của một cột hoặc một nhóm cột. Ví dụ cột status có 5 giá trị khác nhau thì NDV của status là 5.

NDV là một loại thống kê giúp ước lượng cardinality. Nó không phải số hàng của kết quả. Nếu bảng có 10 triệu hàng và cột status có 5 giá trị, NDV bằng 5 nhưng cardinality của bảng vẫn là 10 triệu.

### 1.1. Ước lượng số hàng sau điều kiện lọc

Giả sử bảng orders có N hàng và cột status có D giá trị phân biệt. Nếu các giá trị phân bố đồng đều, không có NULL và điều kiện là:

~~~sql
WHERE status = 'SHIPPED'
~~~

Bộ tối ưu có thể ước lượng số hàng gần bằng:

\[
EstimatedRows \approx \frac{N}{D}
\]

Nếu N = 10.000.000 và D = 5, ước lượng đơn giản là 2.000.000 hàng.

Trong thực tế, dữ liệu hiếm khi phân bố hoàn toàn đồng đều. Có thể 70% đơn hàng ở trạng thái COMPLETED, 20% ở trạng thái SHIPPED và 10% chia cho các trạng thái còn lại. Khi đó, chỉ biết NDV = 5 chưa đủ để dự đoán số hàng cho từng giá trị. Bộ tối ưu cần thống kê tần suất hoặc histogram để nhận biết giá trị phổ biến và hiếm.

Nếu cột có NULL, phép so sánh bằng thông thường không khớp các hàng NULL. Một mô hình đơn giản có thể điều chỉnh theo tỷ lệ không NULL:

\[
EstimatedRows \approx N \times (1-NullFraction) \times Selectivity
\]

Trong đó Selectivity là tỷ lệ hàng dự kiến thỏa điều kiện trong phần dữ liệu không NULL. Cách tính chính xác tùy hệ quản trị và loại predicate.

### 1.2. Ước lượng số hàng sau nhiều điều kiện

Với hai điều kiện A và B, một giả định phổ biến là hai điều kiện độc lập:

\[
Selectivity(A \land B) \approx Selectivity(A) \times Selectivity(B)
\]

Ví dụ, 60% đơn hàng có status = 'SHIPPED' và 70% đơn hàng đến từ channel = 'WEB'. Nếu hai thuộc tính độc lập, bộ tối ưu ước lượng khoảng 42% hàng thỏa đồng thời hai điều kiện.

Giả định độc lập có thể sai nếu các cột tương quan. Trong hệ thống thực, đơn hàng từ WEB có thể có tỷ lệ SHIPPED cao hơn nhiều đơn từ cửa hàng. Khi đó, nhân hai selectivity riêng lẻ sẽ ước lượng thiếu hoặc thừa số hàng.

Đối với điều kiện OR, một cách ước lượng đơn giản dưới giả định độc lập là:

\[
Selectivity(A \lor B) \approx s_A + s_B - (s_A \times s_B)
\]

Các công thức này là mô hình trực giác. Bộ tối ưu có thể dùng histogram, thống kê đa cột, ràng buộc, quy tắc riêng và mô hình phức tạp hơn. Không nên tự suy ra con số chính xác chỉ từ một công thức giản lược.

## 2. Thống kê giúp bộ tối ưu ước lượng như thế nào?

Thống kê (statistics) là mô tả tóm tắt dữ liệu mà bộ tối ưu sử dụng để dự đoán độ chọn lọc và số hàng. Thống kê thường được tạo tự động hoặc cập nhật bằng thao tác bảo trì, tùy hệ quản trị.

Các thành phần quan trọng gồm:

| Thống kê | Ý nghĩa | Dùng để ước lượng |
|---|---|---|
| Row count | Số hàng của bảng hoặc phân vùng | Quy mô dữ liệu đầu vào |
| NDV | Số giá trị phân biệt | Độ chọn lọc của điều kiện bằng và số nhóm |
| Null fraction | Tỷ lệ giá trị NULL | Số hàng thỏa IS NULL hoặc có thể tham gia phép so sánh |
| Histogram | Phân bố giá trị theo khoảng hoặc bucket | Điều kiện bằng, range và giá trị phổ biến/hiếm |
| Most common values (MCV) | Các giá trị xuất hiện thường xuyên và tần suất | Ước lượng chính xác hơn cho giá trị lệch |
| Density | Mật độ hoặc mức độ lặp của khóa theo định nghĩa hệ quản trị | Ước lượng predicate và join |
| Multi-column statistics | Quan hệ giữa nhiều cột | Predicate kết hợp, số nhóm hoặc tương quan |
| Index statistics | Phân bố và cardinality của khóa chỉ mục | Đánh giá khả năng truy cập qua index |

### 2.1. Row count và NDV

Row count cho biết quy mô bảng. NDV cho biết số giá trị phân biệt của cột hoặc nhóm cột. Cả hai cần được cập nhật khi dữ liệu thay đổi đáng kể.

Ví dụ, một bảng events có 50 triệu hàng nhưng chỉ 4 giá trị ở cột event_type. Chỉ mục trên event_type có thể kém chọn lọc nếu truy vấn lấy một loại chiếm 80% dữ liệu. Trong khi đó, chỉ mục trên event_id có NDV gần bằng số hàng có thể rất chọn lọc cho điều kiện bằng.

Đối với GROUP BY, NDV của nhóm cột giúp dự đoán số nhóm. Nếu GROUP BY region, status thì NDV riêng của region và status chưa chắc cho biết chính xác số cặp kết hợp, nhất là khi hai cột tương quan.

### 2.2. Histogram và giá trị phổ biến

Histogram chia miền giá trị thành các bucket hoặc mô tả phân bố theo cách riêng của hệ quản trị. Nó giúp bộ tối ưu biết dữ liệu tập trung ở đâu, thay vì giả định mọi giá trị có tần suất như nhau.

Ví dụ, nếu cột created_at chứa dữ liệu tập trung mạnh trong ba tháng gần nhất, điều kiện lọc một ngày gần đây có thể trả về nhiều hàng hơn một ngày cách đây ba năm. Histogram giúp phân biệt hai khoảng này.

Histogram có độ chi tiết hữu hạn. Nếu phân bố thay đổi nhanh, giá trị hiếm hoặc khoảng nhỏ không được đại diện tốt, ước lượng vẫn có thể sai. Tăng sample hoặc statistics target có thể cải thiện độ chính xác nhưng làm tăng chi phí thu thập và lưu trữ thống kê.

### 2.3. Thống kê đơn cột và tương quan đa cột

Thống kê đơn cột mô tả từng thuộc tính riêng lẻ. Khi truy vấn kết hợp nhiều điều kiện, bộ tối ưu có thể cần biết mối quan hệ giữa các cột.

Ví dụ, trong bảng orders:

- channel = 'WEB' có tỷ lệ 70%.
- status = 'SHIPPED' có tỷ lệ 60%.
- Nhưng trong các đơn WEB, tỷ lệ SHIPPED có thể là 90%.

Nếu coi hai cột độc lập, bộ tối ưu dự đoán 42% hàng thỏa cả hai điều kiện. Nếu thực tế là 63% tổng số hàng, số hàng thực tế cao hơn ước lượng 50%. Sai lệch này có thể ảnh hưởng đến lựa chọn chỉ mục và join.

Một số hệ quản trị hỗ trợ thống kê đa cột, thống kê phụ thuộc hoặc thống kê giá trị phổ biến kết hợp. Chúng giúp mô tả các tương quan mà thống kê đơn cột không thể hiện được. Khả năng và cú pháp khác nhau giữa PostgreSQL, SQL Server và MySQL.

## 3. Cardinality ảnh hưởng đến lựa chọn kế hoạch như thế nào?

Bộ tối ưu thường tạo hoặc đánh giá nhiều phương án thực thi, rồi chọn phương án có chi phí ước lượng thấp theo mô hình của nó. Cardinality ảnh hưởng đến gần như mọi quyết định lớn trong kế hoạch.

### 3.1. Index Seek/Scan hay Table Scan

Nếu điều kiện lọc dự kiến trả về ít hàng, truy cập qua chỉ mục thường hấp dẫn vì engine có thể tìm một vùng nhỏ của dữ liệu. Nếu điều kiện trả về phần lớn bảng, quét bảng tuần tự có thể rẻ hơn việc đọc chỉ mục rồi thực hiện nhiều lookup rời rạc.

Khi cardinality bị ước lượng quá thấp, bộ tối ưu có thể chọn Index Seek kèm nhiều Key Lookup hoặc bookmark lookup. Nếu thực tế hàng triệu hàng được trả về, chi phí lookup lặp lại có thể cao hơn một Table Scan.

Khi cardinality bị ước lượng quá cao, bộ tối ưu có thể chọn Table Scan dù một chỉ mục chọn lọc có thể phục vụ truy vấn tốt hơn.

### 3.2. Thứ tự join

Với truy vấn nối nhiều bảng, thứ tự join quyết định kích thước các tập dữ liệu trung gian. Bộ tối ưu thường cố gắng áp dụng các bộ lọc chọn lọc sớm để giảm số hàng cần kết hợp.

Nếu ước lượng số hàng của một bảng sau filter sai, bộ tối ưu có thể chọn thứ tự join khiến các tập dữ liệu lớn được kết hợp quá sớm. Sai lệch ở một bước có thể lan sang các bước phía trên.

Hãy xem số hàng đầu ra của từng join, không chỉ số hàng cuối cùng. Một join trung gian tạo ra hàng triệu hàng rồi operator phía trên mới loại bỏ phần lớn có thể là dấu hiệu cần xem lại predicate, thống kê hoặc thứ tự join.

### 3.3. Nested Loop, Hash Join và Merge Join

Cardinality có ảnh hưởng trực tiếp đến lựa chọn thuật toán:

- **Nested Loop:** thường phù hợp khi đầu vào ngoài nhỏ và đầu vào trong có đường tìm kiếm hiệu quả. Nếu outer thực tế lớn hơn nhiều dự đoán, inner lookup có thể bị lặp quá nhiều lần.
- **Hash Join:** thường phù hợp với tập dữ liệu lớn hơn khi có thể xây dựng bảng băm. Nếu build input lớn hơn dự kiến, bảng băm có thể vượt bộ nhớ và spill.
- **Merge Join:** phù hợp khi hai đầu vào đã có thứ tự hoặc chi phí tạo thứ tự chấp nhận được. Cardinality ảnh hưởng đến chi phí sort và merge.

Không có thuật toán join nào luôn tốt nhất. Một kế hoạch có Nested Loop không phải tự động sai; cần xem số hàng, loops, cách truy cập inner và chi phí thực tế.

### 3.4. Sort, Aggregate và memory grant

Cardinality cũng quyết định lượng dữ liệu phải sắp xếp, số nhóm cần tổng hợp và bộ nhớ được cấp:

- Sort nhiều hàng hoặc hàng rộng cần nhiều bộ nhớ hơn.
- Hash Aggregate có nhiều nhóm cần bảng băm lớn hơn.
- Hash Join có build input lớn cần nhiều bộ nhớ hơn.
- Nếu ước lượng thấp, bộ nhớ được cấp có thể thiếu và gây spill ra vùng tạm.
- Nếu ước lượng cao, bộ nhớ có thể bị cấp quá nhiều, làm giảm khả năng chạy đồng thời của các truy vấn khác.

Do đó, sai lệch cardinality không chỉ làm thay đổi thuật toán mà còn ảnh hưởng đến I/O tạm, concurrency và độ ổn định của hệ thống.

## 4. Các dạng sai lệch cardinality

### 4.1. Ước lượng thấp (underestimation)

Estimated rows thấp hơn actual rows đáng kể. Nguyên nhân thường gặp:

- Thống kê đã cũ sau khi nạp hoặc thay đổi nhiều dữ liệu.
- Giá trị phổ biến không được mô tả đủ trong histogram hoặc MCV.
- Predicate kết hợp nhiều cột có tương quan nhưng bộ tối ưu giả định độc lập.
- Tham số lúc biên dịch khác với tham số lúc thực thi.
- Ước lượng số hàng sau join không mô hình hóa đúng mức độ trùng khóa.
- Dữ liệu phân bố lệch hoặc có hot key.

Hậu quả có thể gồm chọn Nested Loop với quá nhiều vòng lặp, chọn Index Lookup cho tập dữ liệu lớn, cấp thiếu memory grant và phát sinh spill.

### 4.2. Ước lượng cao (overestimation)

Estimated rows cao hơn actual rows đáng kể. Nguyên nhân có thể là thống kê cũ, giả định phân bố không đúng, thiếu thông tin về ràng buộc hoặc ước lượng join quá rộng.

Hậu quả có thể gồm chọn Table Scan thay cho truy cập chỉ mục chọn lọc, dùng Hash Join hoặc Sort lớn không cần thiết, cấp memory grant quá lớn và giảm concurrency.

### 4.3. Sai lệch tăng dần qua nhiều operator

Một sai lệch nhỏ ở node đầu có thể tăng lên sau nhiều join hoặc filter. Ví dụ, nếu mỗi bước ước lượng cao hơn thực tế 2 lần và các giả định tiếp tục nhân lên, kết quả cuối có thể lệch rất lớn.

Khi đọc plan, tìm node đầu tiên có chênh lệch lớn giữa estimated và actual rows. Đây thường là nơi đáng điều tra trước. Các node phía trên có thể chỉ đang kế thừa sai lệch từ đầu vào.

### 4.4. Sai lệch do tham số và plan cache

Một câu SQL được chạy với nhiều giá trị tham số có thể có cardinality rất khác nhau. Ví dụ customer_id của khách hàng thông thường có vài chục đơn, còn khách hàng lớn có hàng triệu đơn.

Một kế hoạch được biên dịch dựa trên một tham số có thể không phù hợp cho tham số khác. Một số hệ quản trị có cơ chế parameter sniffing, prepared statement, generic/custom plan hoặc parameter-sensitive plan để quản lý tình huống này, nhưng hành vi phụ thuộc phiên bản và cấu hình.

Khi điều tra, hãy đo nhiều giá trị tham số đại diện, ghi rõ kế hoạch được biên dịch và thực thi với giá trị nào, đồng thời kiểm tra plan cache. Không kết luận chỉ từ một giá trị thuận lợi.

## 5. Ví dụ: sai lệch do hai cột tương quan

Giả sử bảng orders có 10 triệu hàng với phân bố:

| Điều kiện | Tỷ lệ trên toàn bảng |
|---|---:|
| status = 'SHIPPED' | 60% |
| channel = 'WEB' | 70% |
| Cả hai điều kiện đồng thời (thực tế) | 54% |

Truy vấn:

~~~sql
SELECT id, customer_id, created_at
FROM orders
WHERE status = 'SHIPPED'
  AND channel = 'WEB';
~~~

Nếu bộ tối ưu giả định hai cột độc lập, nó có thể ước lượng:

\[
10.000.000 \times 0,60 \times 0,70
= 4.200.000 \text{ hàng}
\]

Nhưng thực tế có 54% hàng thỏa cả hai điều kiện:

\[
10.000.000 \times 0,54
= 5.400.000 \text{ hàng}
\]

Ước lượng thấp hơn thực tế 1,2 triệu hàng; số hàng thực tế cao hơn ước lượng khoảng 29%. Nếu truy vấn cần nhiều cột và bộ tối ưu chọn chỉ mục không cover kèm hàng triệu lookup, kế hoạch có thể chậm hơn dự kiến.

Đây là ví dụ minh họa. Trong hệ thống thật, cần đo actual rows và kiểm tra thống kê của từng cột, phân bố kết hợp, kiểu truy cập và chi phí lookup. Một chỉ mục ghép trên (status, channel) có thể hỗ trợ predicate, nhưng có hiệu quả hay không còn phụ thuộc độ chọn lọc, thứ tự cột, cột cần trả về và workload ghi.

Hướng xử lý:

1. Xác nhận số hàng thực tế cho từng predicate và kết hợp predicate.
2. Kiểm tra thống kê đơn cột và thời điểm cập nhật.
3. Xem hệ quản trị có hỗ trợ thống kê đa cột hoặc histogram phù hợp không.
4. Cân nhắc thống kê đa cột hoặc chỉ mục ghép dựa trên workload thực.
5. Chạy lại với cùng dữ liệu, tham số và trạng thái cache.
6. So sánh estimated rows, actual rows, operator được chọn, I/O và thời gian.

## 6. Ước lượng cardinality cho phép nối

Đối với equi-join giữa hai bảng R và S theo một khóa, một mô hình đơn giản trong trường hợp giá trị phân bố đều và miền giá trị tương thích là:

\\[
JoinRows \\approx
\\frac{|R| \\times |S|}
{\\max(NDV_R, NDV_S)}
\\]

Trong đó |R| và |S| là số hàng của hai đầu vào; NDV_R và NDV_S là số giá trị phân biệt của khóa join ở mỗi phía.

Đây chỉ là mô hình trực giác. Ước lượng thực tế cần xem miền giá trị có giao nhau hay không, NULL, khóa duy nhất, khóa ngoại, giá trị trùng, bộ lọc trước join và phân bố lệch. Nếu một phía là khóa duy nhất, quan hệ ràng buộc có thể giúp giới hạn số hàng khớp. Nếu một khóa xuất hiện rất nhiều lần ở cả hai phía, join có thể tạo ra số hàng lớn do tổ hợp các bản ghi trùng.

Ví dụ, customers có một hàng cho mỗi customer_id, còn orders có nhiều đơn trên một customer_id. Join theo customer_id thường không tạo quá một hàng customers cho mỗi hàng orders. Nếu thống kê hoặc ràng buộc không phản ánh tính duy nhất, bộ tối ưu có thể ước lượng sai số hàng.

Khi join nhiều bảng:

- Kiểm tra số hàng của từng đầu vào sau filter.
- Kiểm tra NDV và phân bố của khóa join ở cả hai phía.
- Xác nhận unique constraint, primary key và foreign key có thực sự tồn tại và được hệ quản trị sử dụng trong ước lượng hay không.
- Kiểm tra số hàng sau join có tăng đúng theo quan hệ một-một, một-nhiều hay nhiều-nhiều dự kiến.
- Tìm node đầu tiên có sai lệch lớn thay vì chỉ nhìn kết quả cuối.

## 7. Đo và chẩn đoán sai lệch trong execution plan

### 7.1. Tìm Estimated Rows và Actual Rows

Khi có actual execution plan, so sánh estimated rows với actual rows tại từng node. Có thể dùng tỷ lệ:

\[
ErrorRatio = \frac{\max(EstimatedRows, ActualRows)}
{\max(\min(EstimatedRows, ActualRows), 1)}
\]

ErrorRatio càng lớn thì chênh lệch càng đáng chú ý. Tuy nhiên, không nên dùng một ngưỡng cố định để tự động kết luận. Một sai lệch 10 lần ở node nhỏ có thể ít ảnh hưởng, trong khi sai lệch 2 lần ở node xử lý hàng chục triệu bản ghi có thể rất tốn kém.

Khi đọc, cần xem:

- Estimated rows và actual rows.
- Loops hoặc số lần operator được thực thi.
- Số hàng trước và sau filter/join.
- Buffer reads, logical reads và physical reads.
- Sort/hash spill, memory grant và temporary I/O.
- Thời gian thực tế của operator và toàn câu truy vấn.

Nếu một node được lặp nhiều lần, hãy xem cách công cụ trình bày actual rows là trung bình mỗi loop hay tổng số hàng. Đọc nhầm đơn vị có thể dẫn đến kết luận sai.

### 7.2. PostgreSQL

Có thể xem kế hoạch với:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id
FROM orders
WHERE status = 'SHIPPED';
~~~

Trong kết quả, rows= ở phần cost là ước lượng; actual rows= là số hàng thực tế theo cách hiển thị của PostgreSQL; loops= cho biết số lần node chạy. Khi cần xem thống kê cột:

~~~sql
SELECT
    attname,
    n_distinct,
    null_frac,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname IN ('status', 'channel');
~~~

pg_stats là view cung cấp thống kê đã thu thập cho các cột. Nếu dữ liệu thay đổi lớn, có thể cập nhật thống kê trong môi trường phù hợp:

~~~sql
ANALYZE orders;
~~~

Với tương quan giữa các cột, PostgreSQL hỗ trợ extended statistics:

~~~sql
CREATE STATISTICS orders_status_channel_stats
    (dependencies, mcv, ndistinct)
ON status, channel
FROM orders;

ANALYZE orders;
~~~

dependencies mô tả một số phụ thuộc giữa cột, mcv lưu các tổ hợp giá trị phổ biến và ndistinct giúp ước lượng số nhóm của tổ hợp cột. Extended statistics không giải quyết mọi dạng tương quan hoặc mọi loại join; hãy xác nhận bằng actual plan sau khi tạo.

Có thể tăng statistics target cho một cột quan trọng khi histogram hoặc MCV chưa đủ chi tiết:

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET STATISTICS 500;

ANALYZE orders;
~~~

Statistics target lớn hơn có thể tăng độ chi tiết nhưng cũng làm ANALYZE tốn thời gian và lưu nhiều thống kê hơn. Chỉ tăng có mục tiêu cho cột có vấn đề đã được xác định.

### 7.3. SQL Server

Trong Actual Execution Plan, đối chiếu Estimated Number of Rows với Actual Number of Rows ở từng operator. Chú ý các node join, seek/scan, sort và aggregate. Nếu một operator có số hàng thực tế lớn hơn ước lượng, kiểm tra thống kê được dùng và tham số lúc biên dịch.

Có thể xem thông tin thống kê:

~~~sql
DBCC SHOW_STATISTICS ('dbo.Orders', 'IX_Orders_Status')
WITH STAT_HEADER, DENSITY_VECTOR, HISTOGRAM;
~~~

Histogram của một statistics object SQL Server tập trung vào cột đầu tiên trong danh sách khóa; density vector cung cấp thêm thông tin mật độ cho các prefix của tập cột. Vì vậy, thứ tự cột trong index/statistics object có ý nghĩa khi bộ tối ưu ước lượng.

Có thể cập nhật thống kê của bảng:

~~~sql
UPDATE STATISTICS dbo.Orders;
~~~

Hoặc dùng FULLSCAN trong trường hợp cần kiểm tra độ chính xác của thống kê và chi phí thu thập được chấp nhận:

~~~sql
UPDATE STATISTICS dbo.Orders WITH FULLSCAN;
~~~

FULLSCAN không nên trở thành thao tác mặc định cho mọi bảng lớn. Cân nhắc thời gian, I/O, lịch bảo trì và tác động đến workload. SQL Server cũng hỗ trợ filtered statistics và statistics đa cột; cần chọn predicate và thứ tự cột phù hợp với truy vấn thực tế.

### 7.4. MySQL

Trong MySQL 8.0.18 trở lên, EXPLAIN ANALYZE cung cấp thời gian và số hàng thực tế theo iterator:

~~~sql
EXPLAIN ANALYZE
SELECT id, customer_id
FROM orders
WHERE status = 'SHIPPED';
~~~

rows trong EXPLAIN dạng ước lượng và số hàng thực tế của iterator cần được phân biệt. Có thể xem thông tin chỉ mục và cardinality ước lượng:

~~~sql
SHOW INDEX FROM orders;
~~~

Để cập nhật thống kê bảng:

~~~sql
ANALYZE TABLE orders;
~~~

MySQL hỗ trợ histogram cho cột:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, channel
WITH 128 BUCKETS;
~~~

Histogram có thể giúp bộ tối ưu ước lượng điều kiện lọc trên các cột được thu thập. Khả năng mô tả tương quan nhiều cột và cách dùng thống kê phụ thuộc phiên bản; không giả định histogram đơn cột sẽ nắm bắt đầy đủ quan hệ giữa status và channel.

## 8. Quy trình cải thiện chất lượng ước lượng

Khi phát hiện sai lệch cardinality, thực hiện theo trình tự để tránh thay đổi không có căn cứ:

1. **Lưu kế hoạch và điều kiện chạy.** Ghi SQL, kiểu tham số, dữ liệu, phiên bản, cấu hình, trạng thái cache và concurrency.
2. **Tìm node đầu tiên sai lệch đáng kể.** Bắt đầu từ node lá và đi lên; ghi estimated rows, actual rows, loops và kích thước dữ liệu.
3. **Kiểm tra dữ liệu.** Xác nhận số hàng, NDV, NULL, giá trị phổ biến, histogram và phân bố lệch.
4. **Kiểm tra thời điểm thống kê.** Xem lần cập nhật gần nhất, sample, statistics target và các thay đổi dữ liệu gần đây.
5. **Kiểm tra tương quan.** Xác định predicate đa cột, khóa join hoặc nhóm GROUP BY có quan hệ phụ thuộc mà thống kê đơn cột không mô tả được.
6. **Kiểm tra tham số và plan cache.** So sánh giá trị phổ biến/hiếm, kiểu bind, kế hoạch biên dịch và kế hoạch tái sử dụng.
7. **Chọn điều chỉnh phù hợp.** Có thể cập nhật thống kê, tăng độ chi tiết thống kê, tạo thống kê đa cột, sửa kiểu tham số hoặc điều chỉnh chỉ mục sau khi đánh giá.
8. **Đo lại trong điều kiện tương đương.** So sánh estimated/actual rows, operator, thời gian, I/O, memory grant và temp usage.
9. **Xác minh tính đúng đắn.** Đối chiếu số hàng, giá trị tổng hợp, NULL, duplicate và trường hợp biên trước/sau.
10. **Theo dõi toàn workload.** Đảm bảo cải thiện một truy vấn không làm tăng chi phí ghi, thời gian ANALYZE hoặc tranh chấp tài nguyên quá mức.

Không phải mọi sai lệch đều cần tạo thống kê mới. Nếu thống kê đã chính xác nhưng tham số thay đổi mạnh theo từng lần gọi, cần xử lý vấn đề plan sensitivity. Nếu join tạo số hàng lớn do quan hệ nhiều-nhiều đúng nghiệp vụ, đó có thể là khối lượng công việc thực tế chứ không phải lỗi ước lượng.

## 9. Những yếu tố làm thống kê nhanh chóng lỗi thời

Thống kê có thể trở nên kém đại diện khi:

- Nạp dữ liệu hàng loạt hoặc xóa nhiều hàng.
- Dữ liệu tăng nhanh theo thời gian và giá trị mới tập trung ở một khoảng.
- Một trạng thái nghiệp vụ thay đổi tỷ trọng đột ngột.
- Một cột phân loại bắt đầu có hot value mới.
- Partition mới được thêm hoặc dữ liệu được chuyển giữa các partition.
- Một cột có tương quan thay đổi do quy trình nghiệp vụ.
- Bảng tăng kích thước nhưng chính sách auto-update chưa kích hoạt hoặc không cập nhật đủ kịp thời.

Hãy gắn việc kiểm tra thống kê với các sự kiện dữ liệu như bulk load, migration, archive, thay đổi phân vùng và đợt cập nhật nghiệp vụ lớn. Việc cập nhật thống kê quá thường xuyên cũng có chi phí; cần chọn lịch và phạm vi phù hợp với tốc độ biến động dữ liệu.

## 10. Sai lầm thường gặp khi đọc cardinality

- **Nhầm NDV với số hàng:** NDV là số giá trị phân biệt; cardinality của kết quả là số hàng.
- **Giả định dữ liệu phân bố đều:** giá trị phổ biến và hiếm có thể làm selectivity khác xa N/NDV.
- **Tin rằng thống kê đơn cột đủ cho mọi predicate:** nhiều cột có thể tương quan.
- **Chỉ xem node cuối:** sai lệch thường bắt đầu ở một node thấp hơn và lan lên.
- **Bỏ qua Loops:** số hàng mỗi lần gọi nhỏ nhưng tổng số lần truy cập rất lớn.
- **So sánh estimated rows giữa hai phiên bản như thể cùng mô hình:** cách ước lượng và cost model có thể thay đổi.
- **Cập nhật thống kê một cách mù quáng:** thống kê mới không chắc giải quyết được vấn đề tham số hoặc mô hình tương quan.
- **Dùng FULLSCAN cho mọi bảng:** chi phí thu thập có thể lớn hơn lợi ích.
- **Tạo chỉ mục chỉ vì estimated rows sai:** cần tìm nguyên nhân sai lệch và xác định index có cải thiện workload tổng thể không.
- **Bỏ qua tính đúng đắn khi sửa SQL:** thay đổi predicate hoặc join có thể làm số hàng khác vì ngữ nghĩa thay đổi.

## 11. Checklist đánh giá cardinality

- [ ] Đã phân biệt số hàng kết quả với NDV của cột.
- [ ] Đã ghi số hàng bảng và thống kê của các cột lọc/join.
- [ ] Đã xem histogram, MCV, NULL fraction hoặc thống kê tương đương.
- [ ] Đã kiểm tra phân bố lệch và tương quan giữa các cột.
- [ ] Đã so sánh estimated rows với actual rows từ node lá lên.
- [ ] Đã xem loops và tổng khối lượng truy cập của operator lặp.
- [ ] Đã kiểm tra số hàng sau từng join và số nhóm sau aggregate.
- [ ] Đã xác nhận thống kê còn phù hợp với dữ liệu hiện tại.
- [ ] Đã xem xét kiểu tham số, giá trị tham số và plan cache.
- [ ] Đã đánh giá tác động đến join algorithm, index access, sort/hash và memory grant.
- [ ] Đã đo lại với dữ liệu và workload đại diện.
- [ ] Đã xác minh kết quả nghiệp vụ và tác động đến toàn workload.

Ước lượng cardinality là nền tảng để bộ tối ưu chọn cách truy cập dữ liệu và tổ chức các operator. Khi thống kê phản ánh đúng quy mô, phân bố và quan hệ giữa các cột, bộ tối ưu có cơ hội chọn kế hoạch phù hợp hơn. Khi thấy kế hoạch bất thường, hãy tìm điểm đầu tiên mà số hàng ước lượng lệch khỏi thực tế, kiểm tra dữ liệu và thống kê liên quan, sau đó đo lại trong điều kiện có thể so sánh.
