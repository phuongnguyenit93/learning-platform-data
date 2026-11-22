# Statement digest và nhóm các truy vấn cùng cấu trúc

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Khi một ứng dụng gửi hàng nghìn câu SQL mỗi phút, việc xem từng câu riêng lẻ không giúp tìm ra nhóm truy vấn đang tiêu tốn tài nguyên. MySQL Performance Schema có thể chuẩn hóa cấu trúc statement thành digest để gom những câu lệnh có cùng hình dạng, sau đó tổng hợp số lần chạy, thời gian, số hàng đọc, số hàng trả về, lỗi, cảnh báo và một số chỉ số thực thi.

Statement digest giúp trả lời các câu hỏi vận hành:

- Nhóm câu SQL nào chạy nhiều nhất?
- Nhóm nào chiếm tổng thời gian database lớn nhất?
- Nhóm nào chậm trung bình trên mỗi lần chạy?
- Nhóm nào đọc nhiều hàng nhưng trả về ít hàng?
- Nhóm nào thường tạo temporary table trên disk, sort hoặc full scan?
- Sau một lần deploy, nhóm truy vấn nào tăng số lần chạy hoặc latency?

Digest là công cụ tổng hợp và ưu tiên điều tra. Nó không thay thế execution plan, query trace, log ứng dụng hoặc phân tích từng giá trị tham số. Nhiều câu SQL có cùng cấu trúc vẫn có thể có độ chọn lọc dữ liệu, plan và thời gian thực thi rất khác nhau.

## 1. Vì sao cần nhóm truy vấn theo cấu trúc?

Giả sử ứng dụng có các câu lệnh:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101;

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 202;

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 303;
~~~

Ba câu lệnh khác nhau ở giá trị customer_id nhưng có cùng cấu trúc. Khi điều tra hiệu năng, thường cần biết tổng thể nhóm truy vấn này chạy bao nhiêu lần, tiêu tốn bao nhiêu thời gian và đọc bao nhiêu hàng.

Một ví dụ khác:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 501;

UPDATE inventory
SET available_quantity = available_quantity - 2
WHERE product_id = 502;
~~~

Hai câu UPDATE có cùng hình dạng. Gom chúng theo digest giúp nhận diện workload cập nhật kho, ngay cả khi từng product_id thay đổi.

Nếu chỉ nhìn slow query log, ta thường tập trung vào những lần chạy vượt ngưỡng thời gian. Digest bổ sung góc nhìn tổng hợp: một câu truy vấn chỉ mất vài mili giây nhưng chạy hàng triệu lần có thể tiêu tốn nhiều tài nguyên hơn một câu chậm hiếm gặp.

## 2. Statement digest là gì?

Statement digest là biểu diễn chuẩn hóa của cấu trúc câu SQL. MySQL phân tích statement, thay các literal thường gặp bằng dấu placeholder ?, chuẩn hóa một số khác biệt về khoảng trắng và cách viết, rồi tạo digest để nhận diện nhóm.

Ví dụ:

| Câu SQL gửi tới server | Dạng digest minh họa |
|---|---|
| SELECT * FROM orders WHERE order_id = 10 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE order_id = 25 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE order_id = 900 | SELECT * FROM orders WHERE order_id = ? |
| SELECT * FROM orders WHERE customer_id = 10 | SELECT * FROM orders WHERE customer_id = ? |

Ba câu đầu thuộc cùng một nhóm cấu trúc; câu cuối thuộc nhóm khác vì điều kiện lọc khác cột.

### 2.1. DIGEST và DIGEST_TEXT

Trong Performance Schema:

- **DIGEST** là mã nhận diện digest được tính từ cấu trúc statement.
- **DIGEST_TEXT** là văn bản digest đã chuẩn hóa, thuận tiện để đọc và phân tích.
- **SCHEMA_NAME** cho biết schema mặc định gắn với statement khi được ghi nhận.

Summary table nhóm theo schema và digest. Cùng một cấu trúc SQL chạy trong hai schema khác nhau có thể xuất hiện thành hai hàng riêng.

### 2.2. Những gì được chuẩn hóa

Thông thường, các literal như số, chuỗi và giá trị ngày giờ được thay bằng placeholder. Khác biệt không có ý nghĩa như khoảng trắng và comment thông thường không tạo ra nhóm riêng. Tên bảng, tên cột, toán tử, cấu trúc JOIN, điều kiện và thứ tự nhiều thành phần SQL vẫn ảnh hưởng đến digest.

Do đó:

- Thay customer_id từ 101 thành 202 thường vẫn thuộc cùng digest.
- Đổi customer_id thành order_id tạo cấu trúc khác.
- Thêm một JOIN hoặc điều kiện WHERE có thể tạo digest khác.
- Hai câu SQL có cùng kết quả nghiệp vụ nhưng viết theo cấu trúc khác nhau có thể thuộc hai digest.

Không coi digest là chứng minh hai câu lệnh tương đương về nghiệp vụ. Digest chỉ phục vụ nhóm cấu trúc theo quy tắc phân tích của MySQL.

### 2.3. Digest không giữ lại mọi giá trị tham số

Vì literal được chuẩn hóa, DIGEST_TEXT không cho biết câu truy vấn đã chạy với customer_id hoặc ngày cụ thể nào. Đây là đặc điểm hữu ích để giảm số nhóm và tránh hiển thị trực tiếp nhiều giá trị literal.

Nếu cần điều tra một giá trị tham số cụ thể, hãy kết hợp log ứng dụng, tracing, slow query log có kiểm soát hoặc công cụ audit phù hợp. Không bật ghi toàn bộ SQL chứa dữ liệu nhạy cảm chỉ để thay thế digest.

### 2.4. Cùng digest không có nghĩa cùng hiệu năng

Một digest có thể gom các lần chạy với giá trị tham số rất khác nhau:

- Một customer có 5 đơn hàng, customer khác có hàng triệu đơn.
- Một khoảng thời gian lọc chỉ chứa vài chục hàng, khoảng khác chứa hàng chục triệu hàng.
- Một giá trị phân bố rất phổ biến, giá trị khác rất hiếm.
- Một lần chạy dùng plan hiệu quả, lần khác bị ảnh hưởng bởi thống kê hoặc điều kiện dữ liệu.

Vì vậy, digest cho biết nhóm nào đáng chú ý; cần kiểm tra thêm các tham số đại diện và execution plan trước khi sửa SQL hoặc index.

## 3. Nguồn dữ liệu: events_statements_summary_by_digest

MySQL Performance Schema cung cấp bảng:

performance_schema.events_statements_summary_by_digest

Bảng này lưu thống kê tổng hợp theo digest và schema. Mỗi hàng đại diện một nhóm statement đã được instrument và tổng hợp. Các chỉ số là số liệu tích lũy trong vòng đời thống kê hiện tại, thường tính từ khi server khởi động hoặc từ lần reset summary table gần nhất.

Một số cột thường dùng:

| Cột | Ý nghĩa |
|---|---|
| SCHEMA_NAME | Schema mặc định của statement |
| DIGEST | Mã nhận diện nhóm |
| DIGEST_TEXT | Câu SQL đã chuẩn hóa |
| COUNT_STAR | Số lần statement được ghi nhận |
| SUM_TIMER_WAIT | Tổng thời gian thực thi |
| AVG_TIMER_WAIT | Thời gian trung bình mỗi lần |
| MIN_TIMER_WAIT | Thời gian ngắn nhất |
| MAX_TIMER_WAIT | Thời gian dài nhất |
| SUM_LOCK_TIME | Tổng thời gian chờ lock được đo |
| SUM_ERRORS | Số lần lỗi |
| SUM_WARNINGS | Số lần có warning |
| SUM_ROWS_AFFECTED | Tổng số hàng bị ảnh hưởng |
| SUM_ROWS_SENT | Tổng số hàng gửi về client |
| SUM_ROWS_EXAMINED | Tổng số hàng được đọc/kiểm tra |
| SUM_CREATED_TMP_TABLES | Tổng temporary table được tạo |
| SUM_CREATED_TMP_DISK_TABLES | Tổng temporary table được tạo trên disk |
| SUM_SELECT_SCAN | Số lần thực hiện select scan |
| SUM_NO_INDEX_USED | Số lần không sử dụng index |
| SUM_NO_GOOD_INDEX_USED | Số lần optimizer không tìm được index phù hợp |
| FIRST_SEEN | Thời điểm đầu tiên ghi nhận digest |
| LAST_SEEN | Thời điểm gần nhất ghi nhận digest |

Danh sách cột có thể khác theo phiên bản MySQL. Hãy kiểm tra cấu trúc bảng trên phiên bản đang chạy trước khi đưa truy vấn monitoring vào hệ thống lâu dài.

### 3.1. Performance Schema có được bật không?

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema';
~~~

Nếu Performance Schema bị tắt khi khởi động, không thể bật đầy đủ chỉ bằng một câu UPDATE trong runtime. Cần cấu hình ở startup và khởi động lại theo quy trình vận hành.

### 3.2. Kiểm tra consumer statements_digest

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'statements_digest',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);
~~~

Consumer statements_digest điều khiển việc thu thập thông tin digest. Trên các bản MySQL hỗ trợ, consumer này thường được bật mặc định; vẫn cần kiểm tra cấu hình thực tế.

Nếu có chủ đích bật digest collection và được cấp quyền:

~~~sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME = 'statements_digest';
~~~

Các consumer history có mục đích khác và không bắt buộc phải bật chỉ để xem summary theo digest. Không bật mọi consumer một cách tùy tiện vì mỗi loại thu thập bổ sung đều có chi phí bộ nhớ và xử lý.

### 3.3. Kiểm tra statement instruments

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
ORDER BY NAME;
~~~

Instrument xác định loại statement nào được ghi nhận và có đo thời gian hay không. Nếu statement instrument bị tắt hoặc TIMED = NO, dữ liệu hoặc timing có thể không đầy đủ.

Chỉ bật những instrument cần thiết theo chính sách monitoring:

~~~sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'statement/%';
~~~

Ví dụ trên bật rộng nhóm statement instruments. Chỉ thực hiện sau khi đánh giá overhead, quyền truy cập và yêu cầu môi trường. Trên hệ thống production, ưu tiên cấu hình có kiểm soát và theo dõi chi phí sau khi bật.

## 4. Truy vấn digest cơ bản

### 4.1. Xem các nhóm truy vấn có tổng thời gian lớn nhất

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR AS exec_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent,
    SUM_ERRORS AS errors,
    SUM_WARNINGS AS warnings
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

Các cột timer của Performance Schema được biểu diễn bằng picosecond. Chia cho 10^12 để đổi sang giây. Tổng thời gian lớn cho thấy nhóm truy vấn chiếm nhiều thời gian database trong khoảng thống kê hiện tại; nó không đồng nghĩa từng lần chạy đều chậm.

### 4.2. Nhóm có số lần chạy cao nhất

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR AS exec_count,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_latency_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY COUNT_STAR DESC
LIMIT 20;
~~~

Một truy vấn rất nhanh nhưng chạy liên tục vẫn có thể đứng đầu danh sách này. Kiểm tra xem ứng dụng có gọi cùng câu SQL quá thường xuyên, có thể batch, cache ở tầng ứng dụng hoặc giảm round trip hay không.

### 4.3. Nhóm có thời gian trung bình cao

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_latency_seconds,
    ROUND(MAX_TIMER_WAIT / 1000000000000, 3) AS max_latency_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND COUNT_STAR > 0
ORDER BY AVG_TIMER_WAIT DESC
LIMIT 20;
~~~

AVG_TIMER_WAIT giúp tìm nhóm tốn thời gian trung bình cao. Cần đọc cùng COUNT_STAR vì một digest chỉ chạy một lần chưa chắc là vấn đề ưu tiên hơn nhóm chạy hàng trăm nghìn lần.

### 4.4. Nhóm đọc nhiều hàng nhưng trả về ít

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        1
    ) AS examined_per_row_sent,
    SUM_NO_INDEX_USED,
    SUM_NO_GOOD_INDEX_USED
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 20;
~~~

Tỷ lệ examined/sent cao có thể gợi ý truy vấn đọc thừa nhiều hàng. Nhưng tỷ lệ này không đủ để kết luận truy vấn sai: aggregate, EXISTS, truy vấn không trả hàng hoặc truy vấn xử lý dữ liệu trung gian có thể có tỷ lệ khác thường. Hãy kiểm tra SQL và plan.

### 4.5. Nhóm tạo temporary table trên disk

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_CREATED_TMP_TABLES,
    SUM_CREATED_TMP_DISK_TABLES,
    SUM_SORT_ROWS,
    SUM_SORT_MERGE_PASSES
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_CREATED_TMP_DISK_TABLES DESC
LIMIT 20;
~~~

Temporary table trên disk có thể phát sinh từ GROUP BY, ORDER BY, DISTINCT, UNION hoặc các phép xử lý khác. Không phải mọi temporary table đều là lỗi; cần so sánh kích thước dữ liệu, tần suất và độ trễ. Nếu số lượng lớn, kiểm tra execution plan, biểu thức, index và giới hạn bộ nhớ tạm.

### 4.6. Nhóm có lỗi hoặc cảnh báo

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ERRORS,
    SUM_WARNINGS,
    FIRST_SEEN,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
  AND (SUM_ERRORS > 0 OR SUM_WARNINGS > 0)
ORDER BY SUM_ERRORS DESC, SUM_WARNINGS DESC
LIMIT 20;
~~~

Digest summary cho biết nhóm nào có lỗi hoặc warning, nhưng không lưu toàn bộ message chi tiết của từng lần chạy. Dùng error log, ứng dụng hoặc statement history phù hợp để tìm nguyên nhân cụ thể.

## 5. Chọn cách xếp hạng đúng mục tiêu

Không có một danh sách top 10 duy nhất phù hợp cho mọi đợt điều tra. Hãy chọn tiêu chí theo câu hỏi:

| Mục tiêu | Chỉ số ưu tiên | Cách đọc |
|---|---|---|
| Giảm tổng thời gian DB | SUM_TIMER_WAIT | Nhóm tiêu tốn tổng thời gian lớn |
| Giảm số lần gọi | COUNT_STAR | Nhóm được thực thi thường xuyên |
| Tìm truy vấn chậm trung bình | AVG_TIMER_WAIT | Chi phí trung bình mỗi lần |
| Tìm lần chạy cực chậm | MAX_TIMER_WAIT | Giá trị lớn nhất trong khoảng thống kê |
| Giảm đọc thừa | SUM_ROWS_EXAMINED, SUM_ROWS_SENT | Đối chiếu số hàng đọc và trả về |
| Tìm full scan đáng chú ý | SUM_NO_INDEX_USED, SUM_SELECT_SCAN | Kiểm tra SQL và plan |
| Giảm temporary disk table | SUM_CREATED_TMP_DISK_TABLES | Điều tra sort, group và kích thước dữ liệu |
| Tìm lỗi ứng dụng | SUM_ERRORS, SUM_WARNINGS | Đối chiếu log chi tiết |

### 5.1. Tổng thời gian và thời gian trung bình khác nhau

Giả sử:

| Digest | Số lần chạy | Trung bình | Tổng thời gian |
|---|---:|---:|---:|
| A | 100.000 | 2 ms | 200 s |
| B | 20 | 2 s | 40 s |
| C | 10.000 | 5 ms | 50 s |

Digest A tiêu tốn tổng thời gian nhiều nhất. Digest B có mỗi lần chạy chậm nhất. Tùy mục tiêu, có thể tối ưu A để giảm tổng tải hoặc B để cải thiện trải nghiệm cho một thao tác quan trọng.

### 5.2. Không chỉ nhìn COUNT_STAR

Một nhóm chạy nhiều có thể chỉ là truy vấn lookup rất nhỏ. Một nhóm chạy ít có thể là báo cáo lớn, migration hoặc thao tác quản trị. Kết hợp tần suất, latency, rows examined, lock time, errors và vai trò nghiệp vụ trước khi ưu tiên.

### 5.3. Không chỉ nhìn MAX_TIMER_WAIT

MAX_TIMER_WAIT chỉ cho biết lần chạy lâu nhất được ghi nhận trong khoảng thống kê hiện tại. Nó không cho biết phân phối latency, percentile hay nguyên nhân. Nếu cần phân phối chi tiết theo request, dùng tracing hoặc hệ thống metrics phù hợp.

## 6. Dùng sys.statement_analysis

MySQL cung cấp schema sys với các view đọc dễ hơn trên Performance Schema. Một view thường dùng là sys.statement_analysis.

~~~sql
SELECT
    query,
    db,
    full_scan,
    exec_count,
    err_count,
    warn_count,
    total_latency,
    avg_latency,
    rows_sent,
    rows_examined,
    tmp_tables,
    tmp_disk_tables
FROM sys.statement_analysis
LIMIT 20;
~~~

View này trình bày statement đã chuẩn hóa cùng các chỉ số tổng hợp ở dạng thuận tiện cho người vận hành. Các cột có thể thay đổi theo phiên bản sys schema đi kèm MySQL. Kiểm tra định nghĩa view nếu triển khai dashboard phụ thuộc vào tên cột cụ thể.

### 6.1. Khi nào dùng sys và khi nào dùng Performance Schema?

- Dùng sys.statement_analysis để xem nhanh top statement bằng các tên cột dễ hiểu.
- Dùng performance_schema.events_statements_summary_by_digest khi cần kiểm soát chính xác phép tính, timer, digest và các cột tổng hợp.
- Dùng events_statements_history hoặc events_statements_history_long để xem một số lần chạy gần đây nếu consumer được bật và dung lượng history đủ.
- Dùng slow query log để lưu các statement vượt ngưỡng theo chính sách log.
- Dùng application tracing để liên kết query với endpoint, request ID, tenant hoặc người dùng.

Digest summary không phải bảng lịch sử bất biến. Nó giữ thống kê tổng hợp, không lưu đầy đủ mọi lần chạy.

## 7. Giới hạn số digest và nội dung bị cắt

Performance Schema không giữ vô hạn số nhóm digest. Dung lượng hàng được kiểm soát bởi biến khởi động performance_schema_digests_size.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema_digests_size';
SHOW GLOBAL VARIABLES LIKE 'max_digest_length';
SHOW GLOBAL VARIABLES LIKE 'performance_schema_max_digest_length';
~~~

- performance_schema_digests_size điều khiển số digest entry có thể được lưu trong summary table.
- max_digest_length giới hạn độ dài statement được dùng cho quá trình tạo digest.
- performance_schema_max_digest_length điều khiển giới hạn độ dài digest text được lưu trong Performance Schema.

Các biến này có phạm vi và khả năng thay đổi phụ thuộc phiên bản; thường phải đặt ở startup. Kiểm tra tài liệu đúng bản MySQL trước khi điều chỉnh.

### 7.1. Khi digest table hết chỗ

Khi số cấu trúc statement khác nhau vượt khả năng lưu, MySQL có thể gom các statement không có entry riêng vào hàng có DIGEST IS NULL. Hàng này là tín hiệu cho biết digest capacity có thể không đủ; nội dung của nó không đại diện một query shape duy nhất để tối ưu.

Kiểm tra:

~~~sql
SELECT
    COUNT_STAR,
    SUM_TIMER_WAIT,
    SUM_ERRORS,
    SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NULL;
~~~

Nếu hàng này có số liệu đáng kể, cân nhắc tăng performance_schema_digests_size ở startup sau khi đánh giá bộ nhớ. Đồng thời kiểm tra ứng dụng có tạo quá nhiều SQL động với tên bảng/cột hoặc cấu trúc khác nhau hay không.

### 7.2. Digest text bị cắt

Statement quá dài có thể bị giới hạn khi tạo digest hoặc lưu digest text. Khi đọc DIGEST_TEXT, kiểm tra xem phần cuối có bị cắt và cấu trúc có còn đủ để phân biệt nhóm hay không.

Không tăng mọi giới hạn digest lên rất lớn một cách máy móc. Số entry và độ dài text đều tiêu tốn bộ nhớ Performance Schema. Đặt mức đủ cho workload và xác nhận sau restart.

## 8. Theo dõi theo khoảng thời gian

Các counter trong digest summary là tích lũy. Nếu chỉ xem một lần, bạn thấy số liệu kể từ lúc server khởi động hoặc lần reset gần nhất, không phải tốc độ trong 5 phút vừa qua.

### 8.1. Lấy hai snapshot

Ghi lại các cột:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_TIMER_WAIT,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_ERRORS,
    LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL;
~~~

Chụp snapshot A, đợi một khoảng thời gian có workload đại diện, rồi chụp snapshot B. Đối chiếu theo khóa (SCHEMA_NAME, DIGEST) để tính delta:

- Delta COUNT_STAR: số lần thực thi trong cửa sổ.
- Delta SUM_TIMER_WAIT: tổng thời gian trong cửa sổ.
- Delta SUM_ROWS_EXAMINED: số hàng đã kiểm tra thêm.
- Delta SUM_ERRORS: số lỗi mới.

Nếu cần dashboard theo thời gian, lưu snapshot ra hệ thống metrics hoặc kho monitoring bên ngoài. Không coi Performance Schema digest summary là time-series database.

### 8.2. Tính latency trung bình trong cửa sổ

Với hai snapshot:

~~~text
delta_count = count_B - count_A
delta_timer = timer_B - timer_A

avg_latency_window =
    delta_timer / delta_count
~~~

Chỉ tính khi delta_count > 0. Timer vẫn ở đơn vị picosecond nếu lấy trực tiếp từ Performance Schema. Đổi sang giây bằng cách chia cho 10^12.

### 8.3. Reset summary có chủ đích

Trong môi trường lab hoặc cửa sổ đo được phê duyệt, có thể reset digest summary:

~~~sql
TRUNCATE TABLE performance_schema.events_statements_summary_by_digest;
~~~

Thao tác này reset số liệu tổng hợp trong bảng Performance Schema, không xóa dữ liệu nghiệp vụ của ứng dụng. Tuy nhiên, nó làm mất baseline thống kê trước đó cho toàn server. Trên production, không reset tùy tiện; hãy lưu snapshot trước và phối hợp với hệ thống monitoring.

### 8.4. Reset không phải giải pháp cho digest capacity

Nếu số digest khác nhau liên tục vượt performance_schema_digests_size, reset có thể giải phóng entry trong thời gian ngắn nhưng vấn đề sẽ quay lại. Hãy kiểm tra SQL động, số schema, kích thước digest và nhu cầu dung lượng thực tế.

## 9. Kết hợp digest với execution plan

Digest cho biết nhóm truy vấn đáng điều tra; execution plan giúp tìm nguyên nhân truy cập dữ liệu.

Quy trình:

1. Chọn digest có tổng latency, average latency hoặc rows examined đáng chú ý.
2. Đọc DIGEST_TEXT để xác định bảng, điều kiện, JOIN, GROUP BY và ORDER BY.
3. Chọn các giá trị tham số đại diện từ log hoặc ứng dụng.
4. Chạy EXPLAIN với câu SQL cụ thể.
5. Nếu phù hợp, dùng EXPLAIN ANALYZE trên môi trường an toàn để xem actual rows, loops và thời gian iterator.
6. So sánh estimate với actual rows.
7. Kiểm tra index, thống kê, cardinality, join order, temporary table và sort.
8. Sau thay đổi, theo dõi digest delta để xác nhận kết quả.

Ví dụ digest:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?;
~~~

Một câu chạy với customer có ít đơn:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101;
~~~

Một câu chạy với customer có rất nhiều đơn:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 900;
~~~

Hai lần chạy thuộc cùng digest nhưng optimizer có thể chịu tác động từ phân bố dữ liệu và thống kê. Đánh giá với các giá trị đại diện thay vì chỉ một giá trị thuận tiện.

### 9.1. Dùng EXPLAIN ANALYZE cẩn thận

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 900;
~~~

EXPLAIN ANALYZE thực thi câu truy vấn để đo actual iterator. Không chạy tùy tiện trên câu UPDATE/DELETE hoặc truy vấn báo cáo rất nặng ở production. Bắt đầu trên staging hoặc với câu SELECT có giới hạn tác động.

### 9.2. Kiểm tra các chỉ số đi kèm

Nếu digest có SUM_NO_INDEX_USED hoặc SUM_SELECT_SCAN cao, xem:

- Điều kiện lọc có sargable không?
- Cột lọc có index phù hợp không?
- Biểu thức có bọc cột trong function khiến index khó sử dụng không?
- Kiểu dữ liệu hai vế so sánh có tương thích không?
- JOIN có index ở khóa nối không?
- Thống kê optimizer có đủ mới và phản ánh phân bố dữ liệu không?

Không thêm index chỉ vì một counter khác 0. Full scan có thể hợp lý khi bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu.

## 10. SQL động và thiết kế ứng dụng

Digest giúp phát hiện ứng dụng tạo quá nhiều cấu trúc SQL khác nhau.

### 10.1. Dùng placeholder cho giá trị

Prepared statement giúp tách cấu trúc SQL khỏi giá trị:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?;
~~~

Ứng dụng bind customer_id cho mỗi lần thực thi. Cách này giảm ghép chuỗi SQL, giúp tái sử dụng statement ở tầng client/driver và thường tạo nhóm digest dễ phân tích hơn.

### 10.2. Không bind identifier như bind value

Tên bảng, tên cột hoặc hướng sort thường không thể bind như một giá trị placeholder. Nếu ứng dụng tạo SQL bằng cách nối tên bảng động hoặc thêm điều kiện tùy tiện, có thể phát sinh nhiều digest khác nhau.

Hãy dùng allowlist cho identifier và giữ cấu trúc truy vấn ổn định khi có thể. Không nối trực tiếp dữ liệu đầu vào người dùng vào SQL.

### 10.3. Phân biệt query shape và business endpoint

Một endpoint có thể gọi nhiều digest; một digest cũng có thể được gọi từ nhiều endpoint. Digest summary không tự lưu route, tenant, user ID hoặc request ID. Muốn nối SQL với nghiệp vụ, bổ sung tracing hoặc metric ở tầng ứng dụng, có kiểm soát nhãn để tránh cardinality quá lớn.

## 11. Bảo mật và quyền truy cập số liệu

Performance Schema chứa thông tin về cấu trúc SQL, schema, tên bảng/cột và thống kê hoạt động. Dù literal thường được chuẩn hóa, digest text vẫn có thể tiết lộ tên đối tượng và logic nghiệp vụ.

Nguyên tắc:

- Chỉ cấp quyền SELECT cần thiết trên Performance Schema hoặc view sys cho nhóm vận hành.
- Không cấp quyền UPDATE setup_consumers/setup_instruments rộng rãi cho tài khoản ứng dụng.
- Chỉ reset summary khi có quyền và kế hoạch đo được duyệt.
- Không lưu snapshot chứa dữ liệu nhạy cảm vào nơi chia sẻ không kiểm soát.
- Hạn chế đưa DIGEST_TEXT thô vào nhãn metrics có cardinality cao.

Tài khoản ứng dụng thông thường không cần quyền đọc hoặc thay đổi cấu hình Performance Schema.

## 12. Sai lầm thường gặp khi đọc digest

| Sai lầm | Vì sao dễ kết luận sai | Cách xử lý |
|---|---|---|
| Chỉ xếp theo COUNT_STAR | Truy vấn nhanh có thể chạy nhiều nhưng ít tốn tài nguyên | Xem thêm tổng và trung bình latency |
| Chỉ xếp theo SUM_TIMER_WAIT | Nhóm chậm hiếm gặp có thể bị bỏ qua nếu mục tiêu là latency người dùng | Kết hợp avg, max và tần suất |
| Cho rằng cùng digest có cùng plan | Giá trị tham số và phân bố dữ liệu có thể khác | EXPLAIN với tham số đại diện |
| Coi SUM_NO_INDEX_USED > 0 là lỗi | Full scan có thể hợp lý với bảng nhỏ hoặc báo cáo | Kiểm tra plan, cardinality và rows |
| Coi DIGEST_TEXT là câu SQL nguyên bản | Literal đã được chuẩn hóa và text có thể bị giới hạn | Dùng log hoặc tracing để tìm câu thực tế |
| Coi summary là lịch sử từng lần chạy | Bảng chỉ lưu số tổng hợp | Bật history có kiểm soát hoặc dùng tracing |
| So tổng counter giữa hai thời điểm mà không tính delta | Counter tích lũy từ startup/reset | Chụp snapshot và tính chênh lệch |
| Reset summary để làm sạch dashboard liên tục | Mất baseline và ảnh hưởng toàn server | Lưu snapshot, reset trong cửa sổ đo được duyệt |
| Bỏ qua hàng DIGEST IS NULL | Có thể bỏ sót tình trạng digest capacity đầy | Theo dõi digest NULL và cấu hình dung lượng |
| Bật mọi statement instrument không đánh giá overhead | Thu thập rộng có chi phí bộ nhớ và CPU | Bật có mục tiêu và theo dõi sau thay đổi |

## 13. Bài thực hành: tìm nhóm SQL tốn tài nguyên

Thực hiện trên MySQL 8.0 trong database lab hoặc staging. Không reset Performance Schema hay bật instrument diện rộng trên production chỉ để làm bài tập.

### 13.1. Kiểm tra Performance Schema

~~~sql
SHOW GLOBAL VARIABLES LIKE 'performance_schema';

SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME = 'statements_digest';
~~~

Xác nhận Performance Schema và digest consumer đang hoạt động. Nếu môi trường không cho phép thay đổi, chỉ thực hiện phần đọc số liệu.

### 13.2. Tạo bảng lab

~~~sql
CREATE DATABASE IF NOT EXISTS observability_lab;
USE observability_lab;

CREATE TABLE lab_orders (
    order_id BIGINT NOT NULL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_lab_orders_customer (customer_id),
    KEY ix_lab_orders_status_date (status, created_at)
) ENGINE = InnoDB;
~~~

Nạp dữ liệu đại diện:

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_id,
    status,
    total_amount,
    created_at
)
VALUES
    (1, 101, 'PAID', 120.00, '2026-01-01 10:00:00'),
    (2, 101, 'PENDING', 80.00, '2026-01-02 10:00:00'),
    (3, 202, 'PAID', 250.00, '2026-01-03 10:00:00'),
    (4, 303, 'CANCELLED', 40.00, '2026-01-04 10:00:00');
~~~

### 13.3. Chạy cùng query shape với literal khác nhau

~~~sql
SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 101;

SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 202;

SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 303;
~~~

Các câu lệnh này có cùng query shape. Sau khi chạy, xem digest:

~~~sql
SELECT
    SCHEMA_NAME,
    DIGEST,
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 6) AS total_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'observability_lab'
  AND DIGEST IS NOT NULL
ORDER BY COUNT_STAR DESC;
~~~

Quan sát xem các lần chạy có được gom vào cùng một digest với customer_id được thay bằng placeholder hay không. Kết quả phụ thuộc consumer và instrument đang bật.

### 13.4. Tạo một query shape khác

~~~sql
SELECT order_id, total_amount
FROM lab_orders
WHERE status = 'PAID';
~~~

Câu này dùng cột status nên tạo cấu trúc digest khác. So sánh DIGEST và DIGEST_TEXT.

### 13.5. So sánh hai cách xếp hạng

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 6) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'observability_lab'
  AND DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC;
~~~

Chạy lại với ORDER BY COUNT_STAR DESC và ORDER BY AVG_TIMER_WAIT DESC. Giải thích vì sao danh sách ưu tiên có thể khác nhau.

### 13.6. Đọc plan của query shape

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM lab_orders
WHERE customer_id = 101;
~~~

Quan sát index được chọn. Sau đó thử một truy vấn không có index trực tiếp:

~~~sql
EXPLAIN
SELECT order_id, total_amount
FROM lab_orders
WHERE total_amount > 100;
~~~

Không kết luận về hiệu năng chỉ từ bảng nhỏ. Mục tiêu là liên kết digest với cấu trúc SQL và plan, không benchmark throughput bằng vài hàng lab.

### 13.7. Dọn database lab

~~~sql
DROP DATABASE observability_lab;
~~~

Chỉ xóa database lab vừa tạo. Không TRUNCATE digest summary trên server dùng chung để dọn kết quả bài tập.

## 14. Runbook điều tra một digest có chi phí cao

1. **Xác định mục tiêu:** giảm tổng thời gian, giảm latency mỗi lần, giảm lỗi hay giảm tài nguyên đọc.
2. **Chọn digest:** dùng COUNT_STAR, SUM_TIMER_WAIT, AVG_TIMER_WAIT, rows examined và các counter liên quan.
3. **Xác định phạm vi:** kiểm tra SCHEMA_NAME, FIRST_SEEN, LAST_SEEN và thời gian uptime/reset.
4. **Kiểm tra capacity:** xem hàng DIGEST IS NULL và performance_schema_digests_size.
5. **Đọc cấu trúc:** phân tích DIGEST_TEXT, bảng, JOIN, điều kiện và biểu thức.
6. **Tìm tham số đại diện:** dùng tracing hoặc log có kiểm soát để hiểu độ chọn lọc dữ liệu.
7. **Đọc execution plan:** EXPLAIN và khi an toàn, EXPLAIN ANALYZE.
8. **Xác định nguyên nhân:** index, statistics, scan, sort, temporary table, lock hoặc tần suất gọi.
9. **Đề xuất thay đổi:** sửa SQL, index, batching, caching hoặc cách gọi ở ứng dụng.
10. **Đo lại:** so snapshot digest trước và sau trên workload tương đương.
11. **Ghi nhận giới hạn:** nêu rõ dữ liệu đại diện, cửa sổ đo và thay đổi khác có thể ảnh hưởng kết quả.

## 15. Checklist triển khai monitoring

### Thu thập

- [ ] Performance Schema đang bật.
- [ ] statements_digest consumer đang được bật.
- [ ] Statement instruments cần thiết được bật và timing phù hợp.
- [ ] Đã xác nhận dung lượng digest đủ cho số query shape.
- [ ] Đã kiểm tra độ dài digest text.

### Phân tích

- [ ] Có top theo tổng latency.
- [ ] Có top theo số lần chạy.
- [ ] Có top theo average/max latency.
- [ ] Theo dõi rows examined và rows sent.
- [ ] Theo dõi errors, warnings, temporary disk tables và scan.
- [ ] Có cách phát hiện digest NULL.
- [ ] Counter được phân tích theo snapshot/delta khi cần cửa sổ thời gian.

### Vận hành

- [ ] Dashboard không coi summary là lịch sử từng lần chạy.
- [ ] Reset summary có phê duyệt và có snapshot trước đó.
- [ ] Digest text được bảo vệ theo quyền truy cập.
- [ ] Metrics không tạo cardinality quá lớn.
- [ ] Query plan được kiểm tra bằng tham số đại diện.
- [ ] Kết quả sau tối ưu được xác nhận trên workload tương đương.

## 16. Nguyên tắc cần ghi nhớ

- Statement digest chuẩn hóa cấu trúc SQL để gom các câu lệnh có literal khác nhau.
- DIGEST là mã nhận diện; DIGEST_TEXT là dạng SQL đã chuẩn hóa để đọc.
- Summary table nhóm theo schema và digest; cùng digest không có nghĩa mọi lần chạy có cùng plan hoặc latency.
- COUNT_STAR đo tần suất; SUM_TIMER_WAIT đo tổng thời gian; AVG_TIMER_WAIT đo trung bình mỗi lần.
- Timer của Performance Schema dùng picosecond; chia cho 10^12 để đổi sang giây.
- Rows examined, rows sent, errors, warnings, temporary disk tables và no-index counters giúp tìm hướng điều tra.
- Performance Schema và statements_digest consumer phải hoạt động thì digest mới được thu thập.
- Digest summary là số liệu tổng hợp tích lũy, không phải lịch sử mọi lần chạy hoặc time series.
- Hàng DIGEST IS NULL có thể báo hiệu số query shape vượt dung lượng digest.
- max_digest_length, performance_schema_max_digest_length và performance_schema_digests_size ảnh hưởng khả năng lưu/nhận diện digest; kiểm tra phiên bản trước khi thay đổi.
- Reset summary bằng TRUNCATE làm mất baseline thống kê; lưu snapshot và phối hợp trước khi thực hiện.
- Dùng digest để chọn nhóm đáng điều tra, sau đó dùng EXPLAIN, EXPLAIN ANALYZE, log và tracing để xác định nguyên nhân.
- Không thêm index chỉ vì một counter báo full scan; đánh giá selectivity, kích thước bảng và workload.
- Bảo vệ DIGEST_TEXT và quyền đọc Performance Schema như dữ liệu vận hành nội bộ.

Statement digest biến một lượng lớn câu SQL thành các nhóm có thể so sánh và ưu tiên. Khi đọc đúng các chỉ số, người vận hành biết nên tối ưu nhóm truy vấn nào trước, liệu vấn đề đến từ tần suất hay chi phí mỗi lần chạy, và cần kiểm tra plan ở đâu. Kết hợp digest với snapshot theo thời gian, execution plan và tracing ứng dụng sẽ tạo được vòng quan sát hiệu năng có thể kiểm chứng sau mỗi thay đổi.
