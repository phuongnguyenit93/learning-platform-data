# Selectivity, cardinality và phân bố dữ liệu lệch

Một chỉ mục có thể chứa rất nhiều giá trị khác nhau nhưng vẫn không giúp ích cho một truy vấn cụ thể. Ngược lại, một cột chỉ có vài giá trị có thể rất hữu ích nếu truy vấn thường tìm một giá trị hiếm. Để hiểu vì sao MySQL chọn index hay quét toàn bảng, cần phân biệt ba khái niệm: **cardinality**, **selectivity của index** và **selectivity của điều kiện lọc**.

Với MySQL/InnoDB, cardinality trong thống kê index là số lượng giá trị khác nhau được ước lượng. Selectivity cho biết một cột hoặc một điều kiện có khả năng thu hẹp tập dòng đến mức nào. Phân bố dữ liệu lệch (data skew) khiến các giá trị trong cùng một cột xuất hiện với tần suất rất khác nhau; khi đó một con số trung bình có thể không mô tả đúng truy vấn đang chạy.

Bài học thuộc chương **Chỉ mục** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, việc đọc đúng thống kê giúp chọn index theo workload, phát hiện ước lượng sai của optimizer và tránh thêm chỉ mục chỉ vì thấy một cột có cardinality cao.

## 1. Phân biệt cardinality và hai cách nói về selectivity

**Cardinality** của một cột là số lượng giá trị khác nhau trong cột. Ví dụ, bảng có một triệu đơn hàng nhưng chỉ có bốn trạng thái thì cardinality của cột status xấp xỉ 4. Nếu mỗi order_id là duy nhất thì cardinality của order_id xấp xỉ một triệu.

Trong MySQL, cột Cardinality của SHOW INDEX là ước lượng số giá trị khác nhau của index hoặc của phần tiền tố index tương ứng. Với index nhiều cột, mỗi dòng trong kết quả SHOW INDEX mô tả một cột trong index; cardinality ở dòng đó ước lượng số giá trị khác nhau của tiền tố tính đến cột ấy. Đây là thống kê ước lượng, không phải phép đếm chính xác mọi giá trị tại mỗi lần truy vấn.

Từ cardinality có thể tính một chỉ số thường gọi là **index selectivity**:

\[
\text{Index selectivity} =
\frac{\text{Số giá trị khác nhau}}{\text{Tổng số dòng}}
\]

Chỉ số càng gần 1 thì giá trị càng phân biệt tốt giữa các dòng. Với một khóa duy nhất, tỷ lệ này gần 1. Với cột trạng thái chỉ có bốn giá trị trong một triệu dòng, tỷ lệ này rất nhỏ.

Một cách diễn đạt khác là **filter selectivity** của một điều kiện WHERE:

\[
\text{Filter selectivity} =
\frac{\text{Số dòng thỏa điều kiện}}{\text{Tổng số dòng}}
\]

Ở cách diễn đạt này, tỷ lệ càng nhỏ thì điều kiện càng chọn lọc vì chỉ giữ lại ít dòng. Hai cách dùng từ selectivity có chiều diễn giải ngược nhau. Khi đọc tài liệu, báo cáo hoặc trao đổi với đồng đội, hãy xác định rõ đang nói về tỷ lệ distinct/total hay matching/total.

| Khái niệm | Công thức hoặc ý nghĩa | Ví dụ |
|---|---|---|
| Cardinality | Số giá trị khác nhau | 4 trạng thái trong bảng đơn hàng |
| Index selectivity | distinct values / total rows | 4 / 1.000.000 = 0,000004 |
| Filter selectivity | matching rows / total rows | 1.000 dòng FAILED / 1.000.000 = 0,001 |
| Data skew | Tần suất các giá trị không đồng đều | PAID chiếm 95%, FAILED chiếm 0,1% |

Không nên kết luận rằng index selectivity thấp đồng nghĩa index vô dụng. Cardinality chỉ cho biết có bao nhiêu giá trị khác nhau; nó không cho biết mỗi giá trị xuất hiện bao nhiêu lần. Để đánh giá một truy vấn cụ thể, cần xem phân bố thực tế của giá trị mà điều kiện WHERE đang tìm.

## 2. Xem cardinality mà MySQL đang lưu

Giả sử có bảng orders với các cột order_id, tenant_id, status, created_at và amount. Có thể xem các index hiện tại bằng:

~~~sql
SHOW INDEX FROM orders;
~~~

Các cột quan trọng trong kết quả:

- **Key_name**: tên index.
- **Seq_in_index**: vị trí cột trong index ghép, bắt đầu từ 1.
- **Column_name**: cột thuộc index.
- **Non_unique**: 0 nếu index bảo đảm duy nhất, 1 nếu cho phép trùng.
- **Cardinality**: số giá trị khác nhau được ước lượng cho index hoặc tiền tố index đến cột hiện tại.
- **Sub_part**: độ dài tiền tố được lập chỉ mục nếu index dùng prefix.
- **Index_type**: loại index, thường là BTREE với index InnoDB thông dụng.

Ví dụ index ghép:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

SHOW INDEX có thể trả về ba dòng cho index này. Cardinality tại dòng tenant_id mô tả số tenant khác nhau; tại dòng status mô tả số tổ hợp tenant_id + status; tại dòng created_at mô tả số tổ hợp tenant_id + status + created_at được ước lượng. Không đọc cardinality của cột thứ hai như thể đó là số status riêng biệt trên toàn bảng.

Có thể đọc thống kê từ Information Schema:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    CARDINALITY,
    NON_UNIQUE,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Cardinality của InnoDB là thống kê dựa trên lấy mẫu các trang index. Nó có thể sai lệch so với số distinct thực tế, đặc biệt khi dữ liệu phân bố không đều hoặc bảng thay đổi đáng kể. Số dòng trong INFORMATION_SCHEMA.TABLES cũng thường là ước lượng với InnoDB. Không nên lấy hai con số ước lượng này làm bằng chứng tuyệt đối cho một quyết định thiết kế.

Nếu cần số distinct chính xác cho một phân tích trên bảng có kích thước phù hợp, có thể dùng:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT status) AS distinct_status,
    ROUND(
        COUNT(DISTINCT status) / NULLIF(COUNT(*), 0),
        8
    ) AS index_selectivity
FROM orders;
~~~

COUNT(DISTINCT column) bỏ qua giá trị NULL. Nếu cột nullable và tỷ lệ NULL có ý nghĩa với truy vấn, hãy thống kê riêng NULL. Trên bảng rất lớn, COUNT(*) và COUNT(DISTINCT) có thể đọc nhiều dữ liệu; hãy cân nhắc chạy trên replica phân tích, trong thời điểm phù hợp hoặc dùng phương pháp lấy mẫu khi mục tiêu chỉ là khảo sát sơ bộ.

## 3. Đo phân bố từng giá trị thay vì chỉ nhìn số distinct

Giả sử orders có một triệu dòng và status chỉ có bốn giá trị. Thống kê distinct bằng 4 không cho biết trạng thái nào phổ biến. Hãy đếm số dòng theo từng giá trị:

~~~sql
SELECT
    status,
    COUNT(*) AS rows_for_value
FROM orders
GROUP BY status
ORDER BY rows_for_value DESC;
~~~

Để xem tỷ lệ của từng nhóm so với toàn bảng:

~~~sql
SELECT
    grouped.status,
    grouped.rows_for_value,
    totals.total_rows,
    ROUND(
        100.0 * grouped.rows_for_value / NULLIF(totals.total_rows, 0),
        2
    ) AS percent_of_table
FROM (
    SELECT status, COUNT(*) AS rows_for_value
    FROM orders
    GROUP BY status
) AS grouped
CROSS JOIN (
    SELECT COUNT(*) AS total_rows
    FROM orders
) AS totals
ORDER BY grouped.rows_for_value DESC;
~~~

Giả sử kết quả minh họa như sau:

| status | Số dòng | Tỷ lệ |
|---|---:|---:|
| PAID | 950.000 | 95% |
| PENDING | 35.000 | 3,5% |
| CANCELLED | 14.000 | 1,4% |
| FAILED | 1.000 | 0,1% |

Các con số này chỉ minh họa cho một bảng có phân bố lệch. Trong thực tế, hãy đo trên dữ liệu của chính hệ thống và tại thời điểm có ý nghĩa với workload.

Điều kiện status = 'FAILED' chỉ khớp 0,1% số dòng, nên index có thể giúp tìm nhanh nhóm nhỏ này. Điều kiện status = 'PAID' khớp 95% số dòng; đọc index rồi quay lại bảng để lấy hầu hết bản ghi có thể tốn kém hơn quét bảng tuần tự. Vì thế, cùng một index có thể hữu ích cho một giá trị và không được optimizer chọn cho giá trị khác.

Một ví dụ khác là tenant_id. Giả sử tenant 42 tạo ra 70% dữ liệu, còn hàng nghìn tenant khác chia nhau 30% còn lại. Cardinality của tenant_id có thể rất cao, nhưng điều kiện tenant_id = 42 vẫn khớp phần lớn bảng. Chỉ nhìn số tenant khác nhau sẽ bỏ lỡ sự lệch này.

## 4. Vì sao phân bố lệch ảnh hưởng quyết định dùng index

Optimizer cần ước lượng số dòng sẽ đọc và chi phí của các cách thực thi có thể có. Khi ước lượng đúng, nó có thể chọn giữa:

- Quét toàn bảng hoặc toàn phạm vi dữ liệu cần thiết.
- Tìm các entry qua secondary index rồi đọc dòng tương ứng trong clustered index.
- Dùng covering index nếu các cột truy vấn đã có trong index.
- Kết hợp điều kiện trên nhiều cột hoặc nhiều index khi kế hoạch đó có chi phí thấp hơn.

Một secondary index BTREE có thể giảm đáng kể số dòng cần đọc nếu điều kiện chọn ra một phần nhỏ dữ liệu. Nhưng nếu điều kiện khớp phần lớn bảng, việc duyệt index rồi thực hiện nhiều lần truy cập đến clustered index có thể đắt hơn một lần quét tuần tự.

Do đó, **index trên cột ít giá trị khác nhau không tự động là sai**:

- Nếu một trạng thái hiếm được truy vấn thường xuyên, index status có thể hữu ích.
- Nếu hầu hết truy vấn tìm trạng thái phổ biến, index status riêng lẻ có thể không được chọn.
- Nếu truy vấn luôn lọc theo tenant và khoảng thời gian, index ghép tenant_id + created_at có thể hữu ích hơn index status riêng lẻ.
- Nếu truy vấn chỉ cần các cột đã có trong index, covering index có thể tránh đọc thêm dòng trong clustered index.

Một index cũng có chi phí: chiếm dung lượng, tăng công việc ghi khi INSERT/UPDATE/DELETE, làm tăng chi phí bảo trì và có thể khiến optimizer phải cân nhắc thêm nhiều kế hoạch. Hãy tạo index để phục vụ truy vấn thực tế, không phải chỉ để làm cardinality trông đẹp hơn.

## 5. Dùng EXPLAIN để kiểm tra ước lượng của optimizer

Bắt đầu với truy vấn đại diện cho workload:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE status = 'FAILED';
~~~

Trong kết quả EXPLAIN dạng bảng, chú ý:

- **type**: kiểu truy cập, từ các dạng quét như ALL đến các dạng truy cập index như range, ref hoặc const. Đây là tín hiệu cần đọc cùng những cột khác, không phải thang điểm tuyệt đối.
- **possible_keys**: các index optimizer xem là ứng viên.
- **key**: index thực sự được chọn, nếu có.
- **key_len**: độ dài phần index được dùng.
- **rows**: số dòng được ước lượng cần đọc ở bước đó.
- **filtered**: tỷ lệ phần trăm dòng ước lượng còn lại sau điều kiện lọc bổ sung tại bước đó.
- **Extra**: thông tin bổ sung như Using where, Using index hoặc Using index condition.

Nếu key là NULL, optimizer không chọn index cho bước truy cập đó. Điều này có thể hoàn toàn hợp lý nếu điều kiện khớp phần lớn bảng, index không phù hợp với thứ tự cột, hoặc chi phí dự kiến của index cao hơn quét bảng.

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE cung cấp số liệu thực thi thực tế cho SELECT:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE status = 'FAILED';
~~~

EXPLAIN ANALYZE thực sự chạy câu truy vấn để đo thời gian và số dòng thực tế ở các iterator. Chỉ chạy trên truy vấn đọc đã hiểu rõ phạm vi; một truy vấn đắt tiền vẫn có thể tiêu thụ CPU, I/O và tài nguyên production. Không dùng EXPLAIN ANALYZE như lệnh chỉ phân tích tĩnh.

Khi so sánh kế hoạch, hãy nhìn chênh lệch giữa số dòng ước lượng và số dòng thực tế:

- Ước lượng gần thực tế: optimizer có thông tin tương đối tốt cho điều kiện đó.
- Ước lượng thấp hơn thực tế rất nhiều: optimizer có thể đánh giá thấp lượng dữ liệu phải đọc, dẫn đến chọn join order hoặc access path không phù hợp.
- Ước lượng cao hơn thực tế rất nhiều: optimizer có thể bỏ qua một index hữu ích hoặc chọn kế hoạch tốn kém hơn cần thiết.
- Sai lệch rõ rệt ở một giá trị nhưng không ở giá trị khác: cần kiểm tra data skew, histogram và cách truyền tham số.

Chi phí và thời gian trong EXPLAIN ANALYZE phụ thuộc dữ liệu, cache, tải máy chủ và môi trường. Một lần chạy không đủ để kết luận hiệu năng ổn định; hãy kiểm tra nhiều lần trong điều kiện có thể so sánh.

## 6. Làm mới thống kê index

Khi dữ liệu thay đổi lớn, thống kê cũ có thể không còn đại diện cho bảng. Có thể yêu cầu MySQL cập nhật thống kê bằng:

~~~sql
ANALYZE TABLE orders;
~~~

Sau đó kiểm tra lại:

~~~sql
SHOW INDEX FROM orders;
~~~

ANALYZE TABLE cập nhật thống kê phục vụ optimizer; nó không tạo thêm index và không thay đổi dữ liệu nghiệp vụ. Với InnoDB, thống kê cardinality dựa trên lấy mẫu nên vẫn là ước lượng. Việc phân tích bảng có thể cần đọc dữ liệu và tiêu thụ tài nguyên; hãy chọn thời điểm phù hợp cho bảng lớn hoặc hệ thống tải cao.

Nếu vừa nạp một lượng dữ liệu lớn, xóa phần lớn dữ liệu, thay đổi mạnh tỷ lệ trạng thái hoặc chuyển workload sang một nhóm tenant khác, hãy đánh giá lại thống kê thay vì giả định cardinality cũ vẫn đúng.

## 7. Dùng histogram để mô tả phân bố lệch

Cardinality chỉ mô tả số lượng giá trị khác nhau. Histogram bổ sung thông tin về cách giá trị phân bố trong một cột, giúp optimizer ước lượng tốt hơn khi một số giá trị xuất hiện nhiều hơn hẳn các giá trị còn lại.

Trong MySQL 8.0, có thể tạo hoặc cập nhật histogram cho một hay nhiều cột:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, tenant_id
WITH 64 BUCKETS;
~~~

MySQL hỗ trợ hai dạng histogram chính:

- **Singleton histogram**: có một bucket cho từng giá trị riêng biệt. Dạng này phù hợp với cột có số giá trị distinct tương đối nhỏ.
- **Equi-height histogram**: chia phân bố thành các bucket đại diện cho số dòng xấp xỉ bằng nhau; ranh giới bucket mô tả khoảng giá trị và tần suất tích lũy. Dạng này hữu ích khi cột có nhiều giá trị khác nhau.

Số bucket là giới hạn chi tiết mà bạn yêu cầu cho histogram. Nhiều bucket hơn có thể mô tả phân bố chi tiết hơn nhưng cũng làm tăng kích thước thống kê. Không nên chọn số bucket lớn nhất một cách máy móc; hãy đối chiếu chất lượng ước lượng với chi phí và workload.

Có thể xem histogram trong Information Schema:

~~~sql
SELECT
    SCHEMA_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    JSON_PRETTY(HISTOGRAM) AS histogram_json
FROM information_schema.column_statistics
WHERE SCHEMA_NAME = DATABASE()
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME IN ('status', 'tenant_id');
~~~

Trong JSON histogram, các trường quan trọng có thể bao gồm loại histogram, số bucket, tỷ lệ NULL, tỷ lệ lấy mẫu, thời điểm cập nhật và các bucket cùng tần suất tích lũy. Đây là thông tin thống kê, không phải bản sao từng dòng dữ liệu.

Nếu cần bỏ histogram đã tạo:

~~~sql
ANALYZE TABLE orders
DROP HISTOGRAM ON status, tenant_id;
~~~

Histogram của MySQL là thống kê theo từng cột. Nó không mô tả đầy đủ mối tương quan giữa nhiều cột. Ví dụ, nếu FAILED hầu như chỉ xuất hiện ở một tenant cụ thể, histogram riêng của status và histogram riêng của tenant_id không nhất thiết mô tả được xác suất kết hợp của hai điều kiện đó. Index ghép và thống kê tiền tố index có thể bổ sung thông tin về tổ hợp cột, nhưng vẫn cần kiểm tra kế hoạch thực thi thực tế.

Histogram cũng có thể trở nên cũ khi dữ liệu thay đổi mạnh. Hãy xem thời điểm cập nhật và chủ động làm mới khi có thay đổi phân bố đáng kể. Đừng nhầm việc tự động cập nhật thống kê index của InnoDB với việc làm mới histogram đã tạo.

## 8. Thiết kế index theo điều kiện truy vấn và độ lệch

Giả sử truy vấn thường lấy các đơn hàng lỗi của một tenant trong một khoảng thời gian:

~~~sql
SELECT order_id, created_at, amount
FROM orders
WHERE tenant_id = 17
  AND status = 'FAILED'
  AND created_at >= '2026-10-01'
  AND created_at <  '2026-11-01'
ORDER BY created_at;
~~~

Một index ghép có thể phù hợp:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Hai điều kiện đầu là so sánh bằng; cột created_at được dùng cho khoảng thời gian. Thứ tự cột index cần dựa trên tập truy vấn thực tế, tính chọn lọc, kiểu điều kiện và yêu cầu sắp xếp. Thứ tự các điều kiện trong mệnh đề WHERE không quyết định thứ tự cột index.

Nếu truy vấn khác thường chỉ lọc theo status và created_at mà không có tenant_id, index bắt đầu bằng tenant_id có thể không phục vụ tốt truy vấn đó vì nguyên tắc leftmost prefix. Có thể cần một index khác, nhưng chỉ thêm khi workload và phép đo chứng minh lợi ích đủ lớn.

So sánh hai trường hợp:

~~~sql
-- Truy vấn cho một tenant và một khoảng thời gian hẹp.
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 17
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-11-02';

-- Truy vấn cho tenant chiếm phần lớn dữ liệu và khoảng thời gian rộng.
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND created_at >= '2025-01-01'
  AND created_at <  '2027-01-01';
~~~

Cùng dùng tenant_id, nhưng truy vấn thứ nhất có thể chỉ đọc một tập nhỏ. Truy vấn thứ hai có thể khớp phần lớn dữ liệu của tenant 42. Index (tenant_id, created_at) có thể hữu ích rõ rệt cho truy vấn thứ nhất; optimizer có thể chọn quét một phạm vi lớn hoặc cách truy cập khác cho truy vấn thứ hai tùy chi phí thực tế.

Với cột status có ít giá trị:

- Index status đơn có thể hữu ích cho trạng thái hiếm như FAILED.
- Index status đơn có thể không hấp dẫn với trạng thái chiếm gần toàn bảng như PAID.
- Index (status, created_at) có thể hữu ích khi truy vấn luôn lọc trạng thái và giới hạn thời gian.
- Nếu truy vấn chỉ lấy một vài cột, một covering index phù hợp có thể giảm lần đọc clustered index; đổi lại index lớn hơn và làm tăng chi phí ghi.

Không có thứ tự index ghép đúng cho mọi truy vấn. Hãy lập danh sách truy vấn quan trọng, xác định cột bằng, cột range, cột join, cột order/group và các cột cần trả về, sau đó thử index ứng viên bằng EXPLAIN và phép đo thực tế.

## 9. Phân biệt thống kê cột đơn và tương quan giữa các cột

Giả sử một hệ thống có quy tắc nghiệp vụ khiến trạng thái FAILED chỉ xuất hiện trong một nhóm tenant nhất định. Nếu xem từng cột riêng lẻ, bạn có thể thấy:

- status có 4 giá trị và FAILED rất hiếm.
- tenant_id có hàng nghìn giá trị và tenant 42 rất phổ biến.

Nhưng truy vấn kết hợp status = 'FAILED' AND tenant_id = 42 có thể có phân bố rất khác so với giả định độc lập giữa hai cột. Histogram đơn cột không thể diễn tả đầy đủ mối tương quan này.

Trong tình huống đó:

1. Đo số dòng thực tế theo tổ hợp các điều kiện quan trọng.
2. Kiểm tra cardinality của từng tiền tố index ghép.
3. Xem ước lượng và actual rows trong EXPLAIN ANALYZE.
4. Thử index ghép theo thứ tự phù hợp với workload.
5. Theo dõi kế hoạch sau khi dữ liệu tăng hoặc phân bố thay đổi.

Ví dụ khảo sát phân bố kết hợp:

~~~sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS rows_for_combination
FROM orders
GROUP BY tenant_id, status
ORDER BY rows_for_combination DESC
LIMIT 30;
~~~

Truy vấn này giúp nhận ra các tổ hợp phổ biến hoặc hiếm. Trên bảng lớn, việc GROUP BY có thể tốn tài nguyên; hãy chạy trong môi trường phân tích hoặc giới hạn phạm vi theo thời gian nếu phù hợp.

## 10. Quy trình điều tra khi optimizer chọn index không như mong đợi

Khi một truy vấn chậm hoặc kế hoạch thay đổi, thực hiện theo thứ tự:

1. **Xác định truy vấn đại diện.** Ghi lại SQL, tham số, tần suất chạy, độ trễ và số dòng kết quả. Một truy vấn có cùng cấu trúc nhưng tham số khác nhau có thể có selectivity rất khác.
2. **Xem index hiện tại.** Dùng SHOW INDEX để kiểm tra cột, thứ tự cột, cardinality và index nào đang tồn tại.
3. **Đo phân bố dữ liệu.** Dùng GROUP BY, COUNT(DISTINCT) và thống kê theo nhóm để xác định giá trị hiếm, giá trị phổ biến, NULL và tenant lệch.
4. **Đọc kế hoạch.** Dùng EXPLAIN để xem key, type, rows và filtered. Dùng EXPLAIN ANALYZE trên truy vấn đọc phù hợp để so sánh estimated rows với actual rows.
5. **Kiểm tra độ mới của thống kê.** Cân nhắc ANALYZE TABLE khi index statistics đã cũ; tạo hoặc cập nhật histogram nếu phân bố lệch ở cột phù hợp.
6. **Thử index theo workload.** Tạo index ứng viên trên môi trường kiểm thử hoặc theo quy trình thay đổi đã duyệt. Đánh giá cả truy vấn đọc và chi phí ghi.
7. **Đo lại và theo dõi.** So sánh thời gian, số dòng đọc, kế hoạch, tải CPU/I/O và tác động lên các truy vấn khác. Xóa index dư thừa theo quy trình quản lý schema nếu đã chứng minh không còn cần thiết.

Không nên ép optimizer dùng một index chỉ vì EXPLAIN hiện tại không chọn index bạn mong đợi. Trước hết hãy xác minh dữ liệu, thống kê, phân bố và chi phí. Index hint có thể hữu ích trong trường hợp đặc biệt đã đo đạc, nhưng cũng có thể khóa hệ thống vào một kế hoạch kém khi dữ liệu thay đổi.

## 11. Những lỗi suy luận thường gặp

**Cardinality cao nghĩa là mọi truy vấn đều nhanh.** Cardinality cao cho thấy nhiều giá trị khác nhau, nhưng một điều kiện cụ thể vẫn có thể khớp nhiều dòng. Hãy đo filter selectivity cho giá trị thực tế.

**Cột chỉ có vài giá trị thì không cần index.** Một giá trị hiếm trong cột ít cardinality vẫn có thể tìm rất nhanh qua index. Phân bố từng giá trị và truy vấn quan trọng hơn kết luận dựa trên số distinct.

**Optimizer không chọn index nghĩa là index bị hỏng.** Có thể quét bảng rẻ hơn, điều kiện không dùng được tiền tố index, thống kê sai lệch hoặc truy vấn trả về quá nhiều dòng. Hãy đọc toàn bộ kế hoạch.

**Cardinality trong SHOW INDEX là con số chính xác.** Đây là ước lượng dựa trên thống kê index của InnoDB. Dùng ANALYZE TABLE để làm mới và so sánh với phép đo thực tế khi cần.

**Histogram thay thế index.** Histogram là thống kê giúp optimizer ước lượng phân bố; nó không tạo đường truy cập dữ liệu. Muốn truy cập nhanh, truy vấn vẫn cần một access path phù hợp.

**Histogram của từng cột mô tả được mọi tổ hợp.** Histogram đơn cột không nắm đầy đủ tương quan giữa các cột. Cần xem phân bố kết hợp và index ghép.

**Index ghép càng nhiều cột càng tốt.** Index rộng làm tăng dung lượng và chi phí ghi. Chọn các cột theo truy vấn thực tế, thứ tự điều kiện và khả năng dùng leftmost prefix.

**Một lần EXPLAIN ANALYZE chứng minh truy vấn luôn nhanh.** Thời gian chịu ảnh hưởng của cache, tải máy chủ, kích thước dữ liệu và tham số. Hãy đo nhiều lần và theo dõi trong điều kiện gần production.

## 12. Checklist đánh giá selectivity và data skew

Trước khi thêm, xóa hoặc thay đổi một index, hãy trả lời:

- Cardinality đang nói đến cột đơn hay tiền tố nào của index ghép?
- Tỷ lệ distinct/total và tỷ lệ matching/total đang được hiểu đúng chiều chưa?
- Các giá trị trong cột có phân bố đồng đều hay lệch mạnh?
- Giá trị mà truy vấn thực sự tìm là phổ biến hay hiếm?
- Cột có nhiều NULL hoặc một vài tenant chiếm phần lớn dữ liệu không?
- Cardinality trong SHOW INDEX có còn đại diện cho dữ liệu hiện tại không?
- EXPLAIN ước lượng bao nhiêu dòng và EXPLAIN ANALYZE thực tế đọc bao nhiêu?
- Histogram có thể cải thiện ước lượng cho cột bị lệch không?
- Truy vấn có điều kiện trên nhiều cột tương quan mà histogram đơn cột không mô tả được không?
- Index ghép có đúng thứ tự leftmost prefix, equality và range không?
- Lợi ích đọc có bù được dung lượng và chi phí ghi của index không?

Khi đánh giá index, hãy bắt đầu từ truy vấn và phân bố dữ liệu mà truy vấn gặp phải. Cardinality cho biết độ đa dạng, selectivity cho biết mức thu hẹp và histogram giúp mô tả tần suất. Kết hợp các thông tin này với EXPLAIN, số liệu thực tế và workload sẽ giúp bạn hiểu vì sao MySQL chọn một access path và thiết kế chỉ mục phù hợp khi dữ liệu tiếp tục tăng hoặc lệch đi.
