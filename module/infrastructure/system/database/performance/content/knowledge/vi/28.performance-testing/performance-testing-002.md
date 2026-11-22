# Sinh dữ liệu đại diện về kích thước, phân bố và quan hệ

Một bài kiểm thử hiệu năng chỉ có ý nghĩa khi dữ liệu thử nghiệm tạo ra những đường truy cập gần với hệ thống thực tế. Một bảng có một triệu hàng ngẫu nhiên không nhất thiết đại diện cho bảng production có một triệu hàng: độ rộng hàng có thể khác, một vài khách hàng có thể chiếm phần lớn giao dịch, các cột có thể tương quan, nhiều hàng có thể cùng tham chiếu một khóa nóng, và quan hệ giữa các bảng có thể tạo ra fan-out lớn khi JOIN.

Dữ liệu quá đơn giản thường làm execution plan trông tốt hơn thực tế. Ví dụ, nếu mọi customer_id xuất hiện với tần suất bằng nhau, optimizer có thể ước lượng selectivity khác với workload có một nhóm khách hàng rất nóng. Nếu dữ liệu chỉ có vài giá trị, index có thể được chọn theo một phân bố không giống production. Nếu các bảng con được tạo độc lập mà không giữ foreign key, truy vấn JOIN có thể trả về quá ít hàng hoặc không phản ánh chi phí thật.

Trong tối ưu hiệu năng cơ sở dữ liệu, dữ liệu kiểm thử phải đại diện ít nhất cho **kích thước**, **phân bố giá trị** và **quan hệ giữa các thực thể**. Bài học này hướng dẫn cách thu thập đặc trưng workload, tạo dữ liệu tổng hợp an toàn và có thể tái lập, mô phỏng skew và tương quan, giữ đúng cardinality và quan hệ khóa, xác minh dữ liệu sau sinh, rồi dùng nó để kiểm thử execution plan và hiệu năng ở nhiều quy mô.

## 1. Dữ liệu kiểm thử đại diện cần mô phỏng điều gì?

Một tập dữ liệu đại diện không chỉ là tập có cùng số hàng với production. Nó cần phản ánh các đặc tính có thể làm thay đổi cách DBMS lưu trữ, lập thống kê, chọn execution plan và thực thi truy vấn.

Các nhóm đặc tính chính:

| Nhóm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kích thước | Có bao nhiêu hàng và bao nhiêu byte? | 200 triệu orders, 1,5 KB/hàng |
| Cardinality | Một cột có bao nhiêu giá trị khác nhau? | 50 triệu customer_id, 8 trạng thái |
| Phân bố | Giá trị có đều hay lệch? | 1% tenant tạo 60% request |
| Tương quan | Hai hay nhiều cột có phụ thuộc nhau? | Khu vực gắn với loại sản phẩm |
| Độ rộng | Giá trị chuỗi/JSON/BLOB dài bao nhiêu? | 80% payload nhỏ, 20% payload lớn |
| Quan hệ | Các bảng liên kết theo tỷ lệ nào? | Một order có 1–40 order_items |
| Thời gian | Dữ liệu mới, cũ và sự kiện đến muộn phân bố ra sao? | 90% truy vấn vào 14 ngày gần nhất |
| Mẫu ghi | Insert, update, delete tập trung ở đâu? | 70% update vào trạng thái và thời điểm gần đây |
| Working set | Phần dữ liệu nào được truy cập thường xuyên? | 5% hàng nhận 75% lượt đọc |
| Giá trị biên | Có NULL, giá trị cực lớn hoặc ngoại lệ không? | Amount bằng 0, rất lớn, timestamp sát ranh giới |

Không phải workload nào cũng cần mô phỏng tất cả đặc tính ở cùng mức độ. Hãy ưu tiên những yếu tố tác động đến truy vấn và thao tác ghi đang được kiểm thử.

## 2. Bắt đầu từ workload và câu hỏi kiểm thử

Trước khi sinh dữ liệu, xác định mục tiêu đo:

- Tối ưu một truy vấn cụ thể hay kiểm tra toàn bộ workload?
- Kiểm tra index, partitioning, join strategy, cache hay concurrency?
- Đo thời gian truy vấn ở cache nóng, cache lạnh hay cả hai?
- Kiểm tra throughput ghi và replication lag?
- Đánh giá khả năng tăng trưởng khi dữ liệu lớn gấp 2, 5 hoặc 10 lần?
- Kiểm tra hành vi ở tenant lớn, nhóm dữ liệu hiếm hoặc khoảng thời gian cao điểm?

Mỗi mục tiêu cần một profile dữ liệu phù hợp. Ví dụ, benchmark point lookup cần cardinality và tỷ lệ key nóng thực tế; benchmark báo cáo cần phân bố theo thời gian, join fan-out và số nhóm aggregate; benchmark bulk load cần độ rộng hàng, index, constraint và log volume gần thực tế.

### 2.1. Lấy đặc trưng từ production một cách an toàn

Có thể dùng metric và thống kê tổng hợp để mô tả dữ liệu production mà không sao chép thông tin nhạy cảm:

- Row count và table/index size.
- Số giá trị khác nhau (NDV) của cột.
- Histogram, most common values (MCV) và tần suất theo bucket.
- Tỷ lệ NULL.
- Phân vị độ dài chuỗi hoặc payload.
- Số hàng con trên mỗi hàng cha.
- Tần suất truy cập theo key, tenant, ngày hoặc partition.
- Tỷ lệ insert/update/delete.
- Tỷ lệ truy vấn theo từng loại predicate.
- Phân phối transaction size và thời gian giữ lock.

Không cần xuất dữ liệu định danh cá nhân để lấy những đặc trưng này. Có thể xuất histogram, bucket, tỷ lệ và số liệu đã tổng hợp.

### 2.2. Chọn profile dữ liệu

Một profile là bản mô tả các phân phối và quan hệ cần tái tạo. Ví dụ:

~~~text
Profile: OLTP orders
Customers: 20 million
Orders: 300 million
Order items: 1.2 billion
Active customers: 25% tạo 85% orders
Orders/customer: median 4, p95 40, p99 250
Order status: 70% completed, 15% pending, 10% cancelled, 5% refunded
Recent 14 days: 35% orders
Hot tenants: 2% tenant tạo 45% traffic
Items/order: median 3, p95 12
Payload size: p50 600 B, p95 4 KB, p99 40 KB
~~~

Các con số trên chỉ minh họa cấu trúc profile. Profile thật phải lấy từ workload mục tiêu.

## 3. Kích thước dữ liệu: số hàng chưa đủ

Hai bảng cùng có 100 triệu hàng có thể chiếm dung lượng rất khác nhau. Cần xem:

- Số byte trung bình và phân phối độ rộng hàng.
- Overhead của row header, null bitmap, alignment và page structure.
- Số lượng index và kích thước key.
- Compression hoặc TOAST/LOB/off-row storage.
- Fill factor, page density và fragmentation.
- Partition count và dung lượng từng partition.
- Dung lượng log, temp và dữ liệu trung gian trong truy vấn.

### 3.1. Scale factor

Scale factor là hệ số tăng quy mô so với một profile cơ sở. Nếu profile cơ sở có 10 triệu orders và scale factor là 5, dữ liệu mục tiêu có khoảng 50 triệu orders. Tuy nhiên, chỉ nhân row count không đủ nếu phân bố và quan hệ không được giữ đúng.

Nên tạo nhiều mức:

| Mức | Mục đích |
|---|---|
| 0,1x | Kiểm tra logic generator và nhanh chóng thử truy vấn |
| 1x | Đại diện quy mô hiện tại |
| 2x–3x | Kiểm tra xu hướng tăng trưởng |
| 5x–10x | Tìm giới hạn dung lượng, index, memory và I/O |

Không phải hệ thống nào cũng cần đủ mọi mức. Chọn theo mục tiêu capacity planning và ngân sách môi trường thử nghiệm.

### 3.2. Working set và cache

Một dataset nhỏ hơn RAM có thể nằm gần như toàn bộ trong buffer cache. Khi đó, truy vấn đo được chủ yếu là CPU và memory access. Production có working set lớn hơn cache có thể chịu physical I/O đáng kể.

Hãy xác định:

- Tổng dung lượng bảng và index.
- Kích thước working set thường được truy cập.
- Tỷ lệ cache hit ở môi trường mục tiêu.
- Dữ liệu nóng có tập trung vào một phần nhỏ không.
- Có chạy benchmark warm-cache và cold-cache hay không.

Nếu mục tiêu là kiểm tra I/O, cần tạo dataset và working set đủ lớn để vượt cache theo cách phù hợp. Không xóa cache hoặc restart database liên tục mà không kiểm soát, vì thao tác đó có thể tạo điều kiện đo không thực tế.

### 3.3. Độ rộng hàng và dữ liệu ngoài hàng

Độ rộng hàng ảnh hưởng số hàng trên mỗi page, số page phải đọc, cache footprint và chi phí ghi. Nếu production có JSON lớn, VARCHAR dài hoặc BLOB, dữ liệu thử nghiệm chỉ dùng chuỗi ngắn sẽ làm giảm đáng kể I/O.

Hãy mô phỏng phân phối độ dài thay vì đặt mọi giá trị cùng độ dài. Ví dụ:

- 60% payload nhỏ dưới 500 byte.
- 30% payload từ 500 byte đến 4 KB.
- 9% payload từ 4 KB đến 32 KB.
- 1% payload rất lớn trên 32 KB.

Đây chỉ là profile minh họa. Với LOB/JSON, cần xem DBMS lưu inline hay ngoài hàng, có nén hay không và truy vấn có thực sự đọc payload không.

## 4. Cardinality và NDV

Cardinality của cột là số giá trị khác nhau trong dữ liệu. NDV (number of distinct values) thường được optimizer dùng để ước lượng selectivity và số hàng trả về.

Ví dụ:

| Cột | Tổng hàng | NDV | Ý nghĩa |
|---|---:|---:|---|
| order_id | 300 triệu | 300 triệu | Gần như duy nhất |
| customer_id | 300 triệu | 20 triệu | Một khách hàng có nhiều đơn |
| status | 300 triệu | 4 | Cardinality thấp |
| region_id | 300 triệu | 30 | Cardinality thấp/trung bình |
| coupon_code | 300 triệu | 2 triệu | Nhiều giá trị hiếm |

Một index trên cột cardinality thấp không phải lúc nào cũng vô ích; hiệu quả phụ thuộc phân phối, clustering, predicate và số hàng cần đọc. Nhưng dữ liệu thử nghiệm cần giữ NDV gần profile thực để optimizer có thể đưa ra quyết định tương tự.

### 4.1. Không tạo cardinality giả

Nếu production có 20 triệu customer nhưng test chỉ có 100 customer, số orders trên mỗi customer sẽ cao hơn nhiều. Query theo customer_id, join orders-customers và index selectivity sẽ khác.

Ngược lại, tạo customer_id mới cho từng order khiến quan hệ one-to-many biến thành gần one-to-one, làm join fan-out nhỏ hơn thực tế.

### 4.2. Cardinality theo nhóm

NDV tổng thể không mô tả hết phân bố. Một cột status có 4 giá trị nhưng tỷ lệ có thể là 90/5/3/2 hoặc 25/25/25/25. Hai dataset có cùng NDV vẫn tạo kế hoạch khác nhau.

Hãy lưu cả số giá trị khác nhau và tỷ lệ từng nhóm hoặc histogram.

## 5. Phân bố đồng đều, lệch và heavy hitters

Dữ liệu production hiếm khi phân bố đồng đều. Một số key hoặc category có thể xuất hiện rất thường xuyên.

### 5.1. Uniform distribution

Uniform nghĩa là mỗi giá trị có xác suất xuất hiện gần bằng nhau. Đây là mô hình đơn giản và hữu ích cho một số test, nhưng thường không đủ để đại diện workload có tenant lớn, khách hàng VIP hoặc sản phẩm bán chạy.

### 5.2. Skewed distribution

Skew là phân bố lệch: một số giá trị chiếm tỷ trọng lớn, còn phần lớn giá trị xuất hiện ít.

Ví dụ:

- 1% customer tạo 40% orders.
- 5% tenant tạo 70% request.
- 10 sản phẩm đứng đầu chiếm 55% lượt xem.
- Một trạng thái chiếm 85% hàng.

Skew ảnh hưởng:

- Selectivity của predicate.
- Phân phối key trong B-tree.
- Hot page và lock contention.
- Hash join/aggregate partition balance.
- Cache locality.
- Khả năng song song hóa và data skew giữa worker.

### 5.3. Heavy hitters

Heavy hitters là một nhóm nhỏ giá trị xuất hiện với tần suất rất cao. Khi benchmark, cần tạo đúng nhóm này để kiểm tra:

- Query theo một key nóng.
- Query theo key hiếm.
- Query không lọc key.
- Update/insert đồng thời vào cùng key hoặc cùng vùng dữ liệu.

Một benchmark chỉ dùng key ngẫu nhiên đều có thể bỏ qua hot-key contention.

### 5.4. Các phân phối thường dùng

| Phân phối | Đặc điểm | Trường hợp mô phỏng |
|---|---|---|
| Uniform | Các giá trị gần đồng đều | ID ngẫu nhiên hoặc category cân bằng |
| Normal/Gaussian | Tập trung quanh trung bình, ít giá trị ở hai đuôi | Một số phép đo tự nhiên có dạng chuông |
| Log-normal | Giá trị dương, đuôi phải dài | Amount, thời lượng, kích thước payload |
| Zipf | Một số ít giá trị rất phổ biến, tần suất giảm theo rank | Key truy cập, sản phẩm, tenant |
| Pareto | Một phần nhỏ đóng góp phần lớn tổng lượng | Phân bố doanh thu hoặc tải |
| Categorical weighted | Nhóm giá trị có xác suất định trước | Status, region, channel |

Không chọn phân phối chỉ vì tên gọi quen thuộc. Hãy so sánh histogram, percentile và tỷ trọng heavy hitters của dữ liệu sinh với số liệu mục tiêu.

## 6. Tương quan giữa các cột

Optimizer có thể ước lượng sai khi các cột có tương quan nhưng thống kê chỉ xem từng cột độc lập.

Ví dụ:

- region_id liên quan đến currency_code.
- tenant_id liên quan đến plan_type.
- order_status liên quan đến cancelled_at.
- product_category liên quan đến price range.
- created_at liên quan đến trạng thái hoàn tất.

Nếu generator chọn từng cột độc lập, nó có thể tạo các tổ hợp hiếm hoặc vô lý. Ví dụ khách hàng ở một khu vực nhưng có currency không phù hợp, hoặc order status là CANCELLED nhưng completed_at luôn có giá trị.

### 6.1. Tương quan dương và âm

- **Tương quan dương:** giá trị một cột tăng thì giá trị cột kia có xu hướng tăng.
- **Tương quan âm:** giá trị một cột tăng thì giá trị cột kia có xu hướng giảm.
- **Phụ thuộc theo nhóm:** phân phối cột B thay đổi theo giá trị cột A.

Không nhất thiết mọi tương quan đều tuyến tính. Nhiều quan hệ nghiệp vụ là phụ thuộc theo nhóm hoặc theo thời gian.

### 6.2. Conditional distribution

Thay vì sinh region và currency độc lập, hãy sinh currency dựa trên region:

~~~text
if region = NORTH_AMERICA:
    currency ~ {USD: 80%, CAD: 20%}
if region = EUROPE:
    currency ~ {EUR: 75%, GBP: 15%, CHF: 10%}
if region = ASIA:
    currency ~ {VND: 35%, JPY: 25%, SGD: 20%, OTHER: 20%}
~~~

Các tỷ lệ chỉ minh họa. Cách này giữ được quan hệ giữa dimensions tốt hơn hai bộ random độc lập.

### 6.3. Tương quan và composite predicate

Giả sử truy vấn:

~~~sql
SELECT *
FROM orders
WHERE region_id = 3
  AND status = 'PENDING';
~~~

Nếu region và status tương quan, selectivity của hai điều kiện kết hợp không bằng tích selectivity riêng lẻ trong mọi trường hợp. Dataset kiểm thử cần giữ tương quan để đánh giá cardinality estimate và lựa chọn index/scan chính xác hơn.

Một test profile nên có:

- Tỷ lệ từng giá trị riêng lẻ.
- Tỷ lệ các tổ hợp quan trọng.
- Các tổ hợp phổ biến và hiếm.
- Một số tổ hợp không hợp lệ hoặc không xuất hiện nếu nghiệp vụ cấm chúng.

## 7. Phân bố thời gian và tính nóng/lạnh

Nhiều hệ thống có dữ liệu thời gian và workload thay đổi theo thời điểm.

Đặc trưng cần mô phỏng:

- Tỷ lệ dữ liệu mới so với lịch sử.
- Tần suất truy cập theo ngày/giờ.
- Burst theo giờ cao điểm hoặc ngày trong tuần.
- Seasonality theo tháng, quý hoặc chiến dịch.
- Late-arriving events.
- Update dữ liệu cũ và correction.
- Retention và archive.

Ví dụ, hệ thống có 500 triệu events nhưng 70% truy vấn chỉ đọc 14 ngày gần nhất. Nếu test generator tạo truy vấn đều trên toàn bộ lịch sử, working set sẽ khác production. Nếu chỉ sinh dữ liệu trong 14 ngày gần nhất, lại không kiểm tra được partition pruning và truy vấn lịch sử.

Nên tạo đủ lịch sử để kiểm tra partition và index, đồng thời mô phỏng xác suất truy cập tập trung vào khoảng gần đây.

### 7.1. Timestamp và timezone

Hãy thống nhất:

- Kiểu timestamp có hoặc không có timezone.
- Múi giờ lưu trữ.
- Múi giờ dùng để chia ngày nghiệp vụ.
- Cách xử lý DST nếu vùng nghiệp vụ có daylight saving time.
- Ranh giới ngày/tháng và truy vấn khoảng nửa mở.

Nếu dữ liệu test sinh timestamp UTC nhưng truy vấn production dùng ngày địa phương mà không chuyển đổi đúng, số hàng ở từng partition/ngày có thể khác.

### 7.2. Late-arriving data

Một event có event_time cũ nhưng ingest_time mới. Tạo dữ liệu đại diện cần giữ hai mốc thời gian này riêng biệt. Nếu đặt chúng luôn bằng nhau, test sẽ bỏ qua correction và refresh lịch sử.

## 8. Tỷ lệ NULL, giá trị biên và ngoại lệ

NULL ảnh hưởng predicate, index, join và thống kê. Hãy mô phỏng tỷ lệ NULL theo từng cột, không đặt tất cả cột NOT NULL hoặc NULL tùy ý.

Các giá trị biên cần xem:

- Chuỗi rỗng, chuỗi chỉ có khoảng trắng và chuỗi rất dài.
- Số 0, số âm, số lớn nhất hợp lệ và giá trị gần overflow.
- Amount có nhiều số lẻ và giá trị cực lớn.
- Timestamp ở ranh giới ngày/tháng/năm.
- Unicode, ký tự có dấu, emoji và collation-sensitive text.
- JSON thiếu field, field NULL, mảng rỗng hoặc cấu trúc lồng sâu.
- BLOB/CLOB rất nhỏ và rất lớn.

Các ngoại lệ hiếm có thể không ảnh hưởng throughput trung bình nhưng có thể gây p99 xấu, memory spill hoặc lỗi kiểu dữ liệu. Tỷ lệ ngoại lệ nên gần với nguồn và có một số test chuyên biệt cho biên.

## 9. Độ rộng và hình dạng dữ liệu

Nếu production có độ dài chuỗi phân bố lệch, test nên giữ phân phối đó. Ví dụ cột description có p50 40 ký tự, p95 500 ký tự và p99 4.000 ký tự. Sinh mọi description bằng chuỗi 20 ký tự sẽ làm row size và page density sai khác.

Với JSON:

- Số field và độ sâu lồng nhau.
- Tỷ lệ field có mặt/thiếu.
- Kiểu dữ liệu của từng field.
- Độ dài string và số phần tử array.
- Tỷ lệ truy vấn filter trên JSON path.

Với binary/LOB:

- Kích thước payload.
- Tỷ lệ NULL.
- Tỷ lệ đọc payload so với chỉ đọc metadata.
- Cách DBMS lưu inline/off-row.
- Compression và encoding.

Không cần tạo nội dung payload có ý nghĩa thật nếu benchmark chỉ quan tâm kích thước. Có thể dùng nội dung tổng hợp an toàn nhưng giữ độ dài và cấu trúc gần profile.

## 10. Quan hệ giữa các bảng và cardinality của JOIN

Dữ liệu quan hệ phải giữ đúng hình dạng liên kết. Một bảng con tạo độc lập không tham chiếu hợp lệ tới bảng cha có thể làm join trả về ít hoặc không có hàng, khiến benchmark sai.

Các quan hệ phổ biến:

- One-to-one: mỗi hàng cha có tối đa một hàng con.
- One-to-many: một hàng cha có nhiều hàng con.
- Many-to-many: hai thực thể liên kết qua bảng junction.
- Optional relationship: một phần hàng không có hàng con.
- Hierarchical relationship: cây hoặc đồ thị cha-con.

### 10.1. Phân phối số hàng con trên mỗi hàng cha

Không chỉ cần biết trung bình. Giả sử trung bình một order có 4 items, nhưng phân phối là:

- 50% orders có 1–2 items.
- 35% có 3–6 items.
- 13% có 7–20 items.
- 2% có 21–100 items.

Nếu generator tạo đúng 4 items cho mọi order, nó không mô phỏng được order lớn và fan-out ở p99.

### 10.2. Fan-out của JOIN

Một JOIN có thể nhân số hàng. Ví dụ, một customer có 10 orders và mỗi order có 4 items; join customer → orders → order_items có thể tạo khoảng 40 hàng cho customer đó.

Nếu test chỉ tạo một order và một item mỗi customer, chi phí JOIN, sort, aggregate và memory sẽ thấp hơn nhiều.

Hãy mô phỏng:

- Tỷ lệ cha không có con.
- Số con trung bình, median, p95, p99.
- Các cha có số con cực lớn.
- Phân phối quan hệ theo tenant/region/time.
- Tỷ lệ orphan nếu hệ thống thực tế cho phép hoặc đang cần kiểm tra lỗi dữ liệu.

Với dữ liệu production hợp lệ, orphan thường phải bằng 0. Có thể tạo một dataset lỗi riêng để kiểm thử quy trình phát hiện dữ liệu không hợp lệ, nhưng không trộn vào benchmark chuẩn nếu production không có đặc tính đó.

### 10.3. Many-to-many

Bảng junction cần giữ:

- Số liên kết trung bình mỗi thực thể.
- Phân phối độ degree của từng phía.
- Tỷ lệ liên kết trùng nếu schema cho phép.
- Các thực thể có degree cao (hub).
- Tính duy nhất của cặp khóa nếu nghiệp vụ yêu cầu.

Đồ thị quan hệ có hub lớn có thể tạo hotspot khi JOIN hoặc cập nhật bảng junction.

## 11. Khóa chính, khóa ngoại và thứ tự sinh dữ liệu

Để dữ liệu có quan hệ hợp lệ, generator cần tạo theo dependency:

1. Tạo thực thể cha.
2. Lưu tập khóa cha hoặc quy tắc sinh khóa xác định.
3. Tạo thực thể con tham chiếu khóa cha hợp lệ.
4. Tạo bảng junction sau khi có cả hai phía.
5. Kiểm tra foreign key và uniqueness.

Ví dụ:

~~~text
customers
   |
   +---- orders
              |
              +---- order_items
              |
              +---- payments
~~~

Nếu khóa được sinh ngẫu nhiên, cần có mapping để con tham chiếu đúng cha. Nếu dùng dải ID xác định, có thể tính foreign key từ ID cha nhưng phải bảo đảm ID nằm trong miền đã sinh.

Không tắt foreign key checks chỉ để tăng tốc rồi quên xác minh. Nếu cần nạp nhanh bằng staging hoặc bulk load, phải có bước kiểm tra quan hệ và bật lại constraint theo đúng quy trình của DBMS.

## 12. Tạo dữ liệu tổng hợp có thể tái lập

Benchmark cần có khả năng chạy lại. Nếu mỗi lần sinh dữ liệu có phân bố hoàn toàn khác, khó so sánh execution plan và latency trước/sau thay đổi.

### 12.1. Seed cố định

Seed cố định cho bộ sinh số ngẫu nhiên giúp tái tạo cùng một tập dữ liệu hoặc cùng chuỗi lựa chọn. Lưu seed cùng cấu hình generator.

Tuy nhiên, chỉ lưu seed chưa đủ nếu:

- Phiên bản thư viện random thay đổi.
- Thứ tự worker song song thay đổi.
- Generator đổi logic.
- Thứ tự dữ liệu đầu vào khác.

Hãy lưu cả version generator, schema version, profile version, seed, scale factor và tham số môi trường.

### 12.2. Sinh xác định theo ID

Một cách khác là tạo giá trị từ khóa chính bằng hàm hash hoặc phép biến đổi xác định. Cùng ID sẽ sinh cùng region/status/date, giúp chạy lại từng batch mà không cần lưu toàn bộ kết quả random.

Khi dùng hash, hãy kiểm tra phân bố và độ ổn định của hàm trong môi trường. Không dùng hash không có kiểm chứng như cơ chế bảo đảm uniqueness.

### 12.3. Idempotent generator

Generator idempotent có thể chạy lại mà không tạo bản ghi trùng hoặc làm sai dữ liệu:

- Dùng khóa xác định.
- Chia batch theo dải ID.
- Có manifest/checkpoint.
- Dùng staging và upsert với quy tắc rõ.
- Xác minh batch đã tồn tại trước khi ghi lại.

Điều này giúp tiếp tục sau lỗi và tạo dataset có thể tái lập.

## 13. Ví dụ sinh dữ liệu quan hệ bằng PostgreSQL

Ví dụ sau minh họa tạo customers và orders với ID xác định, phân bố region không đều và quan hệ foreign key hợp lệ. Các số lượng và tỷ lệ chỉ là dữ liệu thử nghiệm.

~~~sql
CREATE TABLE test_customers (
    customer_id BIGINT PRIMARY KEY,
    region_code TEXT NOT NULL,
    customer_tier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO test_customers (
    customer_id, region_code, customer_tier, created_at
)
SELECT
    g AS customer_id,
    CASE
        WHEN mod(abs(hashint8(g)::bigint), 100) < 55 THEN 'NORTH'
        WHEN mod(abs(hashint8(g)::bigint), 100) < 85 THEN 'SOUTH'
        ELSE 'CENTRAL'
    END AS region_code,
    CASE
        WHEN mod(abs(hashint8(g + 17)::bigint), 100) < 5 THEN 'GOLD'
        WHEN mod(abs(hashint8(g + 17)::bigint), 100) < 25 THEN 'SILVER'
        ELSE 'STANDARD'
    END AS customer_tier,
    TIMESTAMPTZ '2024-01-01 00:00:00+00'
        + (mod(abs(hashint8(g + 31)::bigint), 730)) * INTERVAL '1 day'
FROM generate_series(1, 1000000) AS g;

CREATE TABLE test_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES test_customers(customer_id),
    status TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

INSERT INTO test_orders (
    order_id, customer_id, status, total_amount, created_at
)
SELECT
    g AS order_id,
    CASE
        WHEN mod(abs(hashint8(g)::bigint), 100) < 20
            THEN 1 + mod(g, 20)
        ELSE 1 + mod(abs(hashint8(g + 101)::bigint), 1000000)
    END AS customer_id,
    CASE
        WHEN mod(abs(hashint8(g + 211)::bigint), 100) < 70 THEN 'COMPLETED'
        WHEN mod(abs(hashint8(g + 211)::bigint), 100) < 85 THEN 'PENDING'
        WHEN mod(abs(hashint8(g + 211)::bigint), 100) < 95 THEN 'CANCELLED'
        ELSE 'REFUNDED'
    END AS status,
    (10 + mod(abs(hashint8(g + 307)::bigint), 500000) / 100.0)::numeric(14, 2),
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
        + mod(abs(hashint8(g + 401)::bigint), 365) * INTERVAL '1 day'
FROM generate_series(1, 10000000) AS g;

ANALYZE test_customers;
ANALYZE test_orders;
~~~

Ví dụ sử dụng hash để sinh giá trị xác định theo ID. Một phần orders được gán vào 20 customer đầu để tạo nhóm key nóng; phần còn lại được phân phối trên tập customer lớn. Cách sinh này chỉ mô phỏng một dạng skew đơn giản, không thay thế profile thực tế. Cần xác minh tỷ lệ thực sau khi nạp.

Lưu ý về tính portable: hash function và kiểu dữ liệu trong ví dụ là của PostgreSQL. Khi thay đổi DBMS hoặc phiên bản, cần dùng hàm tương đương và kiểm tra miền giá trị. Với dữ liệu lớn, nên nạp theo batch và theo dõi WAL, thời gian index build, I/O và replication.

## 14. Ví dụ tạo quan hệ one-to-many với fan-out lệch

Giả sử cần tạo order_items với số item khác nhau cho từng order. Generator có thể dùng một phân phối theo nhóm:

~~~text
for each order:
    bucket = deterministic_hash(order_id) mod 1000

    if bucket < 500:
        item_count = 1 + small_range()
    else if bucket < 850:
        item_count = 3 + medium_range()
    else if bucket < 980:
        item_count = 8 + larger_range()
    else:
        item_count = 25 + long_tail_range()

    create item_count rows referencing this order_id
~~~

Phần 2% cuối tạo order có nhiều item, mô phỏng long tail. Trong triển khai, các hàm small_range/medium_range/long_tail_range cần được định nghĩa theo percentile mục tiêu và seed cố định.

Sau khi sinh, kiểm tra phân phối:

~~~sql
SELECT item_count, COUNT(*) AS orders
FROM (
    SELECT order_id, COUNT(*) AS item_count
    FROM test_order_items
    GROUP BY order_id
) AS per_order
GROUP BY item_count
ORDER BY item_count;
~~~

Có thể dùng percentile_cont để kiểm tra median/p95/p99 nếu DBMS hỗ trợ:

~~~sql
SELECT
    percentile_cont(0.50) WITHIN GROUP (ORDER BY item_count) AS p50,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY item_count) AS p95,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY item_count) AS p99
FROM (
    SELECT order_id, COUNT(*) AS item_count
    FROM test_order_items
    GROUP BY order_id
) AS per_order;
~~~

## 15. Sinh dữ liệu bằng Java hoặc công cụ chuyên dụng

Với schema phức tạp, generator thường nên là chương trình có cấu hình thay vì một câu SQL khổng lồ. Có thể dùng Java với thư viện sinh dữ liệu, custom generator hoặc công cụ benchmark chuyên dụng.

Một generator có cấu trúc:

~~~java
record DataProfile(
        long customerCount,
        long orderCount,
        long seed,
        double hotCustomerRatio,
        double hotOrderShare) {}

interface DeterministicGenerator<T> {
    T generate(long id, long seed);
}

public final class OrderGenerator {
    private final DataProfile profile;

    public OrderGenerator(DataProfile profile) {
        this.profile = profile;
    }

    public GeneratedOrder generate(long orderId) {
        long bucket = stableHash(orderId, profile.seed()) % 10_000;

        long customerId;
        if (bucket < profile.hotOrderShare() * 10_000) {
            customerId = 1 + stableHash(orderId, profile.seed() + 1) % 100;
        } else {
            customerId = 1 + stableHash(orderId, profile.seed() + 2)
                    % profile.customerCount();
        }

        return new GeneratedOrder(
                orderId,
                customerId,
                generateStatus(orderId, profile.seed()),
                generateAmount(orderId, profile.seed()),
                generateTimestamp(orderId, profile.seed()));
    }

    // stableHash và các hàm generate* phải được triển khai
    // với phân phối, miền giá trị và kiểm thử xác định.
}
~~~

Đây là skeleton thiết kế, không phải chương trình hoàn chỉnh. Hàm stableHash cần trả giá trị không âm hoặc được chuẩn hóa an toàn; phần chia modulo cần tránh lỗi overflow và phải bảo đảm customerId nằm trong miền đã tạo.

### 15.1. Batch insert

Không nhất thiết insert từng hàng một. Có thể dùng:

- JDBC batch.
- Multi-row INSERT.
- COPY/bulk load của DBMS.
- File staging rồi nạp bằng công cụ native.

Chọn batch size theo độ rộng hàng, index, transaction log và replication. Quá nhiều worker có thể gây lock contention hoặc làm I/O bão hòa; hãy đo thay vì tăng concurrency không giới hạn.

### 15.2. Tách generator khỏi workload driver

Generator tạo dataset ban đầu; workload driver phát truy vấn/transaction theo phân phối mục tiêu. Hai thành phần cần dùng chung profile nhưng không nên đồng nhất:

- Dataset generator quyết định dữ liệu nào tồn tại.
- Workload driver quyết định dữ liệu nào được truy cập, tần suất và thứ tự ra sao.

Một dataset có phân bố đúng nhưng workload chỉ truy cập key đều vẫn không mô phỏng hot-key traffic. Ngược lại, workload truy cập Zipf trên dataset chỉ có 100 key không đại diện hệ thống có hàng triệu key.

## 16. Dữ liệu tổng hợp và bảo vệ dữ liệu nhạy cảm

Không sao chép trực tiếp PII, thông tin thanh toán, token, password, secret hoặc dữ liệu khách hàng thật vào môi trường kiểm thử nếu không có cơ sở và quy trình được phê duyệt.

Các cách tạo dữ liệu an toàn:

- Sinh tên, email, địa chỉ và số điện thoại giả.
- Dùng giá trị định danh không thể gửi nhầm tới khách hàng thật.
- Giữ phân phối và quan hệ nhưng thay nội dung bằng synthetic value.
- Tokenize hoặc pseudonymize dữ liệu theo quy trình có kiểm soát nếu cần giữ liên kết.
- Tổng hợp histogram và percentile thay vì xuất hàng thật.
- Xóa secret, credential, access token và dữ liệu xác thực.

Masking không đồng nghĩa dữ liệu đã vô danh. Một tập dữ liệu vẫn có thể nhận diện cá nhân qua tổ hợp thuộc tính hiếm. Nếu cần dùng dữ liệu dẫn xuất từ production, phải đánh giá quyền truy cập, mục đích sử dụng và nguy cơ tái nhận diện theo chính sách tổ chức.

Đối với benchmark, thường chỉ cần giữ hình dạng thống kê và quan hệ nghiệp vụ, không cần nội dung định danh thật.

## 17. Giữ dữ liệu kiểm thử đúng theo schema và constraint

Generator cần biết:

- Primary key và unique constraint.
- Foreign key và thứ tự phụ thuộc bảng.
- NOT NULL và default.
- Check constraint.
- Enum/domain và giá trị hợp lệ.
- Precision/scale của DECIMAL.
- Collation và encoding.
- Generated column hoặc computed column.
- Trigger và cascade behavior.

Nếu generator tạo giá trị ngoài miền, insert có thể thất bại hoặc test phải tắt constraint. Nếu tắt constraint, cần chạy kiểm tra toàn vẹn trước khi benchmark.

### 17.1. Referential integrity

Kiểm tra không có hàng con mồ côi:

~~~sql
SELECT COUNT(*) AS orphan_orders
FROM test_orders o
LEFT JOIN test_customers c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Kết quả phải bằng 0 nếu quan hệ là bắt buộc và constraint đang được yêu cầu.

### 17.2. Uniqueness

~~~sql
SELECT order_id, COUNT(*)
FROM test_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Truy vấn không được trả về nhóm nào nếu order_id phải duy nhất.

### 17.3. Quan hệ và fan-out

~~~sql
SELECT
    COUNT(*) AS order_count,
    AVG(item_count) AS avg_items,
    MAX(item_count) AS max_items
FROM (
    SELECT order_id, COUNT(*) AS item_count
    FROM test_order_items
    GROUP BY order_id
) x;
~~~

Đối chiếu median, p95, p99 và tỷ lệ order không có item với profile mong muốn.

## 18. Thống kê optimizer sau khi sinh dữ liệu

Dữ liệu đã nạp nhưng thống kê chưa được cập nhật có thể khiến optimizer chọn execution plan dựa trên thông tin cũ hoặc mặc định.

Sau khi nạp hoặc thay đổi lớn:

- Cập nhật statistics theo cơ chế DBMS.
- Kiểm tra row count, NDV, histogram và MCV.
- Kiểm tra correlation giữa các cột nếu hệ quản trị hỗ trợ extended statistics.
- Xem estimated rows so với actual rows.
- Kiểm tra plan cho cả key phổ biến và key hiếm.

Ví dụ PostgreSQL:

~~~sql
ANALYZE test_customers;
ANALYZE test_orders;
~~~

Với SQL Server, cập nhật statistics theo chiến lược phù hợp; với MySQL, xem histogram và persistent statistics; với Oracle, dùng DBMS_STATS theo chính sách. Không chạy lệnh statistics một cách máy móc trên production mà không đánh giá tác động và cơ chế tự động của DBMS.

### 18.1. So sánh estimated rows và actual rows

Nếu optimizer ước lượng 100 hàng nhưng thực tế trả về 2 triệu, sai số cardinality lớn có thể dẫn tới:

- Chọn nested loop thay vì hash join.
- Chọn index lookup quá nhiều lần.
- Cấp memory grant không đủ hoặc quá lớn.
- Chọn thứ tự JOIN kém.
- Chọn scan/seek không phù hợp.

Một bộ dữ liệu đại diện cần tạo ra cả các trường hợp selectivity phổ biến và hiếm để kiểm tra chất lượng estimate.

## 19. Kiểm tra phân phối sau khi sinh

Không tin rằng generator đúng chỉ vì code trông hợp lý. Hãy đo dữ liệu đã ghi vào database.

Các kiểm tra:

| Đặc tính | Cách xác minh |
|---|---|
| Row count | COUNT(*) theo bảng và partition |
| NDV | COUNT(DISTINCT column) hoặc thống kê DBMS |
| Tỷ lệ nhóm | GROUP BY category/status/region |
| Skew | Top-N frequency, histogram và tỷ lệ heavy hitters |
| Độ rộng | OCTET_LENGTH, percentile độ dài hoặc storage metrics |
| NULL rate | COUNT(*) FILTER hoặc SUM(CASE...) |
| Quan hệ | Số hàng con/cha, orphan count, duplicate key |
| Thời gian | Histogram theo ngày/giờ và tỷ lệ late arrival |
| Tương quan | Cross-tab, conditional distribution hoặc correlation |
| Working set | Tần suất truy cập key theo workload driver |

### 19.1. Đo heavy hitters

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM test_orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 20;
~~~

Kiểm tra tỷ lệ tổng orders do top 1%, top 10 hoặc top tenant tạo ra. Một vài key đứng đầu cần có tần suất gần profile mục tiêu.

### 19.2. Đo tỷ lệ NULL

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN coupon_code IS NULL THEN 1 ELSE 0 END) AS null_rows
FROM test_orders;
~~~

Tỷ lệ NULL bằng null_rows / total_rows. Có thể nhóm theo region hoặc status nếu tỷ lệ NULL phụ thuộc các thuộc tính đó.

### 19.3. Đo tương quan theo nhóm

~~~sql
SELECT region_code, currency_code, COUNT(*) AS rows
FROM test_customers
GROUP BY region_code, currency_code
ORDER BY region_code, rows DESC;
~~~

Cross-tab giúp phát hiện generator tạo các tổ hợp không giống profile.

## 20. Dữ liệu cho từng loại kiểm thử

### 20.1. Kiểm thử index và point lookup

Cần:

- Cardinality của key gần production.
- Tỷ lệ hit/miss.
- Heavy hitters và key hiếm.
- Working set nóng/lạnh.
- Độ rộng row và index key.
- Các truy vấn theo prefix hoặc range nếu có.

### 20.2. Kiểm thử JOIN

Cần:

- Cardinality của từng bảng.
- Tỷ lệ quan hệ 1:1, 1:N, N:M.
- Fan-out trung bình và long tail.
- Orphan/optional relationship theo quy tắc dữ liệu.
- Tương quan giữa join key và filter.
- Phân phối dữ liệu lệch theo tenant hoặc partition.

### 20.3. Kiểm thử aggregate và báo cáo

Cần:

- Số nhóm sau GROUP BY.
- Phân bố kích thước nhóm.
- Cardinality của dimensions.
- Tỷ lệ dữ liệu theo thời gian.
- Heavy hitters và nhóm rỗng.
- Độ rộng measure và số lượng distinct.

### 20.4. Kiểm thử ghi và concurrency

Cần:

- Insert key tuần tự hay ngẫu nhiên.
- Update hot rows/hot keys.
- Tỷ lệ update/delete.
- Transaction size.
- Tỷ lệ tranh chấp theo key/partition.
- Số worker và tốc độ sinh log.
- Dữ liệu cần cập nhật đồng thời bởi nhiều session.

### 20.5. Kiểm thử partitioning và retention

Cần:

- Nhiều partition với kích thước thực tế.
- Phân phối dữ liệu qua boundary.
- Truy vấn chỉ đọc một partition và truy vấn xuyên partition.
- Late-arriving data và correction lịch sử.
- Partition mới, partition rỗng và partition gần đầy.
- Tác vụ detach/drop/archive nếu nằm trong phạm vi test.

## 21. Quy trình tạo dataset benchmark

1. **Xác định workload mục tiêu.** Liệt kê query, transaction, tần suất, latency và SLO.
2. **Thu thập profile an toàn.** Dùng row count, histogram, NDV, percentile, join cardinality và access frequency đã tổng hợp.
3. **Chọn scale factor.** Tạo mức nhỏ để phát triển generator và các mức gần/vượt production để benchmark.
4. **Định nghĩa schema dependency.** Lập thứ tự sinh bảng cha, bảng con và junction.
5. **Định nghĩa phân phối.** Chọn uniform, skew, weighted categorical, long-tail, temporal và conditional distributions.
6. **Định nghĩa quan hệ.** Giữ PK/FK, fan-out, optional relationship và các ràng buộc nghiệp vụ.
7. **Cố định seed và version.** Lưu cấu hình, generator version, schema version và seed.
8. **Sinh theo batch.** Giới hạn transaction size, worker và tốc độ nạp.
9. **Xác minh dữ liệu.** Đo row count, NDV, histogram, NULL rate, row width, skew và orphan.
10. **Cập nhật statistics.** Chạy cơ chế analyze/statistics phù hợp với DBMS.
11. **Chạy workload driver.** Dùng phân phối truy cập tương ứng dataset; kiểm tra cả key nóng và hiếm.
12. **Lưu manifest.** Ghi profile, scale, seed, thời điểm, phiên bản schema, số hàng và checksum.
13. **Tái tạo và so sánh.** Dùng cùng manifest cho benchmark trước/sau thay đổi.

## 22. Manifest cho khả năng tái lập

Một manifest có thể lưu:

~~~yaml
dataset:
  name: orders-oltp-profile
  profile_version: 3
  generator_version: 2.4.0
  seed: 481516
  scale_factor: 2
  schema_version: 17
  created_at: 2026-11-19T10:00:00Z
tables:
  customers:
    rows: 2000000
  orders:
    rows: 20000000
  order_items:
    rows: 80000000
distributions:
  hot_customer_share: 0.20
  hot_order_share: 0.18
  recent_14_day_share: 0.35
validation:
  foreign_key_violations: 0
  duplicate_primary_keys: 0
~~~

Đây là ví dụ mô tả, các giá trị phải được lấy từ lần sinh thực tế. Manifest giúp biết chính xác dataset nào đã được dùng cho một kết quả benchmark.

## 23. Những sai lầm thường gặp

- **Chỉ khớp số hàng.** Độ rộng, index, cardinality và quan hệ có thể khác rất xa.
- **Sinh dữ liệu hoàn toàn uniform.** Bỏ qua hot key, heavy hitters và long tail.
- **Sinh các cột độc lập.** Mất tương quan nghiệp vụ và làm optimizer ước lượng khác.
- **Tạo bảng con không có quan hệ hợp lệ.** JOIN fan-out và số hàng kết quả sai.
- **Dùng trung bình thay cho phân phối.** p95/p99 và nhóm ngoại lệ biến mất.
- **Chỉ sinh dữ liệu mới.** Không kiểm tra lịch sử, late arrival, retention và partition boundary.
- **Dùng một seed nhưng không lưu version generator.** Thay đổi code có thể tạo dataset khác dù seed không đổi.
- **Chỉ kiểm tra generator, không kiểm tra dữ liệu sau load.** Constraint, casting hoặc batch lỗi có thể làm phân bố sai.
- **Quên cập nhật statistics.** Optimizer dùng estimate không phù hợp với dataset mới.
- **Chỉ benchmark một query.** Không phản ánh workload hỗn hợp và concurrency.
- **Sao chép dữ liệu thật không kiểm soát.** Có thể đưa PII hoặc secret vào môi trường test.
- **Tắt constraint để nạp nhanh rồi bỏ qua kiểm tra.** Dữ liệu mồ côi hoặc duplicate có thể làm benchmark sai.
- **Dùng dataset nhỏ hơn cache để kết luận về I/O.** Không mô phỏng được working set lớn.
- **Không lưu manifest.** Không thể tái lập hoặc so sánh công bằng giữa các lần đo.

## 24. Checklist dữ liệu đại diện

- [ ] Mục tiêu benchmark và workload được xác định rõ.
- [ ] Row count và tổng dung lượng bảng/index gần scale mục tiêu.
- [ ] Độ rộng hàng và phân phối payload được mô phỏng.
- [ ] NDV và cardinality từng cột quan trọng được giữ gần profile.
- [ ] Skew, heavy hitters và long tail được mô phỏng.
- [ ] Tương quan giữa các cột và tổ hợp phổ biến/hiếm được giữ.
- [ ] Tỷ lệ NULL, giá trị biên và ngoại lệ được xác định.
- [ ] Phân phối thời gian, hot/cold window và late arrival được mô phỏng.
- [ ] Quan hệ PK/FK, one-to-many, many-to-many và fan-out được giữ.
- [ ] Dataset có working set phù hợp với mục tiêu cache/I/O.
- [ ] Generator có seed, version và cấu hình có thể tái lập.
- [ ] Dữ liệu tổng hợp không chứa PII/secret thật ngoài phạm vi được phép.
- [ ] Đã kiểm tra row count, NDV, histogram, NULL rate, độ rộng và skew sau load.
- [ ] Đã kiểm tra foreign key, uniqueness và số hàng con/cha.
- [ ] Đã cập nhật statistics trước khi đọc execution plan.
- [ ] Workload driver truy cập key theo phân phối tương ứng.
- [ ] Đã lưu manifest để tái tạo dataset và benchmark.

Dữ liệu kiểm thử đại diện phải tái tạo được hình dạng mà DBMS nhìn thấy: quy mô, độ rộng, cardinality, skew, tương quan, thời gian và quan hệ giữa các bảng. Số hàng bằng production chưa đủ nếu mọi key được phân phối đều, mọi hàng có độ rộng giống nhau hoặc quan hệ JOIN bị đơn giản hóa. Hãy bắt đầu từ profile workload đã tổng hợp an toàn, sinh dữ liệu có seed và dependency rõ ràng, đo lại phân phối sau khi nạp, cập nhật statistics rồi chạy workload với cùng cách truy cập. Khi dữ liệu có thể tái lập và phản ánh đúng các đặc tính quan trọng, kết quả benchmark mới có giá trị để so sánh execution plan, index, concurrency và năng lực hệ thống.
