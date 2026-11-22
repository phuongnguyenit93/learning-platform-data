# Materialized view, bảng tổng hợp và chi phí làm mới

Truy vấn phân tích thường phải quét nhiều hàng, nối nhiều bảng và tính toán các chỉ số tổng hợp như doanh thu theo ngày, số đơn theo khu vực hoặc số người dùng hoạt động theo tháng. Nếu cùng một phép tính được chạy liên tục, hệ quản trị phải lặp lại công việc đọc, join, group và sort trên dữ liệu nguồn. Materialized view hoặc bảng tổng hợp lưu sẵn kết quả đã tính để truy vấn sau có thể đọc một tập dữ liệu nhỏ hơn.

Lưu kết quả trước giúp giảm thời gian đọc, nhưng chuyển một phần chi phí sang quá trình làm mới. Hệ thống phải tính lại hoặc cập nhật phần dữ liệu thay đổi, ghi kết quả, duy trì chỉ mục, sinh log, truyền thay đổi sang replica và quản lý độ trễ dữ liệu. Một bản tổng hợp chỉ có ích khi chi phí làm mới và lưu trữ thấp hơn lợi ích đọc mà nó mang lại, đồng thời độ mới của dữ liệu đáp ứng yêu cầu nghiệp vụ.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần xem materialized view, bảng tổng hợp và incremental maintenance như các lựa chọn khác nhau. Bài học này trình bày cách chọn grain và chiều tổng hợp, các kiểu refresh, chi phí refresh, điều kiện cập nhật tăng dần, độ nhất quán, cách triển khai trên PostgreSQL, Oracle, SQL Server và MySQL, cùng quy trình đo kiểm trước khi đưa vào workload phân tích.

## 1. View, materialized view và bảng tổng hợp

### 1.1. View thông thường

View lưu định nghĩa truy vấn, không nhất thiết lưu kết quả. Khi ứng dụng truy vấn view, hệ quản trị thường mở rộng định nghĩa view vào truy vấn và thực thi trên bảng nguồn.

Ví dụ:

~~~sql
CREATE VIEW daily_sales AS
SELECT
    CAST(created_at AS DATE) AS sales_date,
    region_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY CAST(created_at AS DATE), region_id;
~~~

Truy vấn view vẫn có thể phải đọc và tổng hợp toàn bộ các hàng phù hợp trong orders. View giúp tái sử dụng logic và quản lý quyền, nhưng tự nó không loại bỏ chi phí tính toán.

### 1.2. Materialized view

Materialized view lưu kết quả truy vấn dưới dạng dữ liệu vật lý do DBMS quản lý. Khi truy vấn đọc materialized view, hệ quản trị có thể đọc các hàng đã được tính trước. Dữ liệu chỉ phản ánh trạng thái nguồn tại lần refresh hoặc lần cập nhật gần nhất.

Ví dụ khái niệm:

~~~sql
CREATE MATERIALIZED VIEW daily_sales AS
SELECT
    CAST(created_at AS DATE) AS sales_date,
    region_id,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY CAST(created_at AS DATE), region_id;
~~~

Cú pháp và khả năng của materialized view phụ thuộc hệ quản trị. Ví dụ này minh họa ý tưởng, không phải DDL dùng chung cho mọi DBMS.

### 1.3. Bảng tổng hợp (summary table)

Bảng tổng hợp là bảng vật lý do ứng dụng, job ETL hoặc pipeline dữ liệu quản lý. Nó lưu các số liệu đã gom nhóm theo grain đã chọn. Hệ thống có thể làm mới toàn bộ, cập nhật theo batch hoặc cộng dồn từng sự kiện.

Ví dụ:

~~~sql
CREATE TABLE sales_daily_summary (
    sales_date DATE NOT NULL,
    region_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(20, 2) NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (sales_date, region_id)
);
~~~

Ứng dụng có thể cập nhật bảng này theo lịch hoặc từ luồng sự kiện. Bảng tổng hợp cho phép kiểm soát logic và chiến lược refresh chi tiết hơn, nhưng đội phát triển phải tự đảm bảo tính đúng đắn, idempotency, checkpoint và xử lý dữ liệu đến muộn.

## 2. Khi nào nên lưu sẵn kết quả?

Materialized view hoặc summary table phù hợp khi:

- Cùng một phép tổng hợp đắt tiền được truy vấn nhiều lần.
- Dữ liệu nguồn lớn nhưng kết quả tổng hợp nhỏ hơn đáng kể.
- Người dùng chấp nhận độ trễ dữ liệu có giới hạn.
- Query pattern tương đối ổn định và có grain tổng hợp rõ.
- Có thể làm mới theo lịch hoặc theo sự kiện với chi phí chấp nhận được.
- Báo cáo cần thời gian phản hồi ổn định hơn truy vấn trực tiếp trên dữ liệu chi tiết.

Ví dụ, dashboard doanh thu theo ngày/khu vực được nhiều người mở liên tục. Thay vì mỗi request quét hàng trăm triệu orders, hệ thống đọc vài nghìn dòng summary đã tính trước.

Không nên tạo materialized view chỉ vì một truy vấn chậm. Trước hết hãy kiểm tra execution plan, index, predicate, join cardinality, partition pruning và thống kê. Nếu truy vấn chỉ chạy một lần mỗi ngày, refresh tốn nhiều phút có thể không đáng so với việc chạy truy vấn gốc.

### 2.1. So sánh lợi ích đọc và chi phí làm mới

| Yếu tố | Truy vấn trực tiếp | Materialized view / summary |
|---|---|---|
| Độ mới dữ liệu | Có thể đọc trạng thái hiện tại theo isolation | Phụ thuộc thời điểm refresh hoặc cập nhật |
| Chi phí đọc | Tính toán lại từ dữ liệu nguồn | Đọc kết quả đã tính |
| Chi phí ghi | Chủ yếu duy trì bảng nguồn và index | Thêm refresh/update và index summary |
| Dung lượng | Chủ yếu dữ liệu chi tiết | Thêm dữ liệu tổng hợp và index |
| Độ phức tạp | Ít thành phần vận hành hơn | Cần lịch refresh, kiểm tra freshness và recovery |
| Tính linh hoạt | Dễ thay đổi filter/grouping | Chỉ phục vụ grain và logic đã lưu |

Quyết định phải dựa trên workload tổng thể. Một materialized view có thể giảm CPU đọc nhưng tăng I/O ghi, WAL/redo, replication traffic và cạnh tranh tài nguyên trong giờ refresh.

## 3. Chọn grain và dimensions cho bảng tổng hợp

Grain là mức chi tiết mà mỗi hàng tổng hợp đại diện. Ví dụ, một hàng có thể đại diện cho một ngày và một khu vực, hoặc một giờ, khu vực và loại sản phẩm.

Ví dụ grain ngày-khu vực:

~~~text
Một hàng = một sales_date + một region_id
Measures = order_count, revenue, refunded_amount
~~~

Grain phải đủ chi tiết để trả lời các câu hỏi cần thiết, nhưng không quá chi tiết đến mức bảng tổng hợp gần bằng bảng nguồn.

### 3.1. Dimensions

Dimensions là các chiều dùng để nhóm hoặc lọc dữ liệu, chẳng hạn:

- Thời gian: ngày, tuần, tháng, giờ.
- Khu vực: quốc gia, tỉnh, vùng kinh doanh.
- Sản phẩm: product, category, brand.
- Khách hàng: segment, tenant, cohort.
- Kênh: web, mobile, partner.

Mỗi dimension bổ sung có thể làm số nhóm tăng mạnh. Nếu có 365 ngày, 100 khu vực và 50 loại sản phẩm, số tổ hợp tối đa về lý thuyết là 1.825.000 nhóm, dù nhiều tổ hợp có thể không xuất hiện.

Không thêm dimension chỉ vì “có thể cần sau này”. Hãy dựa trên truy vấn thực tế và ước lượng cardinality của tổ hợp.

### 3.2. Measures

Measures là các số liệu được lưu, ví dụ:

- COUNT(*) hoặc số đơn.
- SUM(amount) hoặc tổng doanh thu.
- SUM(quantity).
- Số hàng bị hủy.
- Số khách hàng duy nhất.
- Giá trị min/max.

Một số measure có thể kết hợp từ summary khác. Ví dụ, AVG nên được lưu dưới dạng SUM và COUNT để có thể tính lại trung bình đúng khi gộp nhiều nhóm:

\[
AVG=\frac{SUM(value)}{COUNT(value)}
\]

Không lấy trung bình các giá trị trung bình của từng partition nếu số lượng hàng mỗi partition khác nhau. Phải cộng tổng và số lượng rồi chia.

### 3.3. Grain và tính đúng đắn

Nếu một order có nhiều order_items, join orders với order_items trước khi SUM(order.total_amount) có thể nhân bản giá trị order theo số dòng hàng. Bảng tổng hợp phải xác định rõ đơn vị đếm và quan hệ join để tránh double counting.

Ví dụ, đếm đơn hàng theo khu vực nên dùng một hàng cho mỗi order ở cấp đơn hàng hoặc dùng COUNT(DISTINCT order_id) khi phù hợp. Nhưng COUNT DISTINCT có chi phí và khó cập nhật tăng dần hơn COUNT đơn giản. Cần thiết kế grain trước khi chọn cách tính.

## 4. Các loại refresh

### 4.1. Complete refresh

Complete refresh tính lại toàn bộ truy vấn nguồn và thay thế nội dung materialized view hoặc summary. Cách này dễ hiểu và thường dễ xác minh tính đúng đắn.

Ưu điểm:

- Logic refresh đơn giản.
- Tự phản ánh insert, update và delete trong dữ liệu nguồn tại snapshot được đọc.
- Ít phải lưu trạng thái trung gian để áp dụng delta.
- Dễ xây dựng đối chiếu với truy vấn gốc.

Nhược điểm:

- Phải đọc và tính lại phạm vi dữ liệu lớn dù chỉ một phần nhỏ thay đổi.
- Có thể tiêu thụ nhiều CPU, memory và I/O.
- Sort/hash có thể spill ra storage tạm.
- Ghi lại toàn bộ kết quả có thể tạo nhiều log và replication traffic.
- Refresh lâu có thể làm dữ liệu cũ trong thời gian dài hoặc ảnh hưởng truy vấn đọc tùy cơ chế thay thế.

Complete refresh phù hợp khi dữ liệu vừa phải, refresh ít thường xuyên hoặc chi phí tính lại vẫn nằm trong cửa sổ vận hành.

### 4.2. Incremental refresh

Incremental refresh chỉ xử lý phần dữ liệu mới hoặc thay đổi kể từ lần cập nhật trước. Thay vì tính lại toàn bộ summary, pipeline xác định delta và áp dụng vào kết quả hiện tại.

Ví dụ, nếu có 10.000 orders mới trong ngày, summary theo ngày-khu vực có thể cộng thêm order_count và revenue của 10.000 hàng đó.

Ưu điểm:

- Giảm lượng dữ liệu phải đọc và tính lại.
- Có thể làm mới thường xuyên hơn.
- Giảm thời gian refresh khi delta nhỏ so với toàn bộ dữ liệu.

Nhược điểm:

- Cần phát hiện đầy đủ insert, update và delete.
- Phải xử lý sự kiện trùng, đến muộn và sai thứ tự.
- Cập nhật số liệu như MIN/MAX, DISTINCT và percentile phức tạp hơn.
- Cần checkpoint, retry và đối soát để tránh mất hoặc cộng trùng delta.
- Logic vận hành và kiểm thử phức tạp hơn complete refresh.

### 4.3. Refresh theo cửa sổ thời gian

Một chiến lược thực tế là chỉ tính lại một cửa sổ gần đây, ví dụ 3 ngày hoặc 2 tuần, trong khi giữ nguyên các partition tổng hợp cũ đã ổn định.

Chiến lược này phù hợp khi:

- Dữ liệu mới có thể đến muộn trong một khoảng thời gian hữu hạn.
- Các ngày cũ hiếm khi bị sửa.
- Có thể xác định một watermark sau đó dữ liệu được xem là ổn định.

Nếu dữ liệu lịch sử có thể được điều chỉnh bất kỳ lúc nào, refresh cửa sổ gần đây sẽ bỏ sót các sửa đổi cũ. Cần có cơ chế correction/rebuild cho các kỳ bị ảnh hưởng.

## 5. Incremental maintenance cho từng loại aggregate

Không phải aggregate nào cũng có thể cập nhật bằng cách cộng thêm một delta đơn giản.

| Aggregate | Cập nhật tăng dần khi có insert | Khó khăn khi có update/delete |
|---|---|---|
| COUNT(*) | Cộng số hàng mới | Phải trừ số hàng bị xóa hoặc chuyển nhóm |
| SUM(x) | Cộng tổng x mới | Phải trừ giá trị cũ và cộng giá trị mới |
| AVG(x) | Lưu SUM và COUNT rồi tính lại | Cần điều chỉnh cả tổng và số lượng |
| MIN(x), MAX(x) | Giá trị mới có thể cập nhật cực trị | Xóa giá trị cực trị cần tìm lại giá trị kế tiếp |
| COUNT(DISTINCT x) | Có thể cần cấu trúc tập hợp hoặc thuật toán đặc biệt | Xóa một giá trị phải biết còn hàng nào khác dùng giá trị đó không |
| Median/percentile | Cần cấu trúc thống kê phức tạp | Thường không thể cập nhật chính xác chỉ bằng một số tổng đơn giản |

### 5.1. SUM và COUNT

Giả sử summary lưu:

- order_count.
- revenue_sum.

Khi thêm batch mới:

~~~sql
INSERT INTO sales_daily_summary (
    sales_date, region_id, order_count, revenue
)
SELECT
    CAST(created_at AS DATE),
    region_id,
    COUNT(*),
    SUM(total_amount)
FROM orders_delta
GROUP BY CAST(created_at AS DATE), region_id;
~~~

Kết quả delta cần được cộng vào summary hiện có. Cú pháp UPSERT khác nhau theo DBMS; phải xử lý xung đột khóa theo đúng quy tắc.

### 5.2. Update cần trừ giá trị cũ và cộng giá trị mới

Nếu order đổi region hoặc amount, summary cũ phải giảm ở nhóm cũ và tăng ở nhóm mới. Chỉ xử lý trạng thái mới sẽ để lại số liệu sai trong nhóm cũ.

Một CDC feed có before-image và after-image giúp xác định:

- Nhóm cũ và measure cũ cần trừ.
- Nhóm mới và measure mới cần cộng.

Nếu nguồn chỉ cung cấp trạng thái hiện tại, có thể cần audit/change table hoặc tính lại nhóm bị ảnh hưởng.

### 5.3. MIN/MAX và DISTINCT

Nếu hàng đang giữ giá trị MIN bị xóa, không thể biết giá trị MIN mới chỉ bằng cách trừ giá trị cũ khỏi summary. Phải truy vấn lại nhóm hoặc duy trì cấu trúc phụ để tìm cực trị kế tiếp.

COUNT(DISTINCT customer_id) cũng không thể luôn cập nhật bằng cách cộng số khách hàng mới trong batch. Một khách hàng có thể đã xuất hiện ở batch trước. Có thể cần bảng membership theo khóa, sketch xác suất nếu nghiệp vụ chấp nhận xấp xỉ, hoặc refresh lại nhóm.

Hãy chọn aggregate theo nhu cầu chính xác của báo cáo. Đừng thiết kế incremental pipeline dựa trên giả định mọi aggregate đều có thể cộng/trừ đơn giản.

## 6. Chi phí của một lần refresh

Refresh có thể bao gồm nhiều giai đoạn:

1. Đọc dữ liệu nguồn hoặc delta.
2. Thực hiện filter, join và aggregate.
3. Sort, hash hoặc materialize tập kết quả trung gian.
4. Ghi dữ liệu mới vào materialized view/summary.
5. Duy trì index trên kết quả.
6. Commit và sinh WAL/redo/transaction log.
7. Truyền log sang replica và áp dụng thay đổi.
8. Cập nhật thống kê hoặc metadata nếu cần.

Chi phí refresh không chỉ là thời gian chạy SELECT nguồn. Với summary có nhiều index, phần ghi và duy trì index có thể chiếm đáng kể thời gian.

### 6.1. CPU

Join, group by, sort, distinct và expression có thể tiêu thụ CPU lớn. Nếu refresh chạy đồng thời với workload OLTP, nó có thể làm tăng CPU queue và p95/p99 của truy vấn tương tác.

### 6.2. Memory

Hash aggregate, hash join và sort cần memory. Nếu grant không đủ, operator có thể spill ra đĩa. Refresh song song có thể dùng nhiều memory hơn vì nhiều worker hoặc operator hoạt động đồng thời.

### 6.3. I/O và log

Refresh toàn bộ có thể đọc lượng lớn dữ liệu nguồn và ghi lại kết quả. Duy trì index trên summary tạo thêm page write. Log generation tăng có thể ảnh hưởng checkpoint, log backup, replication lag và dung lượng WAL/redo.

### 6.4. Lock và concurrency

Refresh có thể khóa hoặc cạnh tranh với truy vấn đọc/ghi tùy DBMS và phương thức refresh. Một số phương thức cho phép truy vấn đọc tiếp tục nhưng có chi phí cao hơn hoặc yêu cầu index đặc biệt. Cần kiểm tra semantics của sản phẩm đang dùng.

## 7. Định lượng lợi ích của materialized view

Một cách đánh giá là so sánh tổng chi phí đọc tiết kiệm được với chi phí refresh và vận hành trong cùng khoảng thời gian.

Gọi:

- \(Q\): số lần truy vấn đọc trong một chu kỳ.
- \(C_{base}\): chi phí trung bình của truy vấn gốc.
- \(C_{mv}\): chi phí đọc materialized view.
- \(C_{refresh}\): chi phí làm mới trong chu kỳ.
- \(C_{ops}\): chi phí vận hành bổ sung quy đổi trong cùng chu kỳ.

Lợi ích ròng gần đúng:

\[
Benefit=Q(C_{base}-C_{mv})-C_{refresh}-C_{ops}
\]

Đây là mô hình so sánh khái quát. Chi phí có thể đo bằng CPU-seconds, I/O bytes, storage cost hoặc tài nguyên quy đổi; không nên cộng trực tiếp các đơn vị khác nhau nếu chưa chuẩn hóa.

Ví dụ:

- Truy vấn gốc tiêu thụ 4 giây CPU và 2 GB đọc.
- Truy vấn summary tiêu thụ 0,1 giây CPU và 20 MB đọc.
- Có 500 lượt đọc mỗi giờ.
- Refresh mỗi giờ tiêu thụ 80 giây CPU và 30 GB I/O.

Phần CPU đọc tiết kiệm xấp xỉ 500 × (4 − 0,1) = 1.950 giây mỗi giờ, lớn hơn 80 giây CPU refresh. Tuy nhiên, cần tính thêm I/O, log, replica lag, storage, concurrency và ảnh hưởng của refresh lên workload khác. Một phương án có lợi về CPU vẫn có thể không phù hợp nếu refresh tạo write burst hoặc dữ liệu quá cũ.

### 7.1. Tần suất refresh là một trade-off

Refresh thường xuyên:

- Dữ liệu mới hơn.
- Delta mỗi lần có thể nhỏ hơn.
- Tăng số lần chạy job, commit, log và overhead điều phối.

Refresh thưa:

- Giảm số lần chạy.
- Có thể tạo batch lớn và write burst.
- Dữ liệu cũ hơn.
- Khi job lỗi, khoảng thời gian stale có thể kéo dài.

Tần suất nên được quyết định từ freshness SLO, tốc độ thay đổi nguồn, thời gian refresh và năng lực tài nguyên.

## 8. Độ mới và tính nhất quán của dữ liệu tổng hợp

Materialized view không nhất thiết phản ánh dữ liệu mới nhất. Cần xác định rõ:

- Refresh hoàn tất lúc nào?
- Dữ liệu nguồn được đọc tại snapshot nào?
- Các transaction đang ghi có được bao gồm không?
- Khi refresh thất bại, ứng dụng đọc bản cũ hay không có dữ liệu?
- Có cho phép một báo cáo đọc các summary được refresh ở thời điểm khác nhau không?

### 8.1. Freshness SLA

Freshness có thể được định nghĩa là độ trễ giữa thời điểm dữ liệu nguồn được commit và thời điểm số liệu tổng hợp phản ánh thay đổi đó.

Ví dụ:

- Dashboard vận hành: dữ liệu trễ tối đa 1 phút.
- Báo cáo quản trị: dữ liệu trễ tối đa 1 giờ.
- Báo cáo tài chính đã đóng kỳ: dữ liệu chỉ cập nhật sau bước đối soát và phê duyệt.

Không dùng một tần suất refresh chung cho mọi sản phẩm dữ liệu nếu yêu cầu freshness khác nhau.

### 8.2. Ghi nhận watermark

Summary nên lưu metadata cho biết dữ liệu được tính đến thời điểm hoặc vị trí nguồn nào:

- last_successful_refresh_at.
- source_watermark hoặc CDC position.
- refresh_run_id.
- row_count hoặc checksum phục vụ đối soát.
- trạng thái refresh và lỗi gần nhất.

Watermark giúp ứng dụng và vận hành biết summary có đang stale hay không. Timestamp bắt đầu job không nhất thiết là watermark dữ liệu đã xử lý; nên dùng thời điểm snapshot hoặc CDC position thực sự được bao phủ.

### 8.3. Late-arriving data và correction

Một sự kiện có event_time thuộc tháng trước nhưng chỉ được ingest hôm nay có thể làm thay đổi summary của kỳ cũ. Nếu refresh chỉ xử lý ngày hiện tại, số liệu sẽ sai.

Các lựa chọn:

- Refresh lại một cửa sổ gần đây đủ rộng theo đặc tính late arrival.
- Dùng CDC để cập nhật đúng nhóm cũ.
- Ghi nhận correction event riêng.
- Rebuild các kỳ bị ảnh hưởng theo lịch hoặc khi phát hiện.

Hãy đo phân phối độ trễ đến của dữ liệu, không chọn cửa sổ chỉ dựa trên cảm tính.

## 9. Làm mới an toàn và khả năng đọc đồng thời

Một refresh có thể thay thế dữ liệu cũ theo nhiều cách:

- Xóa và nạp lại trong một transaction.
- Xây dựng bảng mới rồi đổi tên/switch sang bảng hiện hành.
- Cập nhật từng partition hoặc từng nhóm.
- Dùng cơ chế refresh concurrent do DBMS cung cấp.

Mục tiêu là tránh để người đọc thấy bảng rỗng hoặc dữ liệu nửa cũ nửa mới ngoài ý muốn.

### 9.1. Atomic replacement

Nếu DBMS và phương thức hỗ trợ transaction phù hợp, thay thế nội dung trong một transaction có thể giúp người đọc thấy phiên bản cũ hoặc mới theo isolation semantics. Tuy nhiên, lock và thời gian commit có thể ảnh hưởng workload.

### 9.2. Build shadow table rồi publish

Một pattern cho summary table:

1. Tạo bảng staging hoặc phiên bản mới.
2. Nạp và xác minh toàn bộ dữ liệu.
3. Tạo index và thống kê cần thiết.
4. Publish bằng thao tác đổi metadata/partition switch/đổi pointer được DBMS hỗ trợ.
5. Giữ phiên bản cũ đủ lâu cho rollback rồi dọn sau.

Đổi tên hai bảng không phải lúc nào cũng là thao tác nguyên tử với mọi consumer, view, permission và foreign key. Hãy kiểm tra semantics của DDL và dependency trong DBMS cụ thể.

### 9.3. Refresh concurrent

Một số DBMS cho phép đọc materialized view trong lúc refresh bằng cơ chế concurrent hoặc online. Cơ chế này thường cần thêm index, tài nguyên và công việc đối chiếu. “Concurrent” không có nghĩa refresh miễn phí hoặc không có lock.

## 10. PostgreSQL materialized view

PostgreSQL hỗ trợ materialized view với nội dung lưu vật lý và lệnh REFRESH MATERIALIZED VIEW.

Tạo view:

~~~sql
CREATE MATERIALIZED VIEW daily_sales AS
SELECT
    created_at::date AS sales_date,
    region_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
GROUP BY created_at::date, region_id;
~~~

Làm mới:

~~~sql
REFRESH MATERIALIZED VIEW daily_sales;
~~~

Refresh thông thường tính lại toàn bộ truy vấn định nghĩa và thay thế nội dung materialized view. PostgreSQL không tự động biến lệnh này thành incremental refresh chỉ vì bảng nguồn chỉ thay đổi một phần.

### 10.1. REFRESH CONCURRENTLY

~~~sql
CREATE UNIQUE INDEX daily_sales_key
ON daily_sales (sales_date, region_id);

REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales;
~~~

REFRESH CONCURRENTLY cho phép các truy vấn khác tiếp tục đọc materialized view trong lúc refresh theo semantics của PostgreSQL, nhưng vẫn tính lại kết quả và cần đối chiếu/thay thế nội dung. Nó không phải incremental refresh.

Điều kiện quan trọng:

- Materialized view phải đã được populate.
- Phải có ít nhất một UNIQUE index dùng tên cột đơn thuần và bao phủ tất cả hàng; index không được là partial index hoặc dùng expression.
- Không thể chạy nhiều refresh đồng thời trên cùng một materialized view.

Concurrent refresh có thể cần thêm I/O, CPU và dung lượng tạm. So sánh thời gian và ảnh hưởng đọc với refresh thông thường.

### 10.2. Incremental maintenance trong PostgreSQL

PostgreSQL core không cung cấp incremental refresh tổng quát cho materialized view bằng lệnh REFRESH MATERIALIZED VIEW. Có thể xây dựng summary table do ứng dụng/ETL cập nhật theo CDC hoặc batch delta, hoặc dùng extension chuyên biệt nếu được chấp thuận trong môi trường.

Khi tự triển khai, cần xử lý update/delete, sự kiện trùng, late arrival, checkpoint và đối soát. Không được gọi REFRESH CONCURRENTLY là incremental.

## 11. Oracle materialized view

Oracle hỗ trợ nhiều dạng materialized view và cơ chế refresh như COMPLETE, FAST và FORCE, cùng các tùy chọn ON DEMAND hoặc ON COMMIT trong những trường hợp được hỗ trợ.

- **COMPLETE:** tính lại toàn bộ kết quả.
- **FAST:** áp dụng thay đổi tăng dần khi query và cấu hình đáp ứng điều kiện fast refresh.
- **FORCE:** thử fast refresh nếu khả thi, nếu không có thể dùng complete theo semantics của Oracle.
- **ON DEMAND:** refresh theo lệnh hoặc lịch.
- **ON COMMIT:** làm mới gắn với commit của bảng nguồn trong các cấu hình hỗ trợ; có thể làm tăng commit cost.

Ví dụ khái niệm:

~~~sql
BEGIN
  DBMS_MVIEW.REFRESH(
    list   => 'DAILY_SALES',
    method => 'F'
  );
END;
/
~~~

Ký tự phương thức và khả năng refresh cần được xác minh theo phiên bản Oracle và định nghĩa materialized view.

### 11.1. Materialized view log

Fast refresh thường cần materialized view log trên bảng nguồn để ghi nhận thay đổi cần thiết. Với một số truy vấn, cần lưu thêm sequence, rowid, primary key hoặc các cột liên quan. Điều kiện chính xác phụ thuộc query shape và loại materialized view.

Materialized view log tạo thêm chi phí trên đường ghi:

- Mỗi insert/update/delete có thể ghi thêm log record.
- Tăng dung lượng và I/O.
- Có thể làm commit transaction nguồn tốn thêm công việc.
- Cần quản lý vòng đời log và refresh consumer.

Trước khi chọn FAST, dùng công cụ phân tích như DBMS_MVIEW.EXPLAIN_MVIEW nếu phù hợp để kiểm tra khả năng fast refresh và nguyên nhân không đáp ứng.

### 11.2. ON COMMIT

ON COMMIT có thể giữ materialized view gần với dữ liệu nguồn hơn, nhưng công việc refresh có thể nằm trên đường commit của transaction nguồn. Điều này làm tăng latency ghi và có thể gây tranh chấp khi nhiều transaction cùng cập nhật.

Chỉ dùng khi freshness yêu cầu và query được hỗ trợ; benchmark commit latency dưới tải ghi đại diện.

## 12. SQL Server indexed view

SQL Server có indexed view: view được schema-bound và tạo unique clustered index để lưu kết quả vật lý. Khác với materialized view refresh theo lịch, indexed view được duy trì đồng bộ khi các bảng nền thay đổi, theo các điều kiện và giới hạn của SQL Server.

Ví dụ minh họa rút gọn:

~~~sql
CREATE VIEW dbo.RegionSales
WITH SCHEMABINDING
AS
SELECT
    region_id,
    COUNT_BIG(*) AS order_count,
    SUM(total_amount) AS revenue
FROM dbo.Orders
GROUP BY region_id;
GO

CREATE UNIQUE CLUSTERED INDEX IX_RegionSales
ON dbo.RegionSales(region_id);
~~~

Đây là ví dụ khái niệm; indexed view có nhiều yêu cầu về SET options, schema binding, hàm được phép, ownership, biểu thức và aggregate. Phải đối chiếu tài liệu SQL Server của phiên bản đang dùng trước khi triển khai.

### 12.1. Chi phí chuyển sang đường ghi

Vì indexed view được duy trì khi bảng nguồn thay đổi, INSERT/UPDATE/DELETE trên Orders phải cập nhật thêm cấu trúc indexed view. Điều này có thể giảm chi phí đọc nhưng tăng:

- CPU và I/O của DML.
- Locking và contention.
- Transaction log generation.
- Thời gian commit.
- Chi phí duy trì nhiều indexed view.

Indexed view phù hợp khi lợi ích đọc lặp lại đủ lớn để bù chi phí duy trì trên mọi thay đổi nguồn. Hãy benchmark cả truy vấn đọc và transaction ghi.

## 13. MySQL và bảng tổng hợp do ứng dụng quản lý

MySQL không có materialized view native tổng quát tương đương cú pháp CREATE MATERIALIZED VIEW của PostgreSQL/Oracle. Một mô hình phổ biến là tạo summary table và cập nhật bằng:

- Scheduled ETL hoặc event-driven worker.
- INSERT ... SELECT theo cửa sổ dữ liệu.
- CDC từ binlog.
- Trigger, nếu workload và yêu cầu vận hành phù hợp.
- Job định kỳ tính lại một số partition/kỳ.

Ví dụ tạo bảng:

~~~sql
CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    region_id BIGINT NOT NULL,
    order_count BIGINT NOT NULL,
    revenue DECIMAL(20, 2) NOT NULL,
    PRIMARY KEY (sales_date, region_id)
);
~~~

Một job có thể tính lại một ngày:

~~~sql
INSERT INTO daily_sales_summary (
    sales_date, region_id, order_count, revenue
)
SELECT
    DATE(created_at),
    region_id,
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE created_at >= :day_start
  AND created_at < :next_day
GROUP BY DATE(created_at), region_id
ON DUPLICATE KEY UPDATE
    order_count = VALUES(order_count),
    revenue = VALUES(revenue);
~~~

Cú pháp VALUES trong ON DUPLICATE KEY UPDATE có thay đổi/deprecation tùy phiên bản MySQL; hãy dùng cú pháp được hỗ trợ bởi phiên bản mục tiêu. Quan trọng hơn, job trên đang thay thế tổng của cả ngày được chọn, không phải cộng delta. Nếu nhiều job cùng refresh một ngày, cần điều phối và bảo đảm không publish kết quả cũ sau kết quả mới.

Không nên dùng trigger để cập nhật summary phức tạp nếu nó làm transaction OLTP dài, tạo deadlock hoặc làm tăng write amplification. Trigger chạy đồng bộ trên đường ghi và có thể làm mọi insert chịu chi phí tổng hợp.

## 14. Thiết kế incremental summary table

Với bảng tổng hợp tự quản lý, cần định nghĩa một giao thức cập nhật rõ ràng.

### 14.1. Xác định nguồn delta

Delta có thể đến từ:

- CDC log.
- Event stream.
- Bảng audit/change log.
- Cột updated_at và watermark, nếu có thể bảo đảm không bỏ sót.
- Batch ID do hệ thống nguồn cung cấp.

Chỉ dùng updated_at nếu mọi thay đổi đều cập nhật cột này, độ chính xác thời gian đủ và job có cách xử lý transaction commit muộn. Query kiểu updated_at > last_time có thể bỏ sót dữ liệu nếu nhiều hàng có cùng timestamp hoặc transaction commit sau khi watermark đã tiến.

### 14.2. Checkpoint và idempotency

Mỗi batch cần một ID hoặc vị trí CDC đã xử lý. Cập nhật summary và checkpoint trong cùng transaction nếu cùng DBMS và cùng database. Nếu checkpoint ở hệ thống ngoài, cần cơ chế chống áp dụng lặp hoặc mất delta.

Ví dụ:

~~~text
Read source changes after checkpoint
    |
    v
Group delta by summary key
    |
    v
BEGIN
    Apply delta to summary
    Record processed batch/offset
COMMIT
    |
    v
Advance consumer position
~~~

Nếu consumer crash sau commit nhưng trước khi xác nhận offset, batch có thể được gửi lại. Bảng processed_batch hoặc idempotency key giúp tránh cộng trùng.

### 14.3. Xử lý update và delete

Để cập nhật chính xác SUM/COUNT, cần before-image hoặc trạng thái cũ:

- Trừ measure cũ khỏi nhóm cũ.
- Cộng measure mới vào nhóm mới.
- Nếu khóa nhóm không đổi, điều chỉnh chênh lệch.
- Khi số lượng nhóm về 0, quyết định xóa hàng summary hay giữ hàng với giá trị 0.

Với delete, chỉ biết khóa hàng bị xóa mà không biết measure cũ thì không thể trừ đúng SUM. CDC cần cung cấp before-image hoặc summary phải được rebuild từ nguồn.

### 14.4. Xử lý sự kiện đến muộn

Sự kiện có event_time cũ nhưng ingest_time mới cần cập nhật kỳ cũ. Có thể partition summary theo kỳ và cập nhật partition tương ứng. Cần theo dõi số lần correction và thời gian từ event_time đến ingest_time để thiết kế cửa sổ rebuild.

## 15. Refresh theo partition hoặc theo cửa sổ

Với summary theo ngày/tháng, thay vì rebuild toàn bộ lịch sử, có thể tính lại các kỳ gần đây.

Ví dụ quy trình:

1. Xác định các ngày có thay đổi nguồn.
2. Tính lại toàn bộ summary cho các ngày đó vào staging.
3. Đối chiếu row count và tổng measure.
4. Thay thế dữ liệu của các ngày bị ảnh hưởng trong summary chính.
5. Cập nhật watermark cho từng kỳ.

Refresh theo partition giúp giới hạn phạm vi đọc và ghi. Tuy nhiên, nó chỉ đúng nếu hệ thống xác định được đầy đủ các kỳ bị ảnh hưởng. Nếu update một order có thể đổi created_at từ tháng cũ sang tháng mới, cả hai kỳ cần được tính lại hoặc cập nhật delta.

Một số DBMS hỗ trợ partition exchange/switch để publish dữ liệu theo kỳ với ít thao tác hàng hơn. Điều kiện về cấu trúc bảng, index, constraint và lock cần được kiểm tra theo sản phẩm.

## 16. Index cho materialized view và summary table

Kết quả tổng hợp thường nhỏ hơn nguồn nhưng vẫn cần index theo truy vấn đọc thực tế.

Ví dụ summary theo ngày và khu vực:

~~~sql
CREATE INDEX sales_summary_region_date_idx
ON sales_daily_summary (region_id, sales_date);
~~~

Nếu truy vấn chính lọc một region và khoảng ngày, thứ tự này có thể phù hợp. Nếu truy vấn thường lấy mọi region cho một khoảng ngày, index bắt đầu bằng sales_date có thể tốt hơn. Hãy xem predicate, sort và cardinality.

### 16.1. Không tạo index dư thừa

Mỗi index bổ sung làm tăng:

- Dung lượng lưu trữ.
- Chi phí INSERT/UPDATE/DELETE hoặc refresh.
- WAL/redo/transaction log.
- Buffer cache footprint.
- Thời gian rebuild và backup.

Summary có vài nghìn hàng có thể không cần nhiều index. Dùng execution plan và workload để xác định index nào thực sự giảm chi phí.

### 16.2. Unique key cho grain

Khóa duy nhất của summary phải phản ánh grain. Với grain ngày-khu vực, có thể dùng (sales_date, region_id). Unique key giúp upsert và bảo đảm mỗi nhóm chỉ có một hàng.

Nếu grain còn tenant_id, currency hoặc channel, phải đưa các chiều này vào khóa. Bỏ một dimension có thể làm các nhóm khác nhau bị gộp nhầm.

## 17. Query rewrite và sử dụng materialized view

Một số DBMS có thể tự động rewrite truy vấn để dùng materialized view hoặc indexed view nếu optimizer chứng minh kết quả tương đương và cấu hình cho phép. Hệ khác yêu cầu ứng dụng truy vấn trực tiếp tên view/table.

Không giả định việc tạo materialized view khiến truy vấn gốc tự động sử dụng nó. Hãy:

- Kiểm tra execution plan của truy vấn gốc.
- Xem operator có đọc materialized view/indexed view hay bảng nguồn.
- Xác minh các predicate và aggregate có tương thích với định nghĩa.
- Kiểm tra freshness và query rewrite settings.
- So sánh kết quả với truy vấn gốc.

Nếu ứng dụng truy vấn trực tiếp summary table, logic chọn phiên bản dữ liệu và freshness cần được thể hiện rõ trong API hoặc query.

## 18. Làm mới đồng thời và tránh ghi đè kết quả mới bằng kết quả cũ

Một lỗi phổ biến là hai refresh job chạy chồng:

1. Job A bắt đầu đọc snapshot cũ.
2. Job B bắt đầu sau đó, đọc dữ liệu mới hơn và hoàn tất trước.
3. Job A hoàn tất muộn và publish kết quả cũ đè lên kết quả mới.

Cần ngăn nhiều refresh cùng cập nhật một summary key hoặc cùng publish phiên bản:

- Dùng lock/lease theo materialized view hoặc partition.
- Ghi refresh_run_id và watermark.
- Chỉ publish nếu watermark của run mới hơn phiên bản hiện hành.
- Dùng staging table và thao tác swap có điều kiện.
- Điều phối scheduler để tránh overlap.

Nếu refresh chạy theo từng partition, có thể cho phép các kỳ độc lập chạy song song, nhưng phải bảo đảm hai job không cập nhật cùng kỳ hoặc cùng khóa tổng hợp.

## 19. Đối soát tính đúng đắn của summary

Summary có thể sai mà query vẫn chạy nhanh. Cần kiểm tra định kỳ bằng truy vấn độc lập trên nguồn hoặc một mẫu dữ liệu tin cậy.

Các phép đối soát:

- So sánh COUNT(*) theo kỳ và dimension.
- So sánh SUM(amount), SUM(quantity).
- Kiểm tra số nhóm và khóa trùng.
- Đối chiếu các kỳ có correction/late arrival.
- So sánh một số nhóm được chọn với truy vấn gốc.
- Kiểm tra watermark và refresh run status.
- Kiểm tra tổng toàn cục có bằng tổng các nhóm khi logic cho phép.

Ví dụ:

~~~sql
SELECT
    sales_date,
    SUM(order_count) AS total_orders,
    SUM(revenue) AS total_revenue
FROM sales_daily_summary
GROUP BY sales_date
ORDER BY sales_date;
~~~

So sánh với truy vấn nguồn được viết độc lập, cùng filter, timezone, currency và quy tắc xử lý trạng thái. Không dùng chính logic summary để tự xác minh summary.

Với dữ liệu tài chính, cần xác định quy tắc làm tròn, tiền tệ và thời điểm đóng kỳ. Tổng hợp theo DECIMAL có thể cần độ chính xác khác với phép tính floating point.

## 20. Giám sát refresh và freshness

Một pipeline summary nên có metric:

| Nhóm | Metric |
|---|---|
| Freshness | Thời điểm refresh thành công, source watermark, tuổi dữ liệu cũ nhất |
| Runtime | Refresh duration, queue time, thời gian từng phase |
| Throughput | Số hàng/byte đọc, số nhóm tạo, số hàng ghi |
| Resource | CPU, memory, temp spill, I/O, log bytes |
| Contention | Lock wait, blocking, query latency khi refresh chạy |
| Reliability | Success/failure, retry, số lần refresh chồng lấn |
| Correctness | Row count, checksum, đối soát SUM/COUNT, correction count |
| Replication | WAL/redo/binlog generation, send/apply lag và queue |

Đặt cảnh báo khi refresh thất bại, freshness vượt SLO, job chạy lâu bất thường, summary không tăng watermark, out-of-order correction tăng hoặc replication lag vượt ngưỡng.

Không chỉ cảnh báo job failed. Một job có thể báo success nhưng chỉ xử lý một phần dữ liệu do watermark hoặc filter sai. Cần kết hợp kiểm tra freshness và correctness.

## 21. Ví dụ thiết kế dashboard doanh thu

Giả sử dashboard cần:

- Doanh thu và số đơn theo ngày, khu vực.
- Lọc theo khoảng ngày tối đa 90 ngày.
- Dữ liệu trễ tối đa 15 phút.
- Order có thể bị hủy hoặc hoàn tiền trong 48 giờ sau khi tạo.

Một thiết kế khả thi:

1. Summary grain là ngày-khu vực.
2. Lưu order_count, gross_revenue, refund_amount và net_revenue.
3. Dùng CDC hoặc batch delta để nhận thay đổi.
4. Refresh lại các ngày có thay đổi trong cửa sổ 48 giờ, cộng thêm khoảng an toàn dựa trên phân phối late arrival.
5. Cập nhật summary theo batch idempotent.
6. Tạo index theo sales_date và region_id theo query pattern.
7. Lưu watermark và refresh timestamp.
8. Đối soát tổng theo ngày với nguồn.
9. Nếu dữ liệu cũ hơn cửa sổ có correction, đưa kỳ tương ứng vào hàng đợi rebuild.

Nếu dashboard cần truy vấn theo sản phẩm, kênh và tiền tệ, phải cân nhắc thêm dimension. Thêm tất cả dimensions có thể làm summary tăng mạnh; có thể tạo summary riêng cho nhóm báo cáo quan trọng hoặc dùng cube/warehouse phù hợp.

Không cộng doanh thu từ nhiều currency nếu chưa quy đổi theo tỷ giá và thời điểm quy đổi thống nhất. Grain có thể cần currency_code để tránh gộp sai.

## 22. Những sai lầm thường gặp

- **Nhầm view với materialized view.** View thông thường không nhất thiết lưu kết quả.
- **Tạo materialized view rồi cho rằng query tự dùng nó.** Cần kiểm tra query rewrite hoặc truy vấn trực tiếp.
- **Gọi refresh complete là incremental.** Refresh concurrent không đồng nghĩa refresh tăng dần.
- **Chọn grain quá chi tiết.** Summary gần bằng nguồn, giảm ít chi phí đọc nhưng vẫn tăng chi phí lưu trữ.
- **Chọn grain quá thô.** Không thể trả lời truy vấn cần dimension đã bị gộp.
- **Cộng AVG của các nhóm.** Phải lưu SUM và COUNT để tính trung bình có trọng số đúng.
- **Cập nhật SUM mà không trừ before-image.** Update/delete có thể làm summary sai.
- **Cộng COUNT DISTINCT theo batch.** Một giá trị có thể đã xuất hiện trong batch trước.
- **Bỏ qua late-arriving data.** Kỳ lịch sử có thể sai dù job hiện tại thành công.
- **Chạy refresh chồng lấn.** Job cũ hoàn tất muộn có thể ghi đè dữ liệu mới.
- **Tạo quá nhiều index trên summary.** Chi phí refresh và dung lượng tăng.
- **Không tính log và replica.** Refresh có thể tạo write burst và replication lag.
- **Chỉ theo dõi job success.** Cần đo freshness và đối soát correctness.
- **Dùng trigger cho tổng hợp nặng trên đường OLTP.** Có thể kéo dài transaction nguồn và làm tăng lock/latency.

## 23. Quy trình chọn và triển khai

1. **Đo truy vấn gốc.** Thu thập execution plan, CPU, I/O, runtime, tần suất và p95/p99.
2. **Xác định nhu cầu freshness.** Ghi rõ dữ liệu được phép trễ bao lâu và cách xử lý correction.
3. **Thiết kế grain.** Chọn dimensions và measures theo truy vấn thực tế; ước lượng số nhóm.
4. **Chọn cơ chế lưu.** View, native materialized view, indexed view hay summary table do pipeline quản lý.
5. **Chọn refresh mode.** Complete, incremental, cửa sổ thời gian, on demand hoặc on commit tùy DBMS và yêu cầu.
6. **Tính chi phí ghi.** Ước lượng CPU, memory, temp I/O, index maintenance, log và replication.
7. **Thiết kế correctness.** Xử lý update/delete, before-image, duplicate, late arrival, checkpoint và idempotency.
8. **Thiết kế publish.** Bảo đảm reader không thấy trạng thái nửa chừng; ngăn refresh job ghi đè phiên bản mới.
9. **Tạo index có chọn lọc.** Phù hợp với filter, join và order của truy vấn summary.
10. **Benchmark end-to-end.** Đo chi phí đọc tiết kiệm được cùng refresh runtime, write amplification và tác động workload nền.
11. **Đối soát kết quả.** So sánh COUNT, SUM và các nhóm mẫu với nguồn.
12. **Giám sát production.** Theo dõi freshness, watermark, failure, resource usage và replica lag.

## 24. Checklist kiểm chứng

- [ ] Đã đo chi phí truy vấn gốc và tần suất sử dụng.
- [ ] Đã xác định freshness SLA và quy tắc snapshot/watermark.
- [ ] Grain của summary phản ánh đúng đơn vị nghiệp vụ.
- [ ] Dimensions và measures có cardinality, kiểu dữ liệu và độ chính xác phù hợp.
- [ ] AVG được lưu dưới dạng SUM/COUNT khi cần gộp.
- [ ] Đã đánh giá khả năng incremental của từng aggregate.
- [ ] Update/delete có before-image hoặc quy trình rebuild đúng.
- [ ] Có xử lý late arrival, correction và sự kiện trùng.
- [ ] Đã phân biệt complete refresh với incremental refresh.
- [ ] Đã kiểm tra semantics concurrent/online refresh của DBMS.
- [ ] Có cơ chế ngăn refresh chồng lấn và publish kết quả cũ.
- [ ] Index trên summary được chọn theo truy vấn đọc thực tế.
- [ ] Đã đo CPU, memory, temp I/O, log và replication trong lúc refresh.
- [ ] Đã kiểm tra reader có thấy phiên bản cũ/mới theo yêu cầu nhất quán.
- [ ] Có watermark, refresh run ID, retry và checkpoint.
- [ ] Đã đối soát COUNT/SUM và các nhóm dữ liệu đại diện với nguồn.
- [ ] Đã benchmark lợi ích đọc so với chi phí refresh và vận hành.
- [ ] Có cảnh báo freshness vượt SLO, refresh thất bại và backlog tăng.

Materialized view và bảng tổng hợp giúp tránh tính lại những phép phân tích lặp lại, nhưng chi phí được chuyển sang refresh, lưu trữ, index maintenance và log. Complete refresh đơn giản nhưng có thể đọc/ghi lại toàn bộ; incremental refresh tiết kiệm khi delta nhỏ nhưng cần xử lý chính xác insert, update, delete, duplicate và late arrival. Chọn grain theo truy vấn, xác định freshness SLA, kiểm tra khả năng của DBMS và đo cả đường đọc lẫn đường ghi. Một summary chỉ thực sự có ích khi nó trả lời đúng câu hỏi nghiệp vụ, đủ mới, đối soát được và giảm tổng chi phí của workload.
