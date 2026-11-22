# Xử lý ước lượng sai do dữ liệu lệch hoặc thống kê lỗi thời

Optimizer chọn cách truy cập dữ liệu và thứ tự thực thi dựa trên ước lượng số hàng trung gian. Nếu ước lượng sai, một kế hoạch có thể chọn Nested Loop cho tập dữ liệu rất lớn, cấp thiếu bộ nhớ cho Hash Join, sắp xếp trên tập hàng lớn hơn dự kiến hoặc đọc một index nhiều lần. Truy vấn khi đó có thể chậm đột ngột dù SQL không thay đổi.

Hai nguyên nhân thường gặp là **thống kê lỗi thời** và **dữ liệu lệch (skew)**. Thống kê lỗi thời mô tả một trạng thái dữ liệu đã cũ sau nhiều lần insert, update, delete hoặc nạp batch. Dữ liệu lệch xuất hiện khi một số giá trị chiếm tỷ lệ lớn, còn nhiều giá trị khác hiếm; một histogram quá thô hoặc thống kê không ghi nhận heavy hitter có thể khiến optimizer đánh giá sai selectivity. Ngoài ra, tương quan giữa các cột và parameter sensitivity cũng có thể làm ước lượng sai dù thống kê từng cột vẫn mới.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần xác định chính xác operator đầu tiên có sai lệch giữa estimated rows và actual rows, tìm lý do thống kê không mô tả đúng dữ liệu, sau đó chọn cách cập nhật hoặc mở rộng thống kê, điều chỉnh truy vấn hay xử lý plan theo bằng chứng. Bài học này trình bày quy trình capstone từ phát hiện, chẩn đoán, khắc phục đến benchmark và xác minh tính đúng đắn trên PostgreSQL, MySQL, SQL Server và Oracle.

## 1. Cardinality estimate ảnh hưởng execution plan như thế nào?

Cardinality là số hàng mà một thao tác hoặc biểu thức truy vấn trả về. Optimizer ước lượng cardinality ở từng bước để tính chi phí của các phương án thực thi.

Ví dụ:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PENDING'
  AND region_id = 7;
~~~

Optimizer cần ước lượng:

- Có bao nhiêu hàng trong bảng orders.
- Có bao nhiêu hàng thỏa status = 'PENDING'.
- Có bao nhiêu hàng thỏa region_id = 7.
- Hai điều kiện kết hợp còn lại bao nhiêu hàng.
- Có thể dùng index nào và cần đọc bao nhiêu page.
- Nếu truy vấn tiếp tục JOIN, có bao nhiêu hàng ở phía trong và phía ngoài.

Các estimate này ảnh hưởng đến:

- Index seek/scan hay table scan.
- Thứ tự JOIN.
- Nested Loop, Hash Join hay Merge Join.
- Sort hoặc Aggregate strategy.
- Memory grant hoặc work area.
- Parallelism và số worker.
- Khả năng spill ra temporary storage.

Sai số ở bước đầu có thể lan truyền qua nhiều operator. Vì vậy, khi đọc plan, hãy tìm **operator đầu tiên có chênh lệch lớn giữa estimated rows và actual rows**, thay vì chỉ nhìn operator cuối cùng chậm nhất.

## 2. Nhận diện cardinality misestimation

Trong execution plan, so sánh số hàng optimizer dự kiến với số hàng thực tế. Cần chú ý định nghĩa của từng công cụ: một số plan hiển thị số hàng trung bình mỗi lần chạy, một số hiển thị tổng số hàng, và operator có thể được thực hiện nhiều lần.

### 2.1. Sai số theo tỷ lệ

Một cách định lượng đơn giản:

\[
Q\text{-error}=\max\left(\frac{Actual}{Estimated},\frac{Estimated}{Actual}\right)
\]

Nếu estimated là 100 và actual là 10.000, Q-error bằng 100. Nếu estimated là 10.000 và actual là 100, Q-error cũng bằng 100. Trường hợp estimated hoặc actual bằng 0 cần quy ước riêng để tránh chia cho 0; khi đó hãy ghi rõ sai lệch tuyệt đối và việc optimizer dự đoán không có hàng trong khi thực tế có hàng.

Q-error lớn không tự động chứng minh truy vấn chậm. Hãy kết hợp:

- Số lần operator được gọi.
- CPU time và elapsed time.
- Logical/physical reads.
- Memory grant và spill.
- Join strategy và thứ tự JOIN.
- Wait events và thời gian chờ.

Một estimate sai ở operator ít tốn kém có thể không ảnh hưởng đáng kể. Một estimate sai ở đầu vào của Nested Loop được lặp hàng triệu lần có thể làm chi phí tăng rất lớn.

### 2.2. Estimated rows và actual rows cần cùng ngữ cảnh

Khi đọc plan:

1. Xác định operator và predicate.
2. Ghi estimated rows.
3. Ghi actual rows.
4. Ghi số lần operator được thực thi.
5. So sánh số hàng đầu vào và đầu ra.
6. Xác định sai lệch bắt đầu từ operator nào.

Với operator chạy nhiều lần, không nhân hoặc không chia số hàng một cách tùy tiện. Đọc chú thích trong plan của đúng DBMS để biết giá trị hiển thị là per execution hay cumulative.

### 2.3. Các dấu hiệu plan bị ảnh hưởng

- Nested Loop có inner index lookup lặp rất nhiều lần.
- Hash Join hoặc Hash Aggregate spill ra đĩa do memory estimate thấp.
- Sort cần xử lý nhiều hàng hơn dự kiến.
- Optimizer chọn scan lớn dù predicate thường rất chọn lọc.
- Optimizer chọn index lookup cho một giá trị thực tế trả về phần lớn bảng.
- Join order tạo ra tập trung gian rất lớn.
- Parallel workers nhận khối lượng không đều do skew.
- Runtime thay đổi mạnh theo giá trị tham số dù SQL giống nhau.

## 3. Thống kê optimizer chứa thông tin gì?

Thống kê mô tả dữ liệu để optimizer ước lượng selectivity và cardinality. Tùy DBMS, thống kê có thể gồm:

- Row count và số page/block.
- Number of distinct values (NDV).
- Số giá trị NULL.
- Minimum/maximum.
- Histogram hoặc bucket distribution.
- Most common values (MCV) và tần suất.
- Density hoặc average frequency.
- Correlation/ordering information.
- Thống kê mở rộng cho nhóm cột hoặc biểu thức.
- Thống kê ở cấp partition và toàn bảng.

Thống kê không phải bản sao đầy đủ của dữ liệu. Nó là mô hình xấp xỉ, có thể dựa trên sampling và có giới hạn số bucket hoặc số giá trị lưu.

### 3.1. NDV và selectivity

Nếu một bảng có 10 triệu hàng và cột status có 4 giá trị, NDV bằng 4. Một ước lượng uniform đơn giản có thể giả định mỗi giá trị chiếm khoảng 25%.

Nhưng dữ liệu thực có thể:

| Status | Tỷ lệ |
|---|---:|
| COMPLETED | 78% |
| PENDING | 2% |
| CANCELLED | 15% |
| REFUNDED | 5% |

Predicate status = 'PENDING' chỉ trả về khoảng 2%, trong khi giả định uniform dự đoán 25%. Sai số hơn 12 lần có thể làm optimizer chọn plan không phù hợp.

### 3.2. Histogram và heavy hitters

Histogram chia miền giá trị thành bucket để mô tả phân bố. MCV lưu riêng những giá trị xuất hiện thường xuyên nhất. Nếu một vài giá trị chiếm phần lớn dữ liệu, thông tin MCV có thể giúp optimizer ước lượng tốt hơn.

Histogram có giới hạn độ phân giải. Nếu phân phối rất lệch hoặc có nhiều giá trị hiếm, một histogram thưa có thể không thể hiện hết đặc điểm. Sampling cũng có thể bỏ lỡ một số giá trị hiếm hoặc ước lượng sai tỷ lệ của nhóm nhỏ.

### 3.3. Statistics không tự động phản ánh mọi tương quan

Thống kê riêng cho region_id và status không nhất thiết mô tả được quan hệ giữa hai cột. Nếu PENDING tập trung ở một vài region, selectivity của hai điều kiện kết hợp không bằng tích xác suất riêng lẻ.

Đây là lý do một bảng có statistics mới vẫn có thể có cardinality estimate sai.

## 4. Phân biệt bốn nguyên nhân thường gặp

Một estimate sai có thể đến từ nhiều nguyên nhân. Trước khi chạy ANALYZE hoặc thay plan, hãy phân loại giả thuyết.

| Nguyên nhân | Dấu hiệu | Phép kiểm tra |
|---|---|---|
| Statistics lỗi thời | Row count hoặc phân bố đã thay đổi nhiều sau lần cập nhật stats | So thời điểm stats, modification count và dữ liệu hiện tại |
| Skew/heavy hitters | Một vài giá trị có tần suất vượt xa phần còn lại | Histogram, MCV, top-N frequency và predicate theo giá trị nóng/hiếm |
| Tương quan cột | Estimate từng predicate có vẻ hợp lý nhưng estimate kết hợp sai | Cross-tab, conditional frequency, extended statistics |
| Parameter sensitivity | Cùng SQL nhưng plan hoặc runtime khác theo tham số | Chạy cùng plan với giá trị phổ biến, hiếm và giá trị biên |

Có thể tồn tại nhiều nguyên nhân cùng lúc. Ví dụ, statistics vừa lỗi thời vừa không đủ histogram để mô tả skew; parameter sniffing lại làm một plan được tối ưu cho giá trị hiếm dùng cho giá trị nóng.

## 5. Nguyên nhân 1: statistics lỗi thời

Statistics có thể mất tính đại diện khi dữ liệu thay đổi đáng kể:

- Bulk insert hoặc ETL nạp lượng lớn hàng.
- Delete theo batch hoặc retention.
- Update làm thay đổi phân bố cột lọc.
- Thêm tenant lớn hoặc chiến dịch tạo traffic mới.
- Một partition mới tăng nhanh.
- Dữ liệu lịch sử được backfill.
- Phân bố trạng thái thay đổi theo vòng đời nghiệp vụ.

Một bảng tăng gấp đôi số hàng nhưng statistics vẫn phản ánh kích thước cũ có thể khiến optimizer ước lượng sai. Ngay cả khi row count tổng gần như không đổi, tỷ lệ status hoặc region thay đổi cũng có thể làm predicate estimate lỗi.

### 5.1. Kiểm tra thời điểm cập nhật

Hãy xem:

- Last analyze/update time.
- Số hàng hoặc modification counter kể từ lần cập nhật.
- Auto-statistics có được bật và chạy thành công không.
- Statistics có bị khóa, stale hoặc không được chọn cập nhật không.
- Bảng/partition có được load ngoài quy trình thông thường không.

Không dùng tuổi statistics như tiêu chí duy nhất. Một bảng ít thay đổi có thể dùng statistics cũ mà vẫn đúng; một bảng thay đổi mạnh trong vài phút có thể cần cập nhật sớm.

### 5.2. Modification threshold

Một số DBMS tự cập nhật statistics khi số thay đổi vượt ngưỡng. Ngưỡng và thuật toán thay đổi theo phiên bản, kích thước bảng, cấu hình và loại statistics. Không giả định mọi hệ quản trị dùng cùng một tỷ lệ phần trăm.

Với bảng lớn, một lượng thay đổi tuyệt đối rất lớn có thể vẫn nhỏ theo tỷ lệ. Ngược lại, một thay đổi nhỏ ở cột có skew mạnh có thể làm estimate của predicate quan trọng thay đổi đáng kể.

### 5.3. Khắc phục

- Cập nhật statistics cho bảng/cột liên quan.
- Xác minh auto-statistics và maintenance schedule.
- Cân nhắc statistics sampling phù hợp.
- Cập nhật statistics partition/global theo đặc điểm DBMS.
- Chạy lại query plan và so estimate với actual.
- Theo dõi plan regression và tác động tới workload khác.

Không cập nhật toàn bộ statistics trên production một cách mù quáng trong giờ cao điểm. Thu thập stats có thể tiêu thụ CPU/I/O, khóa metadata hoặc làm thay đổi plan của nhiều query.

## 6. Nguyên nhân 2: dữ liệu lệch và heavy hitters

Dữ liệu lệch xảy ra khi phân phối giá trị không đồng đều. Một cột tenant_id có thể có hàng nghìn tenant nhỏ và một tenant lớn chiếm 40% số hàng. Một cột status có thể có giá trị PENDING chỉ 1% nhưng tăng đột biến trong giờ cao điểm.

### 6.1. Tại sao skew làm optimizer khó ước lượng?

Optimizer cần dự đoán số hàng của predicate trước khi chạy. Nếu statistics chỉ lưu NDV và giả định phân bố đồng đều, giá trị nóng sẽ bị đánh giá thấp còn giá trị hiếm có thể bị đánh giá cao.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = 42;
~~~

Nếu tenant 42 chiếm 35% bảng, index lookup có thể phải truy cập rất nhiều page. Một scan tuần tự hoặc một phương án khác có thể rẻ hơn. Nhưng với tenant nhỏ chỉ chiếm 0,001%, index seek có thể hiệu quả.

Cùng một SQL structure có thể cần plan khác theo giá trị tham số.

### 6.2. Đo phân bố thực tế

~~~sql
SELECT tenant_id, COUNT(*) AS row_count
FROM orders
GROUP BY tenant_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Cú pháp giới hạn hàng cần điều chỉnh theo DBMS. Hãy tính thêm tỷ lệ top tenant trên tổng số hàng, NDV và percentile của số hàng mỗi tenant.

Với cột status:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM orders
GROUP BY status
ORDER BY row_count DESC;
~~~

Nếu dữ liệu quá lớn, có thể dùng thống kê DBMS hoặc sampling có kiểm soát để tránh full scan không cần thiết.

### 6.3. Khắc phục skew

- Tăng độ chi tiết histogram hoặc MCV nếu DBMS hỗ trợ.
- Tạo statistics riêng cho predicate quan trọng.
- Dùng filtered/partial statistics hoặc index phù hợp với nhóm dữ liệu nếu DBMS hỗ trợ.
- Tách workload theo tenant hoặc giá trị nóng nếu kiến trúc cho phép.
- Dùng query/plan phù hợp cho nhóm giá trị khác nhau khi có bằng chứng parameter sensitivity.
- Cập nhật stats sau khi phân bố thay đổi đáng kể.

Không tạo index cho mọi giá trị nóng. Index có thể làm tăng chi phí ghi và dung lượng, trong khi một giá trị chiếm 35% bảng vẫn có thể cần scan.

## 7. Nguyên nhân 3: tương quan giữa các cột

Giả sử bảng orders có hai cột:

- region_id.
- currency_code.

Trong dữ liệu thực, mỗi region thường dùng một hoặc hai currency chính. Hai cột có tương quan. Nếu optimizer giả định chúng độc lập, estimate của predicate kết hợp có thể sai.

Ví dụ:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE region_id = 3
  AND currency_code = 'VND';
~~~

Nếu region_id = 3 gần như luôn dùng VND, số hàng thỏa cả hai điều kiện có thể gần với số hàng region 3. Giả định độc lập có thể nhân selectivity của region với selectivity của VND và ước lượng thấp hơn thực tế.

### 7.1. Phân biệt skew đơn cột và correlation

- Nếu estimate sai ngay với region_id = 3 riêng lẻ, xem skew hoặc stale stats của region.
- Nếu estimate riêng của region và currency đều hợp lý nhưng estimate kết hợp sai, xem correlation.
- Nếu estimate thay đổi theo giá trị bind dù predicate giống nhau, xem parameter sensitivity.

### 7.2. Extended/multicolumn statistics

Một số DBMS hỗ trợ thống kê cho nhóm cột, dependency hoặc multicolumn distribution. Thống kê này giúp optimizer hiểu quan hệ giữa các predicate.

Ví dụ PostgreSQL:

~~~sql
CREATE STATISTICS orders_region_currency_stats
    (dependencies, mcv)
ON region_id, currency_code
FROM orders;

ANALYZE orders;
~~~

dependencies mô tả một số quan hệ phụ thuộc giữa cột; mcv ghi nhận tổ hợp giá trị phổ biến. Tùy phiên bản, loại statistics và query shape được hỗ trợ có giới hạn. Không phải mọi loại JOIN hoặc biểu thức đều tự động hưởng lợi từ extended statistics.

SQL Server có statistics nhiều cột, nhưng histogram chủ yếu được xây trên cột đầu tiên của statistics; density information có thể hỗ trợ ước lượng tổ hợp. Cần chọn thứ tự cột và kiểm tra estimate trong actual plan.

Oracle hỗ trợ column group statistics qua DBMS_STATS.CREATE_EXTENDED_STATS cho các trường hợp tương quan. Sau khi tạo, cần thu thập statistics và xác nhận optimizer sử dụng.

MySQL có histogram đơn cột và các cơ chế statistics riêng theo phiên bản; không giả định nó cung cấp cùng semantics với extended statistics của PostgreSQL hoặc Oracle. Nếu estimate kết hợp vẫn sai, cân nhắc query rewrite, schema/index phù hợp hoặc kiểm thử phiên bản optimizer.

## 8. Nguyên nhân 4: parameter sensitivity và plan cache

Một câu SQL có thể chạy với nhiều giá trị tham số có selectivity khác nhau. Optimizer có thể tạo một plan khi lần đầu thấy giá trị bind, sau đó plan được cache và tái sử dụng cho giá trị khác.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status;
~~~

Tenant lớn và status phổ biến có thể trả về hàng triệu hàng. Tenant nhỏ và status hiếm có thể trả về vài hàng. Một plan tối ưu cho tenant nhỏ có thể rất tệ cho tenant lớn, và ngược lại.

### 8.1. Parameter sniffing/peeking

Một số DBMS dùng giá trị tham số khi compile hoặc hard parse để ước lượng selectivity. Kế hoạch tạo ra có thể được cache và tái sử dụng. Nếu lần compile đầu gặp giá trị hiếm, plan index lookup có thể được tái sử dụng cho giá trị nóng.

Không phải mọi lần thực thi đều tái sử dụng cùng một plan. Hành vi phụ thuộc DBMS, phiên bản, bind mode, plan cache, adaptive feature, statistics và cách ứng dụng gửi câu lệnh.

### 8.2. Cách xác nhận

Chạy cùng query shape với:

- Giá trị phổ biến nhất.
- Giá trị trung bình.
- Giá trị hiếm.
- Giá trị mới hoặc tenant vừa tăng trưởng.
- NULL hoặc biên nếu ứng dụng cho phép.

So sánh estimated/actual rows, plan hash, CPU, reads và elapsed time. Thử trong môi trường kiểm thử hoặc dùng phương thức compile/plan inspection an toàn.

### 8.3. Khắc phục

Tùy DBMS, có thể:

- Cải thiện statistics/histogram để optimizer hiểu skew.
- Dùng cơ chế plan specialization/adaptive plan nếu có.
- Dùng Query Store plan forcing hoặc plan guide trong SQL Server khi đã xác minh.
- Dùng SQL Plan Management/baseline trong Oracle theo quy trình.
- Tách truy vấn theo workload class hoặc nhóm selectivity khi có cơ sở.
- Dùng recompile/hint có phạm vi hẹp nếu chứng minh được lợi ích và chi phí compile chấp nhận được.
- Điều chỉnh query để tránh một plan phải phục vụ hai phân bố quá khác nhau.

Không tắt parameterization hoặc ép literal trên mọi truy vấn theo phản xạ. Điều đó có thể làm plan cache phình to, tăng compile CPU và tạo nhiều plan không cần thiết.

## 9. Quy trình chẩn đoán theo từng bước

### Bước 1: Xác định query và cửa sổ sự cố

Ghi query fingerprint, thời điểm bắt đầu, số lần gọi, latency p50/p95/p99, CPU, reads, errors và workload liên quan. Dùng delta trong đúng cửa sổ thay vì chỉ nhìn counter tích lũy.

### Bước 2: Lấy execution plan thực tế

Lấy actual plan hoặc runtime statistics nếu có thể. Ghi:

- Estimated rows và actual rows.
- Số lần operator chạy.
- Join order và join algorithm.
- Predicate, residual filter và implicit conversion.
- Memory grant, spill và parallel workers.

Không chạy actual plan cho DML có side effect trên production nếu chưa có cách kiểm soát.

### Bước 3: Tìm operator sai lệch đầu tiên

Đọc plan từ scan/filter đầu vào lên trên. Xác định operator đầu tiên mà estimated rows khác actual rows đáng kể. Sai lệch ở đây thường là điểm bắt đầu để tìm statistics hoặc predicate problem.

### Bước 4: Kiểm tra dữ liệu thực tế

Đo row count, NDV, tỷ lệ NULL, top-N frequency, histogram và phân bố theo các cột filter. Với predicate kết hợp, tạo cross-tab hoặc conditional frequency.

### Bước 5: Kiểm tra trạng thái statistics

Xem last update, modification count, sampling, histogram/MCV, statistics target, auto-update và partition-level stats. Xác định liệu dữ liệu đã thay đổi sau lần thu thập gần nhất.

### Bước 6: Kiểm tra parameter sensitivity

So sánh plan và runtime với giá trị phổ biến, hiếm và trung bình. Kiểm tra plan cache, bind peeking/sniffing, child cursor hoặc parameter-sensitive plan feature tùy DBMS.

### Bước 7: Chọn thay đổi nhỏ nhất có thể kiểm chứng

Có thể là cập nhật statistics, tăng histogram detail, tạo extended stats, điều chỉnh query hoặc dùng plan control có phạm vi hẹp. Tránh thay nhiều yếu tố cùng lúc.

### Bước 8: Benchmark và xác minh

So sánh cùng dữ liệu, cùng tham số, cùng concurrency và cache condition. Kiểm tra cả query bị điều chỉnh lẫn workload khác, vì statistics update có thể làm thay đổi plan của nhiều câu SQL.

## 10. PostgreSQL: kiểm tra và cập nhật statistics

PostgreSQL thu thập statistics qua ANALYZE hoặc autovacuum/analyze. View pg_stats cung cấp thông tin ước lượng về NDV, NULL fraction, MCV và histogram.

### 10.1. Kiểm tra statistics

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'orders'
  AND attname IN ('tenant_id', 'status', 'region_id');
~~~

pg_stats là view thân thiện với quyền truy cập; nội dung có thể bị giới hạn theo quyền. Các giá trị histogram/MCV là mẫu thống kê, không phải danh sách đầy đủ mọi giá trị.

### 10.2. Kiểm tra thời điểm analyze

~~~sql
SELECT
    relname,
    n_live_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'orders';
~~~

Các bộ đếm là ước lượng và có thể reset hoặc chưa cập nhật tức thời. Hãy xem cùng lịch bulk load, autovacuum và thống kê của hệ thống.

### 10.3. Cập nhật statistics

~~~sql
ANALYZE orders;
~~~

Nếu cần histogram chi tiết hơn cho một cột:

~~~sql
ALTER TABLE orders
    ALTER COLUMN tenant_id SET STATISTICS 500;

ANALYZE orders (tenant_id);
~~~

Statistics target cao hơn có thể cho histogram/MCV chi tiết hơn nhưng tăng chi phí analyze, kích thước thống kê và thời gian planning. Không đặt target cực cao cho mọi cột; ưu tiên cột có skew và truy vấn quan trọng.

### 10.4. Extended statistics

~~~sql
CREATE STATISTICS orders_tenant_status_stats
    (dependencies, mcv, ndistinct)
ON tenant_id, status
FROM orders;

ANALYZE orders;
~~~

Chọn loại thống kê theo vấn đề:

- dependencies: một số dạng phụ thuộc giữa cột.
- mcv: tổ hợp giá trị phổ biến.
- ndistinct: ước lượng số nhóm khác nhau của tổ hợp cột.

Extended statistics có phạm vi áp dụng cụ thể; cần xem plan để xác nhận estimate thay đổi đúng. Không tạo statistics cho mọi tổ hợp cột vì có thể làm tăng thời gian analyze và quản lý.

### 10.5. Xác minh plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT *
FROM orders
WHERE tenant_id = 42
  AND status = 'PENDING';
~~~

So sánh estimated rows, actual rows, loops, buffers và thời gian. EXPLAIN ANALYZE thực thi query; chỉ dùng truy vấn phù hợp và dữ liệu thử nghiệm hoặc cửa sổ production được kiểm soát.

## 11. MySQL: histogram và persistent statistics

MySQL/InnoDB duy trì persistent statistics cho bảng/index khi được cấu hình. Histogram có thể được thu thập cho cột để mô tả phân bố, đặc biệt với predicate không được index hỗ trợ trực tiếp.

### 11.1. Cập nhật table statistics

~~~sql
ANALYZE TABLE orders;
~~~

Thao tác có thể cần tài nguyên và có hành vi khóa/metadata tùy phiên bản và storage engine. Kiểm tra trước trên phiên bản đang chạy và chọn thời điểm phù hợp.

### 11.2. Tạo histogram

Ví dụ:

~~~sql
ANALYZE TABLE orders
UPDATE HISTOGRAM ON status, region_id
WITH 100 BUCKETS;
~~~

Số bucket và loại histogram cần chọn theo NDV, skew và query pattern. Histogram không thay thế index và không mô tả mọi tương quan nhiều cột. Xem INFORMATION_SCHEMA.COLUMN_STATISTICS để kiểm tra histogram nếu quyền và phiên bản hỗ trợ.

### 11.3. Đọc EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE status = 'PENDING'
  AND region_id = 7;
~~~

MySQL hiển thị iterator timing và actual rows ở các phiên bản hỗ trợ. Đọc số hàng cùng loops; một iterator chạy nhiều lần có thể tạo tổng công việc lớn dù mỗi lần chỉ trả ít hàng.

### 11.4. Lưu ý

Histogram MySQL thường là thống kê đơn cột; không nên kỳ vọng nó giải quyết mọi tương quan giữa nhiều cột. Với predicate kết hợp, xem composite index, query rewrite và khả năng của optimizer trong phiên bản cụ thể.

## 12. SQL Server: statistics, histogram và parameter-sensitive plans

SQL Server dùng statistics để ước lượng cardinality. Statistics có thể được tạo tự động hoặc tạo thủ công; histogram được xây dựng trên cột đầu tiên của statistics, trong khi density information hỗ trợ một số ước lượng kết hợp.

### 12.1. Kiểm tra statistics

~~~sql
SELECT
    s.name AS statistics_name,
    sp.last_updated,
    sp.rows,
    sp.rows_sampled,
    sp.modification_counter
FROM sys.stats AS s
CROSS APPLY sys.dm_db_stats_properties(s.object_id, s.stats_id) AS sp
WHERE s.object_id = OBJECT_ID('dbo.Orders');
~~~

Tên schema/bảng cần đổi theo hệ thống. DMV có thể yêu cầu quyền phù hợp. modification_counter và rows_sampled giúp đánh giá mức thay đổi và sampling, nhưng cần xem cùng đặc điểm dữ liệu.

### 12.2. Xem histogram

~~~sql
DBCC SHOW_STATISTICS ('dbo.Orders', 'IX_Orders_TenantId')
WITH HISTOGRAM;
~~~

Histogram giúp thấy range, frequency và các giá trị được mô tả. Cần xem statistics nào đang được optimizer dùng cho predicate thực tế.

### 12.3. Cập nhật statistics

~~~sql
UPDATE STATISTICS dbo.Orders IX_Orders_TenantId
WITH FULLSCAN;
~~~

FULLSCAN đọc toàn bộ dữ liệu để thu thập stats, có thể tốn I/O/CPU. Có thể dùng sampling theo chính sách nếu phù hợp; lựa chọn cần được benchmark.

### 12.4. Filtered statistics

Nếu một nhóm dữ liệu đặc biệt quan trọng, filtered statistics có thể mô tả một tập con:

~~~sql
CREATE STATISTICS Stats_Orders_Pending
ON dbo.Orders (tenant_id)
WHERE status = 'PENDING';
~~~

Optimizer chỉ có thể sử dụng filtered statistics khi predicate và điều kiện truy vấn phù hợp với filter và các yêu cầu về parameterization. Kiểm tra actual plan để xác nhận.

### 12.5. Parameter Sensitive Plan

Các phiên bản SQL Server hỗ trợ Parameter Sensitive Plan optimization có thể duy trì nhiều plan variant cho các khoảng selectivity khác nhau trong những trường hợp đủ điều kiện. Khả năng và điều kiện phụ thuộc phiên bản, compatibility level và cấu hình.

Trước khi dùng hint như OPTION (RECOMPILE), Query Store plan forcing hoặc plan guide, hãy kiểm tra Query Store, actual plan, parameter values và chi phí compile. Plan forcing có thể bảo vệ khỏi regression nhưng cũng có thể giữ một plan không phù hợp khi dữ liệu tiếp tục thay đổi.

## 13. Oracle: histogram, column group và bind peeking

Oracle optimizer dùng table, column, index và extended statistics. DBMS_STATS quản lý việc thu thập statistics; histogram giúp mô tả skew, còn column group statistics mô tả tương quan.

### 13.1. Kiểm tra statistics

~~~sql
SELECT
    table_name,
    num_rows,
    blocks,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

Xem histogram:

~~~sql
SELECT
    column_name,
    num_distinct,
    num_nulls,
    histogram,
    num_buckets,
    last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS';
~~~

Các view USER_ chỉ hiển thị object thuộc schema hiện tại; có thể dùng ALL_/DBA_ views theo quyền và phạm vi.

### 13.2. Thu thập statistics

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => USER,
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => TRUE
  );
END;
/
~~~

SIZE AUTO cho phép Oracle quyết định histogram dựa trên workload và phân bố theo cơ chế của phiên bản. Có thể cần chỉ định histogram cho cột cụ thể sau khi phân tích. Thu thập statistics có thể làm thay đổi plan, nên dùng quy trình kiểm soát và cân nhắc pending statistics hoặc cơ chế plan management nếu môi trường yêu cầu.

### 13.3. Column group statistics

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'ORDERS',
    extension => '(TENANT_ID, STATUS)'
)
FROM dual;
~~~

Sau khi tạo extension, thu thập lại statistics. Kiểm tra plan và cardinality estimate để xác nhận optimizer sử dụng thông tin nhóm cột.

### 13.4. Bind peeking và adaptive cursor sharing

Oracle có thể xem giá trị bind khi hard parse và dùng histogram để ước lượng. Adaptive Cursor Sharing có thể tạo hoặc chọn child cursor khác nhau cho các nhóm bind value trong những điều kiện phù hợp.

Khi điều tra, xem SQL_ID, child cursor, plan hash, bind sensitivity/awareness và runtime statistics. Không giả định mọi bind value đều dùng cùng một child cursor hoặc một plan.

## 14. Statistics theo partition và bảng lớn

Bảng partitioned có thể có statistics ở cấp partition và cấp global. Nếu chỉ cập nhật partition mới nhưng global statistics không phù hợp, optimizer có thể ước lượng sai khi truy vấn nhiều partition hoặc dùng predicate toàn bảng.

Cần xem:

- Partition mới có được analyze chưa?
- Global stats có được cập nhật hoặc incremental maintenance đúng không?
- Query có partition pruning như mong đợi không?
- Dữ liệu có skew giữa các partition không?
- Partition mới có phân bố khác lịch sử không?
- Statistics có được merge đúng theo cơ chế DBMS không?

Với bảng tăng theo thời gian, partition mới có thể chứa trạng thái PENDING nhiều hơn dữ liệu cũ. Global histogram trên toàn bảng có thể làm mờ phân bố cục bộ của partition mới. Hãy kiểm tra cả plan chỉ truy cập partition mới và plan quét nhiều partition.

## 15. Sampling và mức độ chi tiết của statistics

Statistics sampling giúp giảm chi phí thu thập trên bảng lớn nhưng có thể bỏ lỡ giá trị hiếm hoặc đánh giá sai heavy hitters.

Các yếu tố:

- Tỷ lệ sample.
- Kích thước bảng.
- Độ lệch của phân phối.
- Mức độ tập trung của key nóng.
- Số bucket/histogram target.
- Tần suất thay đổi dữ liệu.
- Thời gian và tài nguyên được phép dùng cho analyze.

Tăng sample hoặc bucket có thể cải thiện estimate nhưng không phải lúc nào cũng cần. Hãy thay đổi có mục tiêu cho cột liên quan và đo:

- Thời gian thu thập statistics.
- Dung lượng statistics.
- Estimated/actual rows.
- Plan thay đổi.
- Query latency và workload tổng thể.

Nếu phân bố thay đổi liên tục, một lần full scan statistics có thể nhanh chóng lỗi thời. Khi đó cần điều chỉnh lịch cập nhật, incremental stats hoặc thiết kế workload phù hợp.

## 16. Query rewrite khi statistics không thể mô tả đủ

Không phải mọi sai số đều giải quyết được bằng statistics. Query rewrite có thể giúp optimizer có predicate rõ hơn hoặc giảm tập dữ liệu trước khi JOIN.

Ví dụ, tránh bọc cột bằng hàm nếu làm mất khả năng dùng index/statistics:

~~~sql
-- Có thể gây khó khăn cho index và ước lượng tùy DBMS
WHERE DATE(created_at) = DATE '2026-11-19'

-- Dạng range thường rõ hơn
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00'
~~~

Kiểu timestamp và timezone cần phù hợp với schema. Range predicate cũng giúp optimizer suy ra khoảng dữ liệu rõ ràng hơn.

Các hướng khác:

- Loại bỏ implicit conversion trên cột join/filter.
- Dùng kiểu bind đúng với kiểu cột.
- Tách truy vấn cho nhóm selectivity khác nhau nếu cần.
- Đẩy filter sớm khi semantics cho phép.
- Giảm JOIN không cần thiết và kiểm tra duplicate multiplication.
- Dùng temporary/staging result khi nó giúp kiểm soát cardinality và được đo chứng minh.

Không rewrite chỉ để làm estimated rows trông đẹp. Kết quả nghiệp vụ phải tương đương và plan phải cải thiện trong workload đại diện.

## 17. Index không thay thế statistics

Index cung cấp đường truy cập dữ liệu và có thể mang thông tin phân bố riêng, nhưng tạo index không tự giải quyết mọi cardinality misestimation.

Trước khi thêm index:

- Xác định predicate và join key.
- Kiểm tra index hiện có và thứ tự cột.
- Xem selectivity của từng giá trị.
- Xem query có trả về tỷ lệ lớn của bảng không.
- Đo chi phí ghi và dung lượng index.
- Kiểm tra statistics của index/cột liên quan.

Với cột skew mạnh, một index có thể tốt cho giá trị hiếm nhưng kém cho giá trị nóng. Nếu optimizer không nhận diện được selectivity khác nhau, cần xử lý statistics hoặc parameter sensitivity.

Filtered/partial index có thể hữu ích cho một tập con nhỏ như PENDING, nhưng query predicate phải tương thích với điều kiện index và DBMS phải có thể chứng minh việc sử dụng là đúng.

## 18. Capstone: truy vấn orders chậm sau một đợt nạp dữ liệu

### 18.1. Bối cảnh

Một hệ thống thương mại có bảng orders gồm 80 triệu hàng. Sau một chiến dịch, một tenant mới tạo lượng đơn rất lớn và tỷ lệ PENDING tăng nhanh. API tra cứu đơn hàng theo tenant và status bắt đầu chậm.

SQL:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Triệu chứng:

- p95 tăng từ 90 ms lên 1,4 giây.
- CPU database tăng nhưng chưa bão hòa toàn bộ.
- Một số tenant nhỏ vẫn nhanh.
- Tenant mới và status PENDING chậm rõ rệt.
- Actual plan cho thấy Nested Loop/Index access thực hiện nhiều lần.

### 18.2. Bước 1: xác định plan và estimate

Plan minh họa:

| Operator | Estimated rows | Actual rows |
|---|---:|---:|
| Index Scan orders_tenant_status | 120 | 480.000 |
| Sort/Top-N input | 120 | 480.000 |

Q-error ở bước scan xấp xỉ 4.000. Sai số rất lớn và có thể khiến optimizer chọn đường truy cập không phù hợp.

### 18.3. Bước 2: kiểm tra dữ liệu

Thống kê tổng hợp cho thấy:

- Tenant mới chiếm 28% tổng số orders.
- PENDING chỉ chiếm 4% toàn bảng.
- Trong tenant mới, PENDING chiếm 45%.
- Các tenant cũ có tỷ lệ PENDING thấp hơn nhiều.

Hai cột tenant_id và status có tương quan. Statistics riêng lẻ có thể mô tả tenant và status nhưng không đủ mô tả tổ hợp của tenant lớn với PENDING.

### 18.4. Bước 3: kiểm tra freshness

Đợt nạp dữ liệu đã thêm hàng triệu orders sau lần analyze gần nhất. Statistics đang cũ so với trạng thái mới. Đây là một nguyên nhân, nhưng chưa giải thích hết tương quan tenant/status.

### 18.5. Bước 4: chọn thay đổi

Thực hiện trong môi trường kiểm thử trước:

1. Cập nhật statistics của bảng và các cột liên quan.
2. Kiểm tra histogram/MCV cho tenant_id và status.
3. Bổ sung multicolumn/extended statistics nếu DBMS hỗ trợ và query shape có thể sử dụng.
4. Xem lại index theo (tenant_id, status, created_at) hoặc phương án khác dựa trên truy vấn thực tế.
5. Kiểm tra parameter sensitivity với tenant nhỏ và tenant lớn.

Không mặc định index trên là đúng. Nếu status có skew và query luôn sắp xếp theo created_at, thứ tự index và khả năng covering phải được đánh giá qua plan và workload ghi.

### 18.6. Bước 5: xác minh

Chạy lại với:

- Tenant mới và PENDING.
- Tenant mới và COMPLETED.
- Tenant nhỏ và PENDING.
- Tenant nhỏ và COMPLETED.
- Giá trị tenant mới chưa từng được dùng ở lần compile trước nếu có plan cache.

So sánh estimated/actual rows, plan, logical reads, CPU, elapsed time và p95/p99. Chạy thêm workload ghi để xem index và statistics maintenance có làm tăng chi phí DML đáng kể không.

### 18.7. Kết quả mong đợi

- Estimate gần actual hơn ở operator đầu tiên.
- Plan phù hợp với nhóm tenant nóng và hiếm.
- Logical reads và CPU giảm cho truy vấn mục tiêu.
- p95/p99 cải thiện.
- Không làm query tenant nhỏ hoặc workload ghi regression đáng kể.
- Statistics được cập nhật theo lịch hoặc theo sự kiện nạp dữ liệu.

Các số liệu kết quả phải được đo thực tế; không suy ra thành công chỉ vì plan thay đổi hoặc estimated rows gần actual hơn.

## 19. Benchmark trước và sau thay đổi

Một quy trình benchmark đáng tin cậy:

1. Lưu SQL, parameter set và query fingerprint.
2. Lưu execution plan và statistics state trước thay đổi.
3. Chạy các giá trị phổ biến, hiếm và biên.
4. Đo warm-cache và điều kiện cache khác nếu mục tiêu cần.
5. Ghi CPU, elapsed, logical/physical reads, memory, spill và wait.
6. Thay đổi một yếu tố: stats, histogram, extended stats, query hoặc index.
7. Thu thập lại plan và số đo dưới cùng điều kiện.
8. Chạy workload đồng thời và truy vấn liên quan.
9. Kiểm tra kết quả dữ liệu và semantics.
10. Lưu lại plan, cấu hình, timestamp và kết luận.

### 19.1. Chỉ số cần so sánh

| Chỉ số | Vì sao cần |
|---|---|
| Estimated/actual rows | Xác nhận chất lượng cardinality estimate |
| Q-error ở operator quan trọng | Định lượng sai lệch |
| Logical reads | Đo lượng page được xử lý |
| Physical reads | Đánh giá I/O từ storage |
| CPU time | Đo công việc xử lý |
| Elapsed time | Đo thời gian người dùng chờ |
| Memory grant/spill | Phát hiện thiếu hoặc lãng phí bộ nhớ |
| Lock/wait | Phát hiện contention |
| Throughput và p95/p99 | Đánh giá toàn workload |
| DML latency/log bytes | Đánh giá chi phí phụ do index/statistics |

### 19.2. Không chỉ kiểm tra một tham số

Một thay đổi có thể cải thiện tenant lớn nhưng làm tenant nhỏ chậm hơn. Hãy dùng parameter matrix đại diện và cân nhắc tỷ trọng request của từng nhóm khi đánh giá tổng thể.

## 20. Quản lý plan regression sau khi cập nhật statistics

Statistics mới có thể làm optimizer chọn plan mới. Điều này thường là mục tiêu, nhưng không phải mọi plan change đều tốt.

Sau cập nhật:

- Theo dõi query có plan hash thay đổi.
- So sánh runtime statistics trước/sau.
- Xem query nào tăng latency hoặc reads.
- Kiểm tra plan forcing/baseline hiện có.
- Xác định plan regression có liên quan statistics change hay dữ liệu/workload khác.

Nếu plan mới gây regression:

1. Xác minh regression có thể tái lập.
2. Xác định query và parameter values bị ảnh hưởng.
3. Xem plan cũ có còn phù hợp với phân bố hiện tại không.
4. Dùng cơ chế plan management có kiểm soát nếu cần rollback tạm.
5. Tìm giải pháp bền vững ở statistics, query, index hoặc workload separation.

Không giữ plan cũ vĩnh viễn chỉ vì nó từng nhanh. Khi dữ liệu tiếp tục tăng, plan cũ có thể trở nên không phù hợp.

## 21. An toàn khi cập nhật statistics trên production

Statistics update thường ít rủi ro hơn thay đổi schema nhưng vẫn có thể ảnh hưởng lớn:

- Tốn CPU và I/O khi scan/sample bảng.
- Có thể cạnh tranh với workload OLTP.
- Có thể thay đổi execution plan của nhiều query.
- Có thể tạo plan regression ngay sau cập nhật.
- Một số thao tác có lock hoặc yêu cầu tài nguyên tùy DBMS.
- Statistics partition/global có thể cập nhật theo cách khác nhau.

Quy trình an toàn:

1. Xác định chính xác bảng/cột/statistics cần cập nhật.
2. Kiểm tra dung lượng, workload và cửa sổ bảo trì.
3. Lưu plan và runtime baseline của query quan trọng.
4. Thử trên staging hoặc bản sao dữ liệu đại diện.
5. Chọn sampling/target phù hợp.
6. Cập nhật theo phạm vi nhỏ.
7. Theo dõi query plan và latency sau cập nhật.
8. Dùng plan management hoặc rollback strategy nếu có regression.

Không xóa statistics cũ hoặc reset toàn bộ plan cache như biện pháp đầu tiên. Những hành động đó có thể làm compile storm hoặc gây thêm tải.

## 22. Khi nào cần xem xét thiết kế dữ liệu?

Nếu skew là đặc tính ổn định và tạo ra chênh lệch workload rất lớn, chỉ tăng histogram có thể chưa đủ.

Các lựa chọn kiến trúc:

- Tách tenant lớn sang partition hoặc database riêng khi có lý do vận hành.
- Partition theo tenant/time nếu query pattern và data lifecycle phù hợp.
- Dùng partial/filtered index cho subset có giá trị nghiệp vụ rõ.
- Dùng summary/materialized view cho truy vấn đọc lặp lại.
- Tách workload phân tích khỏi OLTP.
- Thiết kế API/query riêng cho tenant lớn và tenant thông thường.

Mỗi lựa chọn tạo thêm chi phí vận hành, ghi, lưu trữ và tính nhất quán. Không partition hoặc shard chỉ vì một estimate sai; trước tiên xác nhận đây là giới hạn lâu dài của workload và có lợi ích đủ lớn.

## 23. Những sai lầm thường gặp

- **Chỉ nhìn plan cuối cùng.** Operator đầu tiên sai estimate mới thường chỉ ra nguồn gốc.
- **Coi mọi table scan là xấu.** Scan có thể đúng khi predicate trả về phần lớn bảng.
- **Chạy ANALYZE mà không kiểm tra lại.** Statistics mới không bảo đảm giải quyết skew hoặc correlation.
- **Nhầm NDV với phân bố.** Cùng NDV có thể có histogram rất khác.
- **Bỏ qua heavy hitters.** Uniform data không đại diện tenant hoặc key nóng.
- **Giả định các cột độc lập.** Correlation làm estimate của predicate kết hợp sai.
- **Tăng statistics target cho mọi cột.** Tăng chi phí analyze và planning mà không có lợi ích rõ.
- **Tạo extended statistics nhưng không xác minh plan.** Optimizer có thể không dùng loại stats đó cho query shape hiện tại.
- **Dùng FULLSCAN hoặc histogram tối đa cho mọi bảng.** Chi phí thu thập có thể lớn hơn lợi ích.
- **Ép plan trước khi hiểu dữ liệu.** Plan hint có thể che giấu nguyên nhân và gây regression sau này.
- **Chỉ test một bind value.** Parameter-sensitive query cần kiểm tra nhiều nhóm selectivity.
- **Bỏ qua partition/global stats.** Dữ liệu mới ở partition riêng có thể làm estimate sai.
- **Xóa plan cache để chữa chậm.** Có thể tạo compile storm và thay đổi hành vi hàng loạt.
- **Không benchmark workload ghi.** Index hoặc statistics maintenance có thể làm tăng DML cost.
- **Không lưu baseline và plan cũ.** Khó chứng minh cải thiện hoặc khôi phục khi regression.

## 24. Checklist capstone

- [ ] Đã chọn query fingerprint và cửa sổ sự cố rõ ràng.
- [ ] Đã lưu actual execution plan và parameter values đại diện.
- [ ] Đã so estimated rows với actual rows ở từng operator quan trọng.
- [ ] Đã tính hoặc ghi nhận Q-error và số lần operator được thực thi.
- [ ] Đã xác định operator đầu tiên có sai lệch đáng kể.
- [ ] Đã đo row count, NDV, NULL rate, histogram và heavy hitters.
- [ ] Đã kiểm tra statistics freshness, modification count và auto-update.
- [ ] Đã phân biệt stale stats, skew, correlation và parameter sensitivity.
- [ ] Đã kiểm tra partition/global statistics nếu bảng partitioned.
- [ ] Đã chọn thay đổi có phạm vi nhỏ: analyze, histogram, extended stats, query/index hoặc plan management.
- [ ] Đã kiểm tra chi phí thu thập statistics và tác động production.
- [ ] Đã chạy lại với giá trị phổ biến, hiếm và biên.
- [ ] Đã so logical/physical reads, CPU, elapsed, memory grant, spill và wait.
- [ ] Đã benchmark dưới concurrency đại diện và kiểm tra query liên quan.
- [ ] Đã xác minh kết quả nghiệp vụ không đổi.
- [ ] Đã theo dõi plan regression sau cập nhật.
- [ ] Đã lưu plan, statistics state, parameter matrix và kết quả trước/sau.
- [ ] Đã có lịch hoặc trigger cập nhật statistics phù hợp với tốc độ thay đổi dữ liệu.

Ước lượng sai do dữ liệu lệch hoặc thống kê lỗi thời cần được xử lý bằng bằng chứng ở cấp operator. Hãy so sánh estimated rows với actual rows, tìm điểm sai lệch đầu tiên, rồi phân biệt dữ liệu đã thay đổi, heavy hitters, tương quan giữa cột hay parameter sensitivity. Cập nhật statistics, histogram hoặc extended statistics chỉ khi chúng giải quyết đúng nguyên nhân và được DBMS hỗ trợ cho query shape đó. Cuối cùng, benchmark nhiều giá trị tham số và workload đồng thời, theo dõi plan regression, chi phí ghi và tính đúng đắn. Mục tiêu là giúp optimizer chọn plan phù hợp với phân bố dữ liệu hiện tại và giữ hiệu năng ổn định khi dữ liệu tiếp tục thay đổi.
