# Tối ưu truy vấn từ slow log đến kế hoạch và lựa chọn chỉ mục

Tối ưu truy vấn MySQL cần bắt đầu từ workload thật, đi qua chẩn đoán và kết thúc bằng đo lường sau thay đổi. Một truy vấn chậm trong log có thể là nguyên nhân chính, nhưng cũng có thể chỉ là triệu chứng của lock wait, thiếu tài nguyên, dữ liệu tăng trưởng hoặc kế hoạch thực thi không phù hợp. Thêm index ngay khi thấy một câu SELECT chậm dễ làm tăng dung lượng và chi phí ghi mà không giải quyết được nguyên nhân.

Bài thực hành này đưa bạn qua một quy trình hoàn chỉnh: thu thập slow query log, nhóm truy vấn theo digest, chọn workload ưu tiên, đọc execution plan, nhận diện điểm nghẽn, viết lại SQL khi cần, thiết kế chỉ mục phù hợp và so sánh kết quả trước/sau. Mục tiêu là cải thiện latency và lượng công việc MySQL phải thực hiện trong khi vẫn giữ đúng kết quả nghiệp vụ và kiểm soát tác động lên ghi, transaction, replication.

Trong phạm vi **DATABASE_MYSQL**, quy trình kết hợp thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction và kiểm soát đồng thời. Bạn cũng sẽ thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ.

## 1. Mục tiêu và quy trình tổng thể

Sau bài học, bạn có thể:

- Bật và cấu hình slow query log có kiểm soát.
- Dùng digest và thống kê để tìm nhóm truy vấn tạo tải lớn.
- Đọc EXPLAIN và EXPLAIN ANALYZE để hiểu cách MySQL truy cập dữ liệu.
- Nhận diện table scan, sort, temporary table, lock wait và ước lượng sai cardinality.
- Viết lại predicate để truy vấn có thể sử dụng index hiệu quả.
- Thiết kế composite index và covering index dựa trên điều kiện lọc, thứ tự sắp xếp và cột trả về.
- Đánh giá chi phí của index với INSERT, UPDATE, DELETE, dung lượng và replication.
- Triển khai thay đổi có kiểm soát, so sánh kết quả trước/sau và lưu bằng chứng.

Quy trình thực hành:

~~~mermaid
flowchart TD
    A[Thu thập slow log và metrics] --> B[Nhóm truy vấn theo digest]
    B --> C[Chọn workload ưu tiên]
    C --> D[Tái hiện với tham số đại diện]
    D --> E[Đọc EXPLAIN / EXPLAIN ANALYZE]
    E --> F{Nguyên nhân chính?}
    F -->|Predicate không SARGable| G[Viết lại SQL]
    F -->|Thiếu hoặc sai index| H[Thiết kế index]
    F -->|Lock / transaction| I[Điều tra đồng thời]
    F -->|Ước lượng sai| J[Kiểm tra statistics]
    G --> K[Đo trước/sau và xác minh kết quả]
    H --> K
    I --> K
    J --> K
    K --> L[Triển khai có kiểm soát và theo dõi]
~~~

Không bắt đầu bằng câu hỏi “nên thêm index nào?”. Hãy bắt đầu bằng “truy vấn nào đang tiêu tốn nhiều tài nguyên, nó làm bao nhiêu công việc và vì sao?”.

## 2. Thu thập slow query log

### 2.1. Slow query log cho biết điều gì?

Slow query log ghi lại các câu lệnh vượt ngưỡng thời gian đã cấu hình và một số nhóm truy vấn theo các tùy chọn bổ sung. Tùy cấu hình và phiên bản, bản ghi có thể cho biết:

- Thời gian thực thi (Query_time).
- Thời gian chờ lock (Lock_time).
- Số hàng trả về (Rows_sent).
- Số hàng đã kiểm tra (Rows_examined).
- Timestamp, user/host và câu SQL.

Rows_examined cao trong khi Rows_sent thấp thường là tín hiệu truy vấn phải đọc nhiều hàng để tìm ít kết quả. Tuy vậy, đây không phải kết luận cuối cùng: truy vấn có thể cần quét nhiều hàng theo đúng yêu cầu, hoặc bị ảnh hưởng bởi phân bố dữ liệu, cache, lock và tải đồng thời.

Một truy vấn mất 300 ms nhưng chạy hàng chục nghìn lần mỗi phút có thể gây tổng tải lớn hơn truy vấn 10 giây chỉ chạy một lần mỗi ngày. Vì vậy, cần kết hợp slow log với thống kê tổng hợp theo digest.

### 2.2. Kiểm tra cấu hình hiện tại

~~~sql
SHOW GLOBAL VARIABLES
WHERE Variable_name IN (
  'slow_query_log',
  'slow_query_log_file',
  'long_query_time',
  'min_examined_row_limit',
  'log_output',
  'log_queries_not_using_indexes'
);
~~~

Một số cấu hình có ý nghĩa:

| Biến | Ý nghĩa | Cách dùng |
|---|---|---|
| slow_query_log | Bật/tắt slow query log | Bật trong cửa sổ thu thập phù hợp |
| slow_query_log_file | Đường dẫn file log khi output là FILE | Kiểm tra dung lượng và chính sách rotation |
| long_query_time | Ngưỡng thời gian ghi log, tính bằng giây | Chọn theo latency mục tiêu và mức tải log |
| min_examined_row_limit | Ngưỡng số hàng phải kiểm tra mới ghi log | Có thể giảm log các truy vấn nhỏ |
| log_output | Nơi ghi log: FILE, TABLE hoặc cả hai | Thường dùng FILE cho thu thập vận hành |
| log_queries_not_using_indexes | Ghi thêm truy vấn không dùng index | Có thể tạo log lớn; bật có kiểm soát |

### 2.3. Bật log trong môi trường kiểm thử

Ví dụ đặt ngưỡng 500 ms:

~~~sql
SET GLOBAL slow_query_log = ON;
SET GLOBAL long_query_time = 0.5;
SET GLOBAL min_examined_row_limit = 100;
SET GLOBAL log_output = 'FILE';
~~~

Các thay đổi GLOBAL thường được dùng để khởi tạo giá trị session cho connection mới. Một session hiện tại có thể vẫn giữ giá trị session cũ; nếu cần kiểm tra, xem cả GLOBAL và SESSION.

~~~sql
SELECT
  @@GLOBAL.slow_query_log AS global_slow_log,
  @@SESSION.long_query_time AS session_long_query_time,
  @@GLOBAL.long_query_time AS global_long_query_time;
~~~

Để cấu hình bền vững qua restart, dùng cấu hình server hoặc cơ chế SET PERSIST khi được chính sách vận hành cho phép. Không thay đổi cấu hình production chỉ để thử nghiệm mà chưa đánh giá dung lượng log và tác động hiệu năng.

long_query_time có thể nhận giá trị thập phân. Ngưỡng 0.5 tương đương nửa giây. Ngưỡng quá thấp có thể tạo log rất lớn, đặc biệt với endpoint có tần suất cao. Thu thập trong khoảng thời gian đại diện, rồi tắt hoặc điều chỉnh theo chính sách.

### 2.4. Vì sao không nên bật log mọi truy vấn không dùng index một cách máy móc?

Một số truy vấn hợp lý vẫn có thể không dùng index:

- Bảng rất nhỏ, table scan rẻ hơn index lookup.
- Truy vấn cần đọc phần lớn bảng.
- Index không chọn lọc hoặc chi phí random I/O cao hơn scan.
- Optimizer ước lượng rằng scan sẽ rẻ hơn.
- Truy vấn không có predicate lọc.

log_queries_not_using_indexes có thể tạo rất nhiều log và gây nhiễu. Nếu cần bật, kết hợp giới hạn số hàng, thời gian thu thập và cơ chế throttle phù hợp phiên bản. Không dùng việc “không dùng index” làm tiêu chí duy nhất để đánh dấu truy vấn lỗi.

### 2.5. Bảo vệ slow log

SQL trong log có thể chứa literal nhạy cảm, email, mã khách hàng, token hoặc dữ liệu nghiệp vụ. Hãy:

- Giới hạn quyền đọc file và bảng log.
- Lưu log theo chính sách retention và mã hóa phù hợp.
- Không gửi nguyên slow log vào ticket công khai hoặc chat không được phép.
- Redact giá trị nhạy cảm trước khi chia sẻ.
- Theo dõi dung lượng file và cấu hình rotation.
- Dùng tài khoản có quyền tối thiểu khi truy vấn log trong MySQL.

## 3. Chọn truy vấn cần tối ưu

### 3.1. Không chỉ xếp hạng theo thời gian trung bình

Một nhóm truy vấn có thể đáng ưu tiên vì nhiều lý do:

| Chỉ số | Ý nghĩa | Khi nào đáng chú ý |
|---|---|---|
| Số lần thực thi | Tần suất gọi truy vấn | Một truy vấn vừa chậm vừa chạy rất thường xuyên |
| Tổng thời gian | Tổng latency cộng dồn | Nhóm truy vấn chiếm nhiều thời gian database |
| Thời gian trung bình | Latency trung bình mỗi lần | So sánh hiệu năng trên mỗi lần gọi |
| Thời gian tối đa | Outlier lớn nhất | Phát hiện trường hợp dữ liệu biên hoặc lock |
| Rows examined | Số hàng phải kiểm tra | Quét nhiều dữ liệu để trả ít kết quả |
| Rows sent | Số hàng trả về | Đánh giá tỷ lệ công việc và kết quả |
| Temporary/disk tables | Tạo bảng tạm, có thể tràn đĩa | Sort/group lớn hoặc thiếu index phù hợp |
| Full scan | Quét toàn bảng hoặc toàn index | Cần xác định scan có hợp lý với workload không |

Không có một chỉ số duy nhất đại diện cho “truy vấn tệ nhất”. Xếp hạng theo tổng latency giúp tìm nhóm tiêu tốn tài nguyên lớn; xếp theo số lần thực thi giúp phát hiện truy vấn nhỏ nhưng rất thường xuyên; xếp theo rows examined giúp tìm truy vấn đọc quá nhiều dữ liệu.

### 3.2. Dùng mysqldumpslow

Nếu slow log được ghi ra file, MySQL cung cấp mysqldumpslow để nhóm và rút gọn các truy vấn tương tự:

~~~bash
mysqldumpslow -s t -t 20 /var/log/mysql/mysql-slow.log
~~~

Một số tùy chọn thường dùng:

- -s t: sắp xếp theo tổng thời gian truy vấn của nhóm.
- -s at: sắp xếp theo thời gian truy vấn trung bình của nhóm.
- -s c: sắp xếp theo số lần xuất hiện.
- -s r: sắp xếp theo số hàng trả về trung bình.
- -t 20: hiển thị 20 nhóm đầu.

Kiểm tra mysqldumpslow --help trên máy đang dùng vì các tùy chọn có thể khác theo bản phân phối. Có thể dùng pt-query-digest của Percona để phân tích sâu hơn, nhưng cần tuân thủ quy trình cài đặt và bảo vệ dữ liệu log.

### 3.3. Dùng sys schema và Performance Schema

Nếu statement instrumentation đang bật và digest còn trong bộ nhớ, sys schema cung cấp góc nhìn tổng hợp:

~~~sql
SELECT
  query,
  exec_count,
  total_latency,
  avg_latency,
  max_latency,
  rows_examined,
  rows_examined_avg,
  rows_sent,
  full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

Có thể xếp theo số lần thực thi:

~~~sql
SELECT
  query,
  exec_count,
  avg_latency,
  rows_examined_avg,
  rows_sent_avg
FROM sys.statement_analysis
ORDER BY exec_count DESC
LIMIT 20;
~~~

Digest nhóm các câu SQL có cấu trúc tương tự, thường thay literal bằng placeholder. Ví dụ hai câu truy vấn với account_id=10 và account_id=20 có thể thuộc cùng một digest.

Thống kê Performance Schema có giới hạn bộ nhớ và có thể reset khi MySQL restart hoặc khi summary bị truncate. Đây là số liệu tích lũy trong khoảng quan sát, không phải lịch sử lưu trữ lâu dài. Nếu cần xu hướng theo ngày/tuần, xuất metric sang hệ thống giám sát.

### 3.4. Chọn một truy vấn đại diện

Với mỗi digest được chọn, lưu:

- Câu SQL đầy đủ đã loại bỏ hoặc che giá trị nhạy cảm.
- Schema, bảng và phiên bản ứng dụng gọi truy vấn.
- Tham số đại diện: account nhỏ/lớn, trạng thái phổ biến/hiếm, khoảng thời gian ngắn/dài.
- Số lần thực thi và latency theo percentile nếu có.
- Rows examined, rows sent, full scan và temporary table.
- Thời điểm thu thập, tải hệ thống và trạng thái cache.
- Execution plan hiện tại.

Một truy vấn có thể có kế hoạch tốt với account nhỏ nhưng rất kém với account lớn. Đừng chỉ thử một bộ tham số thuận lợi.

## 4. Đọc execution plan bằng EXPLAIN

### 4.1. EXPLAIN cơ bản

Ví dụ:

~~~sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Các cột quan trọng trong output dạng tabular:

| Cột | Cách đọc |
|---|---|
| id | Thứ tự/nhóm SELECT trong kế hoạch |
| select_type | Loại SELECT như SIMPLE, PRIMARY, SUBQUERY |
| table | Bảng hoặc derived table đang được đọc |
| type | Kiểu truy cập: ALL, index, range, ref, eq_ref, const... |
| possible_keys | Các index optimizer có thể cân nhắc |
| key | Index optimizer thực sự chọn |
| key_len | Độ dài phần index được sử dụng |
| ref | Cột/giá trị được dùng để so khớp |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ hàng ước lượng còn lại sau điều kiện |
| Extra | Thông tin như Using filesort, Using temporary, Using index |

### 4.2. Hiểu access type

Một số access type thường gặp, từ truy cập có tính chọn lọc cao đến scan rộng:

- **const:** bảng được đọc như một hàng hằng, thường qua khóa chính/unique với điều kiện hằng.
- **eq_ref:** mỗi tổ hợp hàng từ bảng trước khớp tối đa một hàng qua unique/primary key.
- **ref:** truy cập qua index với giá trị so khớp; có thể trả về nhiều hàng.
- **range:** đọc một hoặc nhiều khoảng của index.
- **index:** quét toàn bộ index; có thể rẻ hơn quét bảng nếu index nhỏ hoặc covering, nhưng vẫn là scan.
- **ALL:** quét toàn bảng.

Không kết luận ALL luôn sai hoặc ref luôn tốt. Bảng nhỏ có thể scan nhanh hơn; một index không chọn lọc có thể làm nhiều random lookup. Cần so sánh số hàng thực tế, kích thước dữ liệu và latency.

### 4.3. Đọc key, rows và Extra

- possible_keys có index nhưng key là NULL: optimizer không chọn index đó. Có thể do predicate không phù hợp, index kém chọn lọc, kiểu dữ liệu không khớp hoặc ước lượng chi phí.
- rows lớn: optimizer dự đoán phải đọc nhiều hàng. So sánh với số hàng thực tế.
- Using filesort: MySQL cần bước sort riêng; không có nghĩa chắc chắn đã ghi ra đĩa.
- Using temporary: cần temporary table cho một phần xử lý; xem kích thước và khả năng tràn disk.
- Using index: truy vấn có thể lấy đủ dữ liệu từ index (covering access).
- Using index condition: Index Condition Pushdown giúp kiểm tra một phần điều kiện ngay trong quá trình đọc index.

Using filesort hoặc Using temporary là tín hiệu cần điều tra, không tự động là lỗi. Một truy vấn top-N có thể cần sort hợp lý nếu tập đầu vào nhỏ.

### 4.4. Xem dạng cây

MySQL hỗ trợ dạng cây:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Dạng cây thể hiện thứ tự các iterator và quan hệ giữa scan, filter, sort, join. Khi truy vấn có nhiều bảng, đọc từ các node lá (nguồn dữ liệu) lên node gốc (kết quả) để hiểu cách MySQL kết hợp dữ liệu.

### 4.5. EXPLAIN ANALYZE

EXPLAIN ANALYZE thực thi câu SELECT và báo thời gian/rows thực tế của các iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Output có thể cho biết:

- actual time: thời gian thực tế để iterator tạo hàng đầu tiên và hoàn tất.
- rows: số hàng thực tế iterator trả về.
- loops: số lần iterator được gọi.
- Estimated rows và actual rows có chênh lệch lớn hay không.

EXPLAIN ANALYZE thực thi câu truy vấn. Chỉ dùng với SELECT an toàn, giới hạn phạm vi và chạy trong môi trường phù hợp; một SELECT vẫn có thể tiêu tốn CPU/I/O lớn hoặc giữ snapshot lâu. Không chạy truy vấn tải nặng tùy tiện trên production đang quá tải.

Nếu estimated rows khác xa actual rows, xem xét statistics, histogram, độ lệch phân bố và tham số truy vấn. Sai ước lượng có thể khiến optimizer chọn sai join order hoặc access path.

## 5. Phân tích truy vấn mẫu

### 5.1. Schema và workload

Giả sử hệ thống có bảng đơn hàng:

~~~sql
CREATE TABLE appdb.orders (
  order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  account_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16) NOT NULL,
  created_at DATETIME(6) NOT NULL,
  total_amount DECIMAL(13,2) NOT NULL,
  PRIMARY KEY (order_id),
  KEY idx_orders_account_created (account_id, created_at)
) ENGINE=InnoDB;
~~~

Endpoint báo cáo lấy 50 đơn hàng gần nhất của một account, theo trạng thái và khoảng thời gian:

~~~sql
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Index hiện tại là (account_id, created_at). MySQL có thể dùng phần account_id và khoảng created_at, nhưng phải lọc status sau khi đọc các ứng viên. Nếu account có nhiều đơn trong tháng nhưng chỉ một phần nhỏ ở trạng thái PAID, lượng hàng phải kiểm tra có thể lớn.

Đây là giả thuyết từ cấu trúc schema. Phải xác nhận bằng slow log, EXPLAIN và dữ liệu thật trước khi thay đổi.

### 5.2. Đặt giả thuyết trước khi thêm index

Các câu hỏi:

1. Bao nhiêu hàng thuộc một account?
2. Tỷ lệ trạng thái PAID là bao nhiêu?
3. Khoảng thời gian lọc trả về bao nhiêu hàng?
4. Query có phải sort thêm sau khi lọc không?
5. Truy vấn có chạy thường xuyên và ảnh hưởng latency endpoint không?
6. Có query khác sử dụng index hiện tại không?

Giả thuyết: composite index bắt đầu bằng account_id, tiếp theo là status, sau đó created_at sẽ lọc hai điều kiện equality trước khi đọc range theo thời gian.

### 5.3. Thiết kế composite index

Index ứng viên:

~~~sql
CREATE INDEX idx_orders_account_status_created
ON appdb.orders (account_id, status, created_at);
~~~

Lý do chọn thứ tự:

- account_id có điều kiện equality.
- status có điều kiện equality.
- created_at là điều kiện range và thứ tự sắp xếp.
- Với hai cột đầu đã cố định, index có thể đọc theo thứ tự created_at để hỗ trợ ORDER BY created_at DESC.

Composite index (a,b,c) thường hỗ trợ truy vấn dùng tiền tố trái như (a), (a,b) hoặc (a,b,c). Nó không tự động thay thế index chỉ có (b) hoặc (c). Cần xem toàn bộ workload trước khi xóa index cũ.

### 5.4. Covering index có đáng không?

Truy vấn trả về order_id, created_at, total_amount. Trong InnoDB, secondary index lưu thêm primary key làm phần định vị hàng. Vì vậy index (account_id,status,created_at) có thể cung cấp order_id và các cột index, nhưng total_amount vẫn cần đọc từ clustered index.

Một ứng viên covering:

~~~sql
CREATE INDEX idx_orders_account_status_created_amount
ON appdb.orders (account_id, status, created_at, total_amount);
~~~

Index này có thể cho phép truy vấn lấy toàn bộ cột cần thiết từ secondary index, giảm lần truy cập clustered index. Tuy nhiên:

- Index lớn hơn, chiếm thêm buffer pool và storage.
- INSERT phải cập nhật index.
- UPDATE total_amount, status, account_id hoặc created_at có thể phải cập nhật index.
- Backup và replication có thể chịu thêm chi phí gián tiếp.
- Nếu truy vấn không đủ thường xuyên hoặc bảng ghi nhiều, lợi ích đọc có thể không bù chi phí.

Không tạo cả hai index ứng viên cùng lúc mà không có lý do. So sánh từng lựa chọn trên workload đại diện.

### 5.5. Kiểm tra truy vấn sau index

Sau khi tạo index trên môi trường thử nghiệm:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
  AND created_at >= '2026-10-01 00:00:00'
  AND created_at <  '2026-11-01 00:00:00'
ORDER BY created_at DESC
LIMIT 50;
~~~

Đối chiếu:

- key có chọn index mới không?
- Estimated rows và actual rows thay đổi thế nào?
- Có còn filter nhiều hàng sau khi đọc index không?
- Có còn sort riêng hay không?
- Using index xuất hiện với covering index không?
- Latency và CPU/I/O có giảm trong workload thật không?

Không tự đặt số liệu cải thiện khi chưa chạy benchmark. Ghi lại kết quả thực tế cùng phiên bản MySQL, dữ liệu và tham số.

## 6. Viết lại predicate để truy vấn có thể dùng index

### 6.1. Tránh bọc cột index trong hàm nếu có thể

Truy vấn:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE DATE(created_at) = '2026-10-15';
~~~

Nếu có index trên created_at, việc áp dụng DATE() lên từng giá trị có thể ngăn optimizer dùng range access trên index thông thường.

Viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE created_at >= '2026-10-15 00:00:00'
  AND created_at <  '2026-10-16 00:00:00';
~~~

Cách này giữ predicate trực tiếp trên cột, xử lý chính xác cả phần microsecond và không phụ thuộc giả định thời điểm kết thúc ngày là 23:59:59.

Nếu nghiệp vụ cần biểu thức theo múi giờ, hãy chuyển ranh giới thời gian sang cùng timezone với cách lưu trữ trước khi chạy query. Không dùng phép đổi ngày tùy tiện vì có thể sai ở thời điểm chuyển DST.

### 6.2. Tránh chuyển đổi kiểu dữ liệu không cần thiết

Nếu cột customer_id là BIGINT nhưng tham số ứng dụng truyền chuỗi, MySQL có thể phải chuyển đổi kiểu và ảnh hưởng khả năng dùng index tùy biểu thức. Bind parameter đúng kiểu số qua JDBC.

Tương tự:

- Cột VARCHAR nên được so sánh với giá trị chuỗi đúng charset/collation.
- Không so sánh ngày giờ với chuỗi có định dạng mơ hồ.
- Không dùng CAST(indexed_column AS ...) trong predicate nếu có thể chuẩn hóa tham số.
- Không chuyển cột số thành chuỗi chỉ để so sánh.

### 6.3. LIKE và wildcard đầu chuỗi

Điều kiện:

~~~sql
WHERE email LIKE '%@example.com'
~~~

Không thể dùng B-tree index thông thường để tìm hiệu quả khi pattern bắt đầu bằng wildcard. Nếu nghiệp vụ cần tìm theo domain, có thể cân nhắc cột domain được chuẩn hóa và index riêng, hoặc một cơ chế tìm kiếm phù hợp. Đừng tạo index B-tree rồi kỳ vọng nó tối ưu được mọi kiểu LIKE.

Với prefix search như email LIKE 'user%', index B-tree có thể được dùng trong điều kiện phù hợp.

### 6.4. OR và nhiều điều kiện

Điều kiện OR không phải lúc nào cũng xấu. MySQL có thể dùng Index Merge hoặc kế hoạch khác nếu phù hợp. Hãy đọc plan trước khi viết lại thành UNION.

Khi tách OR thành UNION/UNION ALL, cần bảo đảm ngữ nghĩa không đổi:

- UNION loại duplicate; UNION ALL giữ duplicate.
- Hai nhánh có thể cùng trả về một hàng.
- Điều kiện NULL và ba giá trị logic của SQL có thể làm kết quả khác.
- ORDER BY và LIMIT có phạm vi áp dụng khác nhau nếu đặt sai vị trí.

Chỉ viết lại khi đã kiểm tra tính tương đương và đo hiệu năng.

## 7. Chọn index theo workload

### 7.1. Composite index: equality, range và ordering

Một nguyên tắc khởi đầu thường hữu ích:

1. Đặt các cột được lọc bằng equality vào phần đầu.
2. Sau đó xem cột range.
3. Cân nhắc cột ORDER BY/GROUP BY nếu thứ tự index có thể đáp ứng.
4. Đối chiếu cardinality, tần suất query và các truy vấn khác dùng cùng index.

Đây là heuristic, không phải quy tắc bất biến. Thứ tự tốt nhất phụ thuộc tập predicate, selectivity, join, range, ordering và workload tổng thể.

Ví dụ:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 100;
~~~

Index (account_id,status,created_at) có thể đáp ứng điều kiện equality và thứ tự thời gian. Nếu truy vấn chỉ lọc status mà không có account_id, index đó có thể không hiệu quả vì không có tiền tố trái.

### 7.2. Cardinality và selectivity

- **Cardinality** của index là ước lượng số giá trị khác nhau.
- **Selectivity** phản ánh mức độ điều kiện lọc thu hẹp tập dữ liệu.

Một cột boolean có hai giá trị thường có selectivity thấp nếu phân bố cân bằng. Tuy vậy, nó vẫn có thể hữu ích trong composite index nếu kết hợp với account hoặc ngày giờ.

Không chọn index chỉ dựa trên cardinality của một cột. Cần xem phân bố kết hợp và query thực tế.

### 7.3. Index cho JOIN

~~~sql
SELECT o.order_id, c.customer_name
FROM appdb.orders o
JOIN appdb.customers c
  ON c.customer_id = o.customer_id
WHERE o.account_id = 42
  AND o.created_at >= '2026-10-01 00:00:00';
~~~

Đảm bảo cột join ở phía customers có primary/unique key hoặc index phù hợp. Với bảng orders, index có thể cần bắt đầu bằng account_id, created_at và/hoặc customer_id tùy thứ tự truy cập và workload.

Đọc join order trong EXPLAIN. Nếu outer table tạo ra rất nhiều hàng, mỗi lần lookup vào bảng trong có thể cộng dồn thành chi phí lớn.

### 7.4. Index và GROUP BY

~~~sql
SELECT status, COUNT(*)
FROM appdb.orders
WHERE account_id = 42
  AND created_at >= '2026-10-01'
  AND created_at < '2026-11-01'
GROUP BY status;
~~~

Index phù hợp có thể khác index phục vụ truy vấn top 50 đơn mới nhất. Không cố tạo một index duy nhất cho mọi báo cáo. Nếu workload phân tích nặng, cân nhắc summary table, materialized aggregate do ứng dụng quản lý hoặc hệ thống phân tích riêng.

### 7.5. Tránh index dư thừa

Index dư thừa làm tăng:

- Storage và buffer pool pressure.
- Chi phí INSERT/UPDATE/DELETE.
- Thời gian tạo backup và restore.
- Thời gian DDL và khả năng metadata lock.
- Lượng dữ liệu cần đồng bộ qua replication.

Một index là tiền tố của index khác có thể dư thừa trong một số workload, nhưng không nên xóa chỉ dựa vào hình thức. Unique constraint, thứ tự cột, collation, độ dài prefix và các query khác có thể khiến hai index có vai trò khác nhau.

Có thể thử đánh dấu index là invisible trong môi trường phù hợp:

~~~sql
ALTER TABLE appdb.orders
  ALTER INDEX idx_orders_account_created INVISIBLE;
~~~

Theo dõi kế hoạch truy vấn và workload trong một khoảng thời gian đại diện. Nếu cần khôi phục khả năng optimizer sử dụng index:

~~~sql
ALTER TABLE appdb.orders
  ALTER INDEX idx_orders_account_created VISIBLE;
~~~

Invisible index vẫn được duy trì khi ghi; nó chỉ bị optimizer bỏ qua trong lựa chọn kế hoạch thông thường. Vì vậy phép thử này đánh giá tác động khi optimizer không dùng index, không đo đầy đủ phần chi phí ghi sẽ tiết kiệm sau khi DROP index. Chỉ DROP khi đã xác minh không có workload cần nó và có kế hoạch khôi phục.

## 8. Statistics và kế hoạch thực thi

### 8.1. Khi statistics cũ hoặc sai lệch

Optimizer dựa vào statistics để ước lượng số hàng và chi phí. Nếu dữ liệu thay đổi mạnh, thống kê cũ có thể dẫn đến lựa chọn kế hoạch kém.

Cập nhật thống kê bảng:

~~~sql
ANALYZE TABLE appdb.orders;
~~~

So sánh estimated rows với actual rows sau khi cập nhật. ANALYZE TABLE không phải công cụ chữa mọi truy vấn chậm; nó chỉ hữu ích khi thống kê là một phần nguyên nhân.

### 8.2. Histogram cho phân bố lệch

Nếu một cột có phân bố lệch và optimizer khó ước lượng, histogram có thể giúp:

~~~sql
ANALYZE TABLE appdb.orders
  UPDATE HISTOGRAM ON status WITH 16 BUCKETS;
~~~

Kiểm tra histogram:

~~~sql
SELECT
  SCHEMA_NAME,
  TABLE_NAME,
  COLUMN_NAME,
  HISTOGRAM
FROM INFORMATION_SCHEMA.COLUMN_STATISTICS
WHERE SCHEMA_NAME = 'appdb'
  AND TABLE_NAME = 'orders';
~~~

Histogram không thay thế index và không bảo đảm optimizer sẽ chọn kế hoạch mong muốn. Dùng khi có bằng chứng ước lượng sai do phân bố dữ liệu; đánh giá lại sau khi workload hoặc dữ liệu thay đổi.

Nếu cần bỏ histogram:

~~~sql
ANALYZE TABLE appdb.orders
  DROP HISTOGRAM ON status;
~~~

### 8.3. Khi optimizer không chọn index

Đừng vội dùng FORCE INDEX. Kiểm tra theo thứ tự:

1. Predicate có dùng đúng kiểu dữ liệu và collation không?
2. Index có đúng tiền tố trái và thứ tự cột không?
3. Điều kiện có chọn lọc đủ cao không?
4. Bảng có nhỏ hoặc query cần đọc phần lớn dữ liệu không?
5. Statistics/histogram có phản ánh phân bố hiện tại không?
6. Plan có thực sự chậm khi đo actual rows và time không?

Index hint chỉ nên là biện pháp có bằng chứng, có kiểm thử và có kế hoạch xem xét lại khi dữ liệu thay đổi.

## 9. Truy vấn không chỉ là index

### 9.1. Trả đúng số cột và số hàng cần thiết

Tránh SELECT * trong endpoint chỉ cần vài cột. Đọc thêm dữ liệu làm tăng I/O, network, memory và thời gian hydrate object ở ứng dụng.

Dùng pagination hoặc giới hạn kết quả khi nghiệp vụ cho phép. LIMIT 50 không bảo đảm MySQL chỉ đọc 50 hàng; nếu phải scan và lọc nhiều hàng trước khi tìm đủ 50 kết quả, chi phí vẫn lớn.

### 9.2. OFFSET pagination và keyset pagination

OFFSET lớn có thể buộc MySQL đọc và bỏ qua nhiều hàng:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 50000;
~~~

Với phân trang tiếp theo, keyset pagination dùng khóa cuối của trang trước:

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE account_id = 42
  AND (
    created_at < '2026-10-15 12:00:00.000000'
    OR (
      created_at = '2026-10-15 12:00:00.000000'
      AND order_id < 987654
    )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Index phù hợp có thể là (account_id, created_at, order_id). Cặp (created_at, order_id) tạo thứ tự ổn định khi nhiều đơn có cùng timestamp. Keyset phù hợp với điều hướng tiến/lùi theo cursor; nó không thay thế được yêu cầu nhảy đến trang số tùy ý.

### 9.3. N+1 query từ ứng dụng

Một endpoint có thể chạy một query lấy 100 đơn hàng rồi chạy thêm 100 query lấy chi tiết từng đơn. Mỗi query riêng lẻ có thể nhanh nhưng tổng số lần round trip lớn.

Xác định N+1 bằng query count, digest và trace ứng dụng. Có thể dùng JOIN, batch fetch hoặc truy vấn IN phù hợp. Khi viết JOIN, kiểm tra duplicate do quan hệ one-to-many và tránh tải quá nhiều dữ liệu vào bộ nhớ.

### 9.4. Lock wait và transaction dài

Một truy vấn có thể chậm vì đang chờ lock, không phải vì scan dữ liệu. Xem lock wait, transaction age và blocker trước khi thêm index.

Index phù hợp có thể giảm số record phải đọc/lock trong một số thao tác, nhưng cũng làm tăng công việc duy trì index. Giữ transaction ngắn, truy cập bảng theo thứ tự nhất quán và tránh gọi API ngoài khi transaction đang mở.

## 10. Đo trước và sau khi tối ưu

### 10.1. Thiết lập baseline

Trước khi sửa SQL hoặc tạo index, lưu:

- Câu SQL và tham số đại diện.
- Số lần thực thi, latency trung bình và percentile nếu có.
- Rows examined, rows sent, temporary tables, full scan.
- EXPLAIN dạng tabular/tree và EXPLAIN ANALYZE trên môi trường an toàn.
- CPU, I/O, buffer pool, connection count và lock wait.
- Tốc độ ghi và replication lag.
- Kết quả nghiệp vụ của query.

Không đo một lần rồi kết luận. Chạy nhiều vòng với dữ liệu và tham số đại diện; ghi rõ trạng thái cache và tải nền.

### 10.2. So sánh cùng điều kiện

Sau thay đổi, dùng cùng:

- Phiên bản MySQL và cấu hình.
- Dataset và phân bố dữ liệu.
- Tham số truy vấn.
- Số lần lặp và concurrency.
- Trạng thái cache nếu có thể kiểm soát.
- Cửa sổ tải nền tương đương.

So sánh latency p50/p95/p99 nếu có, throughput, rows examined, rows sent, sort/temp, CPU/I/O và lock wait. Không chỉ so sánh EXPLAIN estimate; phải đo actual behavior.

### 10.3. Kiểm tra tính đúng đắn

Một query nhanh hơn nhưng trả sai dữ liệu là regression. So sánh:

- Số hàng và khóa định danh.
- Thứ tự kết quả khi có ORDER BY.
- Hành vi với NULL và duplicate.
- Boundary thời gian và timezone.
- Giá trị tổng hợp, decimal và làm tròn.
- Kết quả với tham số phổ biến và tham số biên.

Với rewrite có UNION, JOIN, subquery hoặc keyset pagination, kiểm tra semantics trước khi benchmark.

### 10.4. Tiêu chí thành công

Đặt mục tiêu trước khi thay đổi, ví dụ:

| Nhóm | Chỉ số cần đạt |
|---|---|
| Đúng đắn | Kết quả tương đương theo quy tắc nghiệp vụ |
| Latency | p95/p99 giảm theo mục tiêu |
| Công việc đọc | Rows examined giảm hoặc hợp lý với rows sent |
| Kế hoạch | Chọn access path phù hợp, không sort/temp ngoài dự kiến |
| Tài nguyên | CPU/I/O không chuyển thành bottleneck khác |
| Ghi | Throughput ghi không giảm quá ngưỡng chấp nhận |
| Đồng bộ | Replication lag vẫn trong SLO |
| Vận hành | DDL và rollback index có runbook, giám sát và owner |

Không có ngưỡng latency chung cho mọi ứng dụng. Chọn SLO theo endpoint và yêu cầu nghiệp vụ.

## 11. Triển khai index an toàn

### 11.1. Đánh giá trước DDL

Trước khi tạo index trên bảng lớn, kiểm tra:

- Dung lượng index dự kiến và dung lượng disk còn trống.
- Tải CPU/I/O và buffer pool.
- Transaction dài và metadata lock.
- Replication lag và khả năng bắt kịp.
- Thời gian tạo index đã đo trên bản sao.
- Ảnh hưởng tới INSERT/UPDATE/DELETE.
- Thời điểm chạy và cách dừng/khôi phục nếu có vấn đề.

Một số thao tác InnoDB hỗ trợ Online DDL, nhưng không phải mọi thay đổi đều không khóa hoặc không ảnh hưởng tải. Xác nhận thuật toán và mức lock được hỗ trợ cho đúng phiên bản và cấu trúc bảng. Có thể chỉ định ALGORITHM/LOCK để yêu cầu MySQL thất bại thay vì âm thầm dùng phương thức có mức khóa không mong muốn, sau khi đã kiểm tra cú pháp được hỗ trợ.

### 11.2. Theo dõi trong khi tạo index

Trong lúc DDL chạy:

- Theo dõi process list và metadata lock.
- Theo dõi CPU, I/O, disk, temporary space và redo/undo.
- Theo dõi replication lag và relay log.
- Theo dõi latency ứng dụng và lock wait.
- Xác định rõ điều kiện dừng nếu tải vượt ngưỡng.

Không KILL DDL hoặc restart chỉ vì thời gian chạy lâu. Đánh giá tiến độ, metadata lock và tác động trước khi can thiệp.

### 11.3. Sau khi tạo index

- Chạy ANALYZE TABLE khi cần cập nhật thống kê.
- Đọc lại EXPLAIN và EXPLAIN ANALYZE.
- Chạy workload benchmark.
- Kiểm tra query khác có đổi plan bất lợi không.
- Theo dõi write latency, storage và replication.
- Ghi lại index owner, query phục vụ và lý do giữ index.

Index nên có một workload cụ thể biện minh cho chi phí duy trì của nó.

## 12. Kịch bản thực hành từ đầu đến cuối

Dùng staging hoặc database kiểm thử có dữ liệu đại diện.

### Bước 1: Chọn digest

Từ slow log hoặc sys.statement_analysis, chọn nhóm query có tổng latency cao hoặc rows examined lớn. Ghi digest, tần suất, tham số đại diện và owner.

### Bước 2: Tái hiện

Chạy query với cùng kiểu bind parameter và bộ dữ liệu gần production. Xác minh kết quả đúng trước khi tối ưu.

### Bước 3: Đọc kế hoạch

Chạy EXPLAIN FORMAT=TREE, EXPLAIN và EXPLAIN ANALYZE trên SELECT an toàn. Ghi lại access type, key, estimated/actual rows, sort/temp và thời gian iterator.

### Bước 4: Xác định nguyên nhân

Phân loại nguyên nhân:

- Predicate không SARGable.
- Thiếu hoặc sai composite index.
- Index không chọn lọc hoặc dư thừa.
- Statistics/histogram không phản ánh dữ liệu.
- JOIN order hoặc N+1.
- OFFSET lớn hoặc sort.
- Lock wait, transaction dài hoặc tài nguyên bão hòa.

### Bước 5: Thử một thay đổi

Chỉ thay đổi một yếu tố trong mỗi vòng: rewrite predicate, thêm index, cập nhật statistics hoặc đổi cách pagination. Như vậy có thể xác định yếu tố nào tạo ra cải thiện.

### Bước 6: Đo lại và kiểm tra đúng đắn

Chạy cùng dataset/params/concurrency. So sánh plan, latency, rows examined, CPU/I/O và kết quả dữ liệu. Kiểm tra cả workload ghi và query khác sử dụng cùng bảng.

### Bước 7: Lập kế hoạch triển khai

Ghi DDL, cửa sổ triển khai, metadata lock, dung lượng, replication lag, ngưỡng dừng và phương án rollback. Nếu tạo index mới, rollback thường là bỏ index sau khi xác nhận không có query phụ thuộc; cần tính thời gian và tác động DDL khi DROP.

### Bước 8: Theo dõi sau release

Theo dõi slow log/digest, latency, throughput, error rate, write load, lock wait và replica lag. Nếu plan thay đổi xấu hoặc tài nguyên tăng quá ngưỡng, thực hiện rollback theo runbook đã chuẩn bị.

## 13. Sự cố tối ưu truy vấn thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| type=ALL, rows lớn | Table scan, predicate không dùng được index hoặc optimizer chọn scan | Kiểm tra predicate, cardinality, kích thước bảng và EXPLAIN ANALYZE |
| possible_keys có nhưng key=NULL | Index không phù hợp hoặc scan rẻ hơn | Kiểm tra selectivity, kiểu dữ liệu, statistics và điều kiện |
| Using filesort | Thứ tự index không đáp ứng ORDER BY hoặc cần sort tập kết quả | Kiểm tra composite index, LIMIT và số hàng đầu vào |
| Using temporary | GROUP BY/DISTINCT/ORDER BY cần xử lý trung gian | Kiểm tra plan, cardinality và khả năng giảm dữ liệu trước aggregation |
| Rows examined rất cao, rows sent thấp | Filter muộn hoặc index thiếu cột điều kiện | Xem composite index và SARGability |
| Plan thay đổi sau deploy | Statistics, dữ liệu, parameter distribution hoặc version thay đổi | So sánh plan và statistics trước/sau; kiểm thử trên dữ liệu đại diện |
| Query nhanh riêng lẻ nhưng endpoint chậm | N+1, round trip, lock, serialization hoặc tải ứng dụng | Kết hợp digest với trace và metrics ứng dụng |
| Thêm index làm ghi chậm | Index maintenance và I/O tăng | Đánh giá lợi ích workload đọc so với chi phí ghi |
| Tạo index gây lag replica | DDL và workload tạo tải lớn | Theo dõi topology, điều chỉnh cửa sổ và phương pháp DDL |
| Slow log quá lớn | Ngưỡng thấp hoặc log truy vấn không dùng index quá rộng | Điều chỉnh threshold, throttle, retention và rotation |

## 14. Checklist trước khi kết luận tối ưu

### Thu thập và ưu tiên

- [ ] Slow log được bật với ngưỡng phù hợp.
- [ ] Đã xem digest và xếp hạng theo tổng latency, tần suất, rows examined.
- [ ] Đã chọn tham số đại diện và xác định owner.
- [ ] Log được bảo vệ và che dữ liệu nhạy cảm.

### Phân tích

- [ ] Đã đọc EXPLAIN dạng tabular/tree.
- [ ] Đã so estimated rows với actual rows khi có thể.
- [ ] Đã kiểm tra predicate, kiểu dữ liệu, JOIN, ORDER BY và GROUP BY.
- [ ] Đã kiểm tra lock wait và transaction nếu latency bất thường.
- [ ] Đã kiểm tra statistics/histogram khi ước lượng sai.

### Index và rewrite

- [ ] Index có workload cụ thể biện minh.
- [ ] Thứ tự composite index phù hợp predicate và ordering.
- [ ] Đã đánh giá covering index và chi phí storage/write.
- [ ] Không tạo index trùng hoặc dư thừa mà chưa xem toàn workload.
- [ ] Query rewrite giữ đúng semantics, NULL, duplicate và boundary.

### Đo lường và triển khai

- [ ] Baseline và kết quả sau thay đổi dùng cùng điều kiện.
- [ ] Đã đo latency, rows examined, CPU/I/O, write load và replication lag.
- [ ] Đã kiểm tra kết quả nghiệp vụ.
- [ ] Đã đánh giá metadata lock và Online DDL.
- [ ] Có ngưỡng dừng, phương án rollback và người chịu trách nhiệm.
- [ ] Đã theo dõi sau release và lưu bằng chứng.

## 15. Tự kiểm tra

**Tình huống 1:** Slow log cho thấy một query mất 200 ms nhưng chạy 50.000 lần mỗi giờ. Một query khác mất 8 giây nhưng chỉ chạy một lần mỗi ngày. Nên ưu tiên truy vấn nào?

**Gợi ý:** So sánh tổng latency, tác động tới SLO, tài nguyên và số người dùng bị ảnh hưởng. Query 200 ms có thể tạo tổng tải lớn hơn nhiều; query 8 giây vẫn cần xem nếu chặn một nghiệp vụ quan trọng.

**Tình huống 2:** EXPLAIN cho thấy type=ALL. Có phải phải tạo index ngay?

**Gợi ý:** Không. Bảng có thể nhỏ hoặc query cần phần lớn dữ liệu. Xem rows, predicate, selectivity, actual execution và workload trước khi quyết định.

**Tình huống 3:** Một truy vấn lọc theo DATE(created_at). Index trên created_at không được sử dụng hiệu quả. Nên thử gì?

**Gợi ý:** Viết lại thành khoảng nửa mở: created_at >= đầu_ngày AND created_at < đầu_ngày_tiếp_theo, rồi so sánh execution plan và kết quả.

**Tình huống 4:** Index (account_id,status,created_at) phục vụ tốt query lọc đủ ba cột. Query chỉ lọc status có chắc dùng index hiệu quả không?

**Gợi ý:** Không. Composite index tuân theo tiền tố trái; không có account_id thì index có thể không phù hợp cho điều kiện chỉ dùng status.

**Tình huống 5:** Sau khi tạo covering index, SELECT nhanh hơn nhưng UPDATE chậm hơn. Có nên giữ index?

**Gợi ý:** Đánh giá toàn workload. Index làm tăng chi phí ghi và storage. So sánh lợi ích đọc với tần suất cập nhật, latency ghi, replication và dung lượng trước khi quyết định.

**Tình huống 6:** EXPLAIN ANALYZE cho thấy estimated rows là 10 nhưng actual rows là 200.000. Cần kiểm tra gì?

**Gợi ý:** Xem statistics, phân bố dữ liệu, histogram và selectivity. Cập nhật statistics hoặc histogram khi có bằng chứng ước lượng sai; sau đó đọc lại plan và đo thực tế.

## 16. Điểm cần ghi nhớ

- Slow query log giúp tìm truy vấn chậm, digest và metrics giúp chọn đúng nhóm workload cần ưu tiên.
- Tổng latency và tần suất thường quan trọng không kém latency trung bình của một lần chạy.
- EXPLAIN cho biết kế hoạch ước lượng; EXPLAIN ANALYZE thực thi SELECT và cho biết số liệu thực tế.
- ALL hoặc Using filesort là tín hiệu cần phân tích, không phải bằng chứng tự động rằng phải thêm index.
- Composite index cần được thiết kế theo predicate, tiền tố trái, range, ordering và workload tổng thể.
- Covering index có thể giảm lookup nhưng làm tăng dung lượng và chi phí ghi.
- Predicate SARGable, kiểu dữ liệu phù hợp và pagination hợp lý có thể cải thiện truy vấn mà không cần thêm index.
- Statistics và histogram ảnh hưởng lựa chọn kế hoạch; cập nhật chúng khi có bằng chứng ước lượng sai.
- Index mới cần được đo cả lợi ích đọc lẫn tác động lên ghi, DDL, backup và replication.
- Chỉ kết luận tối ưu sau khi so sánh cùng dữ liệu, tham số, concurrency và xác minh kết quả nghiệp vụ.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: The Slow Query Log](https://dev.mysql.com/doc/refman/8.4/en/slow-query-log.html) — cấu hình và nội dung slow query log.
- [MySQL 8.4 Reference Manual: mysqldumpslow](https://dev.mysql.com/doc/refman/8.4/en/mysqldumpslow.html) — nhóm và phân tích slow query log.
- [MySQL 8.4 Reference Manual: EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html) — đọc execution plan và EXPLAIN ANALYZE.
- [MySQL 8.4 Reference Manual: Optimization and Indexes](https://dev.mysql.com/doc/refman/8.4/en/optimization-indexes.html) — nguyên tắc tối ưu và sử dụng index.
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html) — composite index và tiền tố trái.
- [MySQL 8.4 Reference Manual: Optimizer Statistics](https://dev.mysql.com/doc/refman/8.4/en/optimizer-statistics.html) — thống kê optimizer và histogram.
- [MySQL 8.4 Reference Manual: Invisible Indexes](https://dev.mysql.com/doc/refman/8.4/en/invisible-indexes.html) — thử nghiệm index invisible.
- [MySQL 8.4 Reference Manual: InnoDB Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — thuật toán DDL và mức khóa.
- [MySQL 8.4 Reference Manual: sys Schema Statement Analysis](https://dev.mysql.com/doc/refman/8.4/en/sys-statement-analysis.html) — thống kê statement theo digest.
