# Bộ đếm tích lũy, khoảng đo và diễn giải dữ liệu sau restart/reset

Một giá trị counter lớn chưa đủ để kết luận MySQL đang chịu tải cao. Counter thường tích lũy từ một mốc bắt đầu, vì vậy số liệu 8 triệu câu SELECT có thể phản ánh một tuần hoạt động bình thường hoặc một phút tăng đột biến. Muốn hiểu tốc độ hiện tại, cần chụp ít nhất hai snapshot, biết chính xác khoảng thời gian giữa chúng và xác nhận cả hai snapshot thuộc cùng một chu kỳ hoạt động của máy chủ.

Cũng cần phân biệt counter với gauge và high-water mark. Counter tăng theo sự kiện; gauge mô tả trạng thái tại thời điểm lấy mẫu; high-water mark giữ giá trị lớn nhất đã quan sát kể từ một mốc reset. Mỗi loại cần cách diễn giải khác nhau. Sau restart, failover, FLUSH STATUS hoặc thao tác reset thống kê, một phép trừ đơn giản có thể tạo ra delta âm hoặc một tốc độ vô nghĩa.

Bài học thuộc chương **Quan sát hệ thống** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, kỹ năng đọc counter theo khoảng đo giúp phát hiện xu hướng tải, so sánh trước/sau thay đổi và tránh kết luận sai khi dữ liệu thống kê bị gián đoạn.

## 1. Ba nhóm số liệu cần phân biệt

Trước khi tính toán, hãy xác định một metric thuộc loại nào:

| Loại | Đặc điểm | Ví dụ MySQL | Cách đọc |
|---|---|---|---|
| Counter tích lũy | Tăng theo số sự kiện hoặc lượng công việc; thường không giảm trong cùng chu kỳ thống kê | Questions, Connections, Slow_queries, Bytes_received | Tính delta giữa hai snapshot rồi chia cho thời gian |
| Gauge | Giá trị trạng thái tại thời điểm lấy mẫu, có thể tăng hoặc giảm | Threads_connected, Threads_running, Innodb_buffer_pool_pages_data | Đọc giá trị hiện tại, xu hướng, min/max/percentile theo chuỗi thời gian |
| High-water mark | Giữ cực đại hoặc cực tiểu đã ghi nhận trong một khoảng | Max_used_connections | So sánh với giới hạn và thời điểm reset; không tính rate như counter |

Một counter như Questions bằng 2.000.000 chỉ cho biết tổng đã tích lũy đến thời điểm chụp. Nếu snapshot trước là 1.998.000 và snapshot sau là 2.000.000 trong 20 giây, delta là 2.000 và tốc độ trung bình là 100 câu hỏi/giây.

Một gauge như Threads_connected bằng 240 cho biết có 240 connection đang mở tại thời điểm đó. Không lấy 240 trừ số connection ở snapshot trước rồi gọi kết quả là số truy vấn/giây. Để hiểu tải kết nối, có thể theo dõi giá trị hiện tại, trung bình, cực đại và phân bố theo user/host.

High-water mark như Max_used_connections bằng 480 cho biết server từng đạt mức 480 connection đồng thời kể từ mốc thống kê gần nhất. Giá trị này không phải số connection hiện tại và cũng không cho biết thời điểm đỉnh xảy ra nếu không có hệ thống giám sát lưu lịch sử.

Một số metric có thể mang ý nghĩa khác tùy phiên bản hoặc nguồn thu thập. Hãy kiểm tra định nghĩa của từng biến trong tài liệu đúng phiên bản MySQL trước khi đưa vào dashboard hoặc cảnh báo.

## 2. Nguồn số liệu và phạm vi thống kê

MySQL cung cấp status variables ở phạm vi GLOBAL và SESSION.

~~~sql
SHOW GLOBAL STATUS;
SHOW SESSION STATUS;
~~~

- GLOBAL phản ánh thống kê ở cấp server theo định nghĩa của từng biến. Nhiều biến là tổng hợp hoạt động của các session.
- SESSION phản ánh hoạt động của connection hiện tại. Một session khác có thể có số liệu khác.
- Khi connection đóng, số liệu SESSION của connection đó không còn đọc được từ chính session đó.
- Performance Schema cung cấp các bảng như performance_schema.global_status và performance_schema.session_status để truy vấn status variables bằng SQL.

Ví dụ chỉ lấy một nhóm biến:

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Slow_queries'
);
~~~

Hoặc:

~~~sql
SELECT
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections',
    'Slow_queries'
)
ORDER BY VARIABLE_NAME;
~~~

Status variables thường được biểu diễn dưới dạng chuỗi trong Performance Schema. Khi tính toán, cần chuyển đổi kiểu một cách có chủ đích và kiểm tra giá trị có phải số hay không. Không nên ép kiểu mọi biến trong toàn bộ global_status nếu danh sách có cả giá trị không phải số.

Cần phân biệt status variables với summary tables của Performance Schema. Ví dụ events_statements_summary_by_digest tổng hợp số lần chạy, thời gian, dòng đọc và các thông tin theo digest. Các bảng summary có thể được reset theo cơ chế của Performance Schema, chẳng hạn TRUNCATE TABLE trên một số summary table. Việc reset summary không đồng nghĩa mọi status variable toàn server cũng được reset.

## 3. Counter phổ biến và ý nghĩa thực tế

Một số status variables hữu ích khi quan sát tải:

| Counter | Ý nghĩa tổng quát | Có thể suy ra |
|---|---|---|
| Questions | Số câu lệnh được client gửi và server xử lý theo định nghĩa của biến | Tốc độ câu lệnh client gửi |
| Queries | Số câu lệnh được server thực thi, bao gồm một số câu lệnh bên trong stored program | Mức hoạt động câu lệnh rộng hơn Questions |
| Connections | Số lần client thử kết nối đến server | Tốc độ kết nối mới, không phải số connection hiện tại |
| Slow_queries | Số câu lệnh bị ghi nhận là slow theo ngưỡng và điều kiện log | Tốc độ phát sinh truy vấn slow |
| Com_select | Số câu SELECT được thực thi | Xu hướng câu SELECT |
| Com_insert / Com_update / Com_delete | Số câu lệnh DML tương ứng | Tỷ trọng thao tác ghi ở mức statement |
| Bytes_received / Bytes_sent | Số byte server nhận/gửi theo định nghĩa biến | Tốc độ lưu lượng SQL protocol |
| Created_tmp_tables | Số internal temporary table được tạo | Tần suất tạo temporary table |
| Created_tmp_disk_tables | Số internal temporary table được tạo trên disk | Tín hiệu cần điều tra về temporary table trên disk |
| Innodb_buffer_pool_reads | Số lần InnoDB phải đọc page từ disk vào buffer pool | Xu hướng đọc vật lý |
| Innodb_buffer_pool_read_requests | Số logical read request đối với buffer pool | Quy mô yêu cầu đọc |
| Select_scan | Số lần thực hiện table scan cho SELECT | Tín hiệu truy vấn có thể quét nhiều dữ liệu |
| Select_full_join | Số join không dùng index theo định nghĩa status variable | Tín hiệu cần xem lại join access path |

Không dùng một counter riêng lẻ để kết luận nguyên nhân. Ví dụ Created_tmp_disk_tables tăng có thể là hành vi hợp lý của một workload cần sort/group lớn; cần so sánh delta với tổng temporary table, query digest, latency và kích thước dữ liệu. Innodb_buffer_pool_reads tăng không tự động có nghĩa buffer pool quá nhỏ; có thể do working set thay đổi hoặc workload đọc dữ liệu mới.

Questions và Queries không nên dùng thay thế cho nhau mà không hiểu định nghĩa. Questions tập trung vào câu lệnh client gửi; Queries có thể bao gồm câu lệnh được thực thi bên trong stored program. Nếu dùng chúng để tính QPS, ghi rõ loại đang đo.

## 4. Gauge và high-water mark thường gặp

Một số biến cần theo dõi như trạng thái hiện tại:

| Metric | Loại | Cách diễn giải |
|---|---|---|
| Threads_connected | Gauge | Connection đang mở |
| Threads_running | Gauge | Thread đang hoạt động, không ở trạng thái ngủ |
| Innodb_buffer_pool_pages_data | Gauge | Số page đang chứa dữ liệu trong buffer pool |
| Innodb_buffer_pool_pages_free | Gauge | Số page còn trống trong buffer pool |
| Innodb_row_lock_current_waits | Gauge | Số lần chờ khóa hàng đang diễn ra tại thời điểm lấy mẫu |
| Max_used_connections | High-water mark | Số connection đồng thời cao nhất kể từ mốc thống kê |

Gauge có thể tăng rồi giảm. Muốn đánh giá đỉnh tải, hệ thống giám sát phải lấy mẫu đủ thường xuyên và lưu max/min hoặc percentile theo cửa sổ. Nếu chỉ chạy truy vấn một lần lúc tải đã giảm, bạn có thể bỏ lỡ spike.

High-water mark cần được đọc cùng giới hạn tương ứng. Ví dụ:

~~~sql
SELECT
    @@global.max_connections AS configured_limit;
~~~

~~~sql
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
~~~

Nếu Max_used_connections gần max_connections, cần xem lịch sử connection và xu hướng. Nhưng nếu server vừa restart, high-water mark có thể thấp dù trước restart đã từng đạt đỉnh cao. Không so sánh giá trị sau restart với giá trị trước restart mà không lưu snapshot bên ngoài.

## 5. Chụp snapshot có timestamp và định danh máy chủ

Một snapshot có thể so sánh phải lưu tối thiểu:

- Thời điểm lấy mẫu, có độ chính xác đủ cho khoảng đo.
- server_uuid và hostname để xác định node.
- Uptime để phát hiện restart.
- Tên metric và giá trị metric.
- Phạm vi GLOBAL hay SESSION.
- Nguồn thu thập và phiên bản MySQL nếu dữ liệu được lưu lâu dài.

Truy vấn lấy snapshot nhanh:

~~~sql
SELECT
    NOW(6) AS captured_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version,
    VARIABLE_NAME,
    VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections',
    'Slow_queries',
    'Com_select',
    'Com_insert',
    'Com_update',
    'Com_delete',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
)
ORDER BY VARIABLE_NAME;
~~~

Truy vấn trên trả về nhiều dòng, mỗi dòng là một biến. Timestamp và server identity được lặp lại để hệ thống thu thập có thể gắn các giá trị vào cùng snapshot.

Nếu thu thập từ nhiều node, không gộp counter của các node vào một chuỗi duy nhất. Mỗi server_uuid phải có chuỗi thời gian riêng. Sau failover, endpoint có thể chuyển sang node khác với counter bắt đầu từ mốc riêng; hãy lưu cả node identity và vai trò.

Không chỉ lưu giá trị hiện tại trong dashboard. Hãy giữ raw snapshot hoặc time series đủ lâu để điều tra sau incident, so sánh cùng giờ/ngày và nhận biết xu hướng tăng dần.

## 6. Tính delta và rate từ hai snapshot

Với một counter tăng đơn điệu trong cùng chu kỳ thống kê:

- Delta = giá trị cuối - giá trị đầu.
- Elapsed seconds = thời điểm cuối - thời điểm đầu.
- Rate = delta / elapsed seconds.

Ví dụ:

| Thời điểm | Questions |
|---|---:|
| 10:00:00 | 1.200.000 |
| 10:00:30 | 1.201.500 |

Delta là 1.500 câu lệnh trong 30 giây. Rate trung bình là 50 câu lệnh/giây.

Công thức tổng quát:

\[
\text{Rate per second} =
\frac{\text{Counter}_{end} - \text{Counter}_{start}}
{\text{Elapsed seconds}}
\]

Rate là tốc độ trung bình trong toàn khoảng đo. Nó không cho biết phân bố trong từng giây. Một spike 2.000 QPS trong 2 giây có thể bị làm mờ khi tính trung bình trên cửa sổ 5 phút. Vì vậy, chọn khoảng đo theo mục tiêu: 1–10 giây cho phát hiện spike, 30–60 giây cho dashboard vận hành, nhiều phút/giờ cho xu hướng dài hạn. Đây chỉ là điểm bắt đầu; chi phí thu thập và độ nhạy của hệ thống cần được cân nhắc.

Ví dụ, nếu Bytes_received tăng 12.000.000 byte trong 60 giây:

\[
\text{Bytes per second} = \frac{12.000.000}{60}
\]

Kết quả là 200.000 byte/giây. Nếu muốn hiển thị MiB/giây, chia tiếp cho 1.048.576. Ghi rõ đơn vị là byte, KB, MB hay MiB để tránh hiểu sai.

Đừng tính rate cho gauge như Threads_connected. Với gauge, hãy lưu chuỗi giá trị rồi tính average, max, min hoặc percentile trong cửa sổ. Đừng tính rate cho high-water mark như Max_used_connections; hãy so sánh giá trị đỉnh với giới hạn và quan sát khi nó được reset.

## 7. Thực hành hai snapshot trong cùng một session

Có thể dùng temporary table để lưu hai snapshot trong cùng một session MySQL. Ví dụ sau chỉ lưu một nhóm counter số nguyên:

~~~sql
CREATE TEMPORARY TABLE status_samples (
    sample_label VARCHAR(10) NOT NULL,
    captured_at DATETIME(6) NOT NULL,
    server_uuid CHAR(36) NOT NULL,
    uptime_seconds BIGINT UNSIGNED NOT NULL,
    variable_name VARCHAR(64) NOT NULL,
    variable_value DECIMAL(30, 0) NOT NULL,
    PRIMARY KEY (sample_label, variable_name)
);
~~~

Chụp snapshot đầu:

~~~sql
SET @sample_label = 'before';
SET @sample_time = NOW(6);
SET @sample_uuid = @@server_uuid;
SET @sample_uptime = (
    SELECT CAST(VARIABLE_VALUE AS UNSIGNED)
    FROM performance_schema.global_status
    WHERE VARIABLE_NAME = 'Uptime'
);

INSERT INTO status_samples (
    sample_label,
    captured_at,
    server_uuid,
    uptime_seconds,
    variable_name,
    variable_value
)
SELECT
    @sample_label,
    @sample_time,
    @sample_uuid,
    @sample_uptime,
    VARIABLE_NAME,
    CAST(VARIABLE_VALUE AS DECIMAL(30, 0))
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
);
~~~

Chờ một khoảng thời gian có chủ đích, sau đó chụp snapshot thứ hai trong cùng session:

~~~sql
DO SLEEP(30);

SET @sample_label = 'after';
SET @sample_time = NOW(6);
SET @sample_uuid = @@server_uuid;
SET @sample_uptime = (
    SELECT CAST(VARIABLE_VALUE AS UNSIGNED)
    FROM performance_schema.global_status
    WHERE VARIABLE_NAME = 'Uptime'
);

INSERT INTO status_samples (
    sample_label,
    captured_at,
    server_uuid,
    uptime_seconds,
    variable_name,
    variable_value
)
SELECT
    @sample_label,
    @sample_time,
    @sample_uuid,
    @sample_uptime,
    VARIABLE_NAME,
    CAST(VARIABLE_VALUE AS DECIMAL(30, 0))
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Created_tmp_tables',
    'Created_tmp_disk_tables',
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests'
);
~~~

So sánh hai snapshot:

~~~sql
SELECT
    first_sample.variable_name,
    first_sample.variable_value AS start_value,
    last_sample.variable_value AS end_value,
    TIMESTAMPDIFF(
        MICROSECOND,
        first_sample.captured_at,
        last_sample.captured_at
    ) / 1000000 AS elapsed_seconds,
    last_sample.variable_value - first_sample.variable_value AS delta_value,
    ROUND(
        (last_sample.variable_value - first_sample.variable_value)
        /
        NULLIF(
            TIMESTAMPDIFF(
                MICROSECOND,
                first_sample.captured_at,
                last_sample.captured_at
            ) / 1000000,
            0
        ),
        2
    ) AS rate_per_second
FROM status_samples AS first_sample
JOIN status_samples AS last_sample
    ON last_sample.variable_name = first_sample.variable_name
WHERE first_sample.sample_label = 'before'
  AND last_sample.sample_label = 'after'
  AND first_sample.server_uuid = last_sample.server_uuid
  AND last_sample.uptime_seconds >= first_sample.uptime_seconds
  AND last_sample.variable_value >= first_sample.variable_value
ORDER BY first_sample.variable_name;
~~~

Điều kiện trong ví dụ chỉ trả ra các biến có server_uuid không đổi, Uptime không giảm và counter không giảm. Nếu một biến bị reset hoặc node đổi, dòng đó bị loại khỏi kết quả rate; cần kiểm tra nguyên nhân thay vì coi như delta bằng 0.

Truy vấn này là bài thực hành trong một session. Hệ thống giám sát production thường thu thập snapshot độc lập qua agent và lưu vào time-series database, kèm node identity, timestamp, labels và metadata. Không cần tạo temporary table trên mỗi lần scrape nếu nền tảng giám sát đã làm việc đó.

Kết thúc bài thực hành:

~~~sql
DROP TEMPORARY TABLE IF EXISTS status_samples;
~~~

## 8. Phát hiện restart, failover và reset counter

Không phải mọi counter đều giữ nguyên qua mọi sự kiện. Các tình huống cần nhận diện:

| Sự kiện | Dấu hiệu thường gặp | Cách xử lý khoảng đo |
|---|---|---|
| MySQL restart | Uptime giảm mạnh; error log có startup; process/server identity cần xác minh | Bắt đầu chu kỳ mới, không tính delta xuyên restart |
| Failover sang node khác | server_uuid hoặc hostname thay đổi; vai trò node thay đổi | Tách chuỗi metric theo node |
| FLUSH STATUS | Một số status counters có thể được reset hoặc cập nhật theo quy tắc riêng | Xem như ranh giới reset nếu counter giảm hoặc lịch sử có thao tác này |
| Reset Performance Schema summary | Summary table bị truncate/reset; count và timer có thể về 0 | Tạo mốc mới cho bảng summary bị reset |
| Reconfigure/disable instrumentation | Một số metric không còn được thu thập hoặc giá trị thay đổi | Ghi nhận thay đổi cấu hình và đánh dấu khoảng dữ liệu không tương đương |
| Counter rollover | Giá trị quay vòng khi vượt giới hạn kiểu lưu trữ, tùy metric | Dùng logic riêng nếu tài liệu xác nhận; nếu không, đánh dấu invalid |

Uptime là một chỉ báo hữu ích nhưng không đủ để nhận diện mọi reset. FLUSH STATUS có thể ảnh hưởng một số status variables mà không restart server. Reset Performance Schema summary tables cũng có thể xảy ra độc lập với uptime.

Khi phát hiện counter cuối nhỏ hơn counter đầu, không lấy delta âm rồi hiển thị rate âm. Đánh dấu khoảng đo là reset/invalid, chụp baseline mới và ghi lại nguyên nhân nếu biết.

Không dùng một câu lệnh FLUSH STATUS hoặc TRUNCATE summary table để làm sạch dashboard production. Reset thống kê làm mất mốc so sánh và có thể ảnh hưởng các công cụ giám sát khác. Chỉ reset khi có mục tiêu rõ ràng, quyền phù hợp, kế hoạch ghi nhận snapshot trước/sau và sự chấp thuận theo quy trình vận hành.

## 9. Phân biệt counter reset với workload giảm

Giả sử Questions ở snapshot đầu là 900.000 và snapshot sau là 120.000. Có ít nhất ba khả năng:

1. Server đã restart và counter bắt đầu lại.
2. Counter bị reset theo thao tác quản trị hoặc cơ chế thống kê.
3. Snapshot được lấy từ hai node khác nhau sau failover hoặc đổi endpoint.

Không kết luận workload giảm 780.000 câu lệnh. Kiểm tra:

~~~sql
SELECT
    NOW(6) AS checked_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version;
~~~

~~~sql
SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Queries',
    'Connections'
);
~~~

Đối chiếu timestamp và server_uuid trong hệ thống giám sát, error log, sự kiện deploy/failover và lịch thao tác quản trị. Nếu không thể xác định nguyên nhân, đánh dấu khoảng đo không hợp lệ và bắt đầu chu kỳ mới.

Một counter tăng chậm cũng không đồng nghĩa workload giảm. Có thể instrumentation bị tắt, agent mất quyền đọc, exporter ngừng scrape hoặc server đang ở node khác. Luôn theo dõi cả trạng thái thu thập metric và số lượng metric nhận được.

## 10. Diễn giải tỷ lệ từ các counter liên quan

Một số tỷ lệ có thể giúp nhận diện xu hướng nếu được tính trên cùng khoảng đo:

**Tỷ lệ internal temporary table tạo trên disk**

\[
\text{Disk temp ratio} =
\frac{\Delta Created\_tmp\_disk\_tables}
{\Delta Created\_tmp\_tables}
\]

Chỉ tính khi mẫu số lớn hơn 0. Tỷ lệ cao cần xem truy vấn GROUP BY, ORDER BY, DISTINCT, kích thước dữ liệu và cấu hình temporary table. Không coi mọi disk temporary table là lỗi.

**Tỷ lệ physical buffer pool read so với logical read request**

\[
\text{Read ratio} =
\frac{\Delta Innodb\_buffer\_pool\_reads}
{\Delta Innodb\_buffer\_pool\_read\_requests}
\]

Đây là chỉ báo tương đối của hoạt động đọc page từ disk so với logical read request trong cùng khoảng. Không phải phép đo đầy đủ latency hoặc cache efficiency của ứng dụng. Cần xem thêm I/O latency, working set và thời gian truy vấn.

**Tốc độ byte mạng**

\[
\text{Bytes per second} =
\frac{\Delta Bytes\_received \text{ hoặc } \Delta Bytes\_sent}
{\text{Elapsed seconds}}
\]

Dùng để theo dõi lưu lượng giao thức MySQL ở cấp server. Không đồng nhất với tổng lưu lượng mạng của host vì host có thể chạy nhiều dịch vụ và luồng mạng khác.

**Tỷ lệ truy vấn slow mới phát sinh**

\[
\text{Slow query rate} =
\frac{\Delta Slow\_queries}{\text{Elapsed seconds}}
\]

Biến này phụ thuộc long_query_time, log_queries_not_using_indexes và cấu hình liên quan. Khi thay đổi ngưỡng hoặc cấu hình slow log, chuỗi số liệu trước/sau không còn hoàn toàn tương đương; ghi lại thời điểm thay đổi.

Khi tính tỷ lệ, đảm bảo tử số và mẫu số thuộc cùng node, cùng khoảng thời gian và cùng chu kỳ thống kê. Nếu một counter reset giữa khoảng, loại bỏ toàn bộ phép tính phụ thuộc counter đó.

## 11. Đo tốc độ câu lệnh và lưu lượng theo workload

Có thể tính QPS gần đúng từ delta Questions:

\[
QPS = \frac{\Delta Questions}{\Delta t}
\]

Tuy nhiên, QPS không nói lên độ phức tạp của truy vấn. 1.000 SELECT đọc một dòng khác xa 1.000 SELECT quét hàng triệu dòng. Hãy kết hợp với rows examined, digest, latency và loại câu lệnh.

Tỷ trọng DML theo statement counter có thể khảo sát bằng snapshot Com_select, Com_insert, Com_update và Com_delete. Ví dụ:

- SELECT tăng nhanh có thể do request đọc hoặc polling.
- UPDATE/DELETE tăng đột biến có thể do batch, retry hoặc job.
- Connections tăng nhanh nhưng Questions không tăng tương ứng có thể cho thấy connection churn hoặc client tạo connection nhưng ít sử dụng.
- Bytes_sent tăng mạnh có thể do truy vấn trả tập dữ liệu lớn, dump/export hoặc ứng dụng tải nhiều dữ liệu.

Đây là tín hiệu điều tra, không phải kết luận nguyên nhân. Cần đối chiếu log ứng dụng, query digest, client host và lịch chạy job.

## 12. So sánh trước/sau thay đổi cấu hình hoặc triển khai

Khi đánh giá một thay đổi, đừng chỉ chụp một snapshot trước và một snapshot sau với khoảng thời gian không tương đương. Hãy giữ điều kiện so sánh:

1. Cùng node hoặc cùng vai trò và cùng topology.
2. Cùng loại workload và khoảng thời gian tương đương.
3. Cùng danh sách metric, cùng đơn vị và cùng phạm vi GLOBAL/SESSION.
4. Cùng cách thu thập và instrumentation.
5. Cùng định nghĩa thời gian, timezone và cửa sổ đo.
6. Ghi lại restart, failover, FLUSH STATUS, reset summary và thay đổi cấu hình.

Ví dụ, so sánh QPS trước/sau khi thêm index trong giờ cao điểm với giờ thấp điểm có thể gây kết luận sai. So sánh delta trong các cửa sổ có lượng request tương đương và xem thêm p95/p99 latency, rows examined, CPU, I/O và chi phí ghi.

Với thay đổi buffer pool, không chỉ xem Innodb_buffer_pool_reads. Hãy theo dõi memory pressure, page reads, latency, disk I/O và workload sau khi warm-up. Với thay đổi max_connections, xem cả connection peak, Threads_running, RAM và error rate.

Nếu thay đổi cần restart, chuỗi counter bị ngắt. Hãy chụp snapshot trước restart, đánh dấu sự kiện restart và bắt đầu baseline mới sau khi server ổn định. Không tính một delta xuyên qua hai uptime khác nhau.

## 13. Thiết kế dashboard cho counter và gauge

Một dashboard dễ đọc cần phân loại metric và thể hiện reset boundary:

| Panel | Dạng hiển thị | Nội dung |
|---|---|---|
| Query throughput | Rate line chart | Questions/s, Com_select/s, DML statements/s |
| Network throughput | Rate line chart | Bytes_received/s, Bytes_sent/s |
| Temporary table | Rate và ratio | disk temp tables/s, disk temp ratio |
| Buffer pool | Counter rate và gauge | physical reads/s, logical requests/s, pages free/data |
| Connections | Gauge và high-water | Threads_connected, Threads_running, Max_used_connections, max_connections |
| Slow queries | Rate | Slow_queries/s và thay đổi long_query_time |
| Node lifecycle | Event annotation | restart, failover, maintenance, FLUSH STATUS |
| Scrape health | Gauge/status | thời điểm scrape gần nhất, lỗi exporter, số metric nhận được |

Không vẽ counter tích lũy như một đường gauge nếu mục tiêu là xem tải tức thời. Đường counter luôn tăng có thể che mất spike và khiến người xem hiểu nhầm. Dùng rate/delta hoặc giữ một panel riêng cho tổng tích lũy.

Đánh dấu restart, failover và reset trên dashboard. Khi counter bắt đầu lại, hệ thống metric có thể tính rate âm hoặc spike giả nếu không biết reset. Một exporter tốt nên xử lý counter reset theo semantics của nguồn dữ liệu; người vận hành vẫn cần kiểm tra node identity và sự kiện lifecycle.

Với gauge, hiển thị giá trị hiện tại và percentile theo cửa sổ. Với high-water mark, có thể hiển thị mức đỉnh cùng giới hạn cấu hình. Với counter, hiển thị rate và tổng tích lũy ở panel riêng nếu cả hai đều hữu ích.

## 14. Cảnh báo dựa trên tốc độ và trạng thái reset

Alert cho counter nên dựa trên rate hoặc tỷ lệ trong cửa sổ, không dựa trên tổng tích lũy kể từ lúc khởi động. Ví dụ, Slow_queries = 50.000 có thể là bình thường sau nhiều ngày, nhưng tăng 500 trong một phút có thể bất thường so với baseline.

Một alert tốt cần:

- Metric có định nghĩa và đơn vị rõ ràng.
- Cửa sổ đo và điều kiện đủ dữ liệu.
- Xử lý reset/restart và node identity.
- Ngưỡng dựa trên baseline hoặc SLO.
- Thời gian duy trì để tránh báo động do spike ngắn không ảnh hưởng.
- Hành động tiếp theo và runbook liên kết.

Không phát cảnh báo rate âm. Nếu counter giảm, chuyển metric sang trạng thái unknown/reset và chờ đủ hai snapshot hợp lệ để tính lại. Không biến unknown thành 0 vì điều đó có thể che mất lỗi thu thập hoặc restart.

Với gauge như Threads_connected, alert theo giá trị hiện tại, tỷ lệ so với max_connections và tốc độ tiến đến giới hạn. Với high-water mark, cảnh báo khi đỉnh lịch sử đã sử dụng phần lớn giới hạn trong chu kỳ hiện tại, nhưng phải tính đến thời điểm restart hoặc reset.

## 15. Các lỗi diễn giải thường gặp

**Lấy counter hiện tại làm tốc độ.** Questions = 5 triệu không phải 5 triệu QPS. Cần delta và thời gian.

**Trừ hai snapshot từ hai node.** Counter của server_uuid khác nhau thuộc hai chuỗi độc lập. Tách dữ liệu theo node.

**Tính delta âm là workload giảm.** Giá trị giảm thường chỉ ra reset, restart, rollover hoặc thay đổi nguồn. Đánh dấu khoảng đo invalid.

**Bỏ qua Uptime.** Uptime giảm là tín hiệu restart. Ghi cả uptime và server identity trong snapshot.

**Cho rằng FLUSH STATUS reset tất cả metric giống nhau.** Các status variable và Performance Schema summary table có quy tắc reset riêng. Kiểm tra semantics của nguồn và biến cụ thể.

**Coi gauge là counter.** Threads_connected là số connection hiện tại. Không chia chênh lệch của nó cho thời gian để gọi là QPS.

**Coi Max_used_connections là connection hiện tại.** Đây là high-water mark. So sánh với max_connections và theo dõi mốc reset.

**Tính tỷ lệ với mẫu số bằng 0.** Không chia khi không có sự kiện trong khoảng. Trả về NULL/unknown hoặc bỏ phép tính.

**Dùng cửa sổ quá dài để phát hiện spike.** Rate trung bình dài có thể làm mờ sự cố ngắn. Chọn nhiều cửa sổ và đối chiếu chi phí thu thập.

**Không theo dõi scrape health.** Counter không tăng có thể do workload dừng hoặc exporter mất dữ liệu. Kiểm tra timestamp và trạng thái thu thập.

**Reset thống kê để làm dashboard đẹp.** Reset làm mất mốc so sánh và ảnh hưởng công cụ khác. Lưu snapshot trước và ghi event nếu reset là cần thiết.

## 16. Bài thực hành: phát hiện restart và tính rate hợp lệ

Dùng MySQL thử nghiệm hoặc môi trường chỉ đọc được phép quan sát. Không restart server hoặc FLUSH STATUS trên production để làm bài tập.

**Phần A — Lấy snapshot**

Chạy truy vấn sau hai lần, cách nhau khoảng 30 giây:

~~~sql
SELECT
    NOW(6) AS captured_at,
    @@hostname AS server_host,
    @@server_uuid AS server_uuid,
    VERSION() AS mysql_version;

SHOW GLOBAL STATUS
WHERE Variable_name IN (
    'Uptime',
    'Questions',
    'Connections',
    'Slow_queries',
    'Bytes_received',
    'Bytes_sent',
    'Threads_connected',
    'Threads_running',
    'Max_used_connections'
);
~~~

Ghi hai kết quả cùng timestamp. Phân loại từng biến thành counter, gauge hoặc high-water mark.

**Phần B — Tính delta**

Với Questions, Connections và Slow_queries, tính delta và rate/second. Với Bytes_received và Bytes_sent, tính byte/second. Với Threads_connected, so sánh hai giá trị như gauge. Với Max_used_connections, so sánh đỉnh với max_connections.

**Phần C — Kiểm tra tính hợp lệ**

So sánh server_uuid và Uptime. Nếu UUID đổi, node đổi. Nếu Uptime giảm, server restart. Nếu counter giảm nhưng Uptime không giảm, điều tra reset thống kê hoặc nguồn thu thập. Không đưa khoảng đó vào rate chart như một giá trị âm.

**Phần D — Viết quy tắc cảnh báo**

Chọn một counter, ví dụ Slow_queries. Viết điều kiện alert dựa trên rate trong cửa sổ, baseline, thời gian duy trì, reset behavior và hành động tiếp theo. Ghi rõ cách xử lý khi exporter không scrape được hoặc server vừa restart.

**Phần E — Báo cáo**

Viết một đoạn ngắn gồm metric, hai timestamp, server identity, delta, elapsed seconds, rate, phân loại metric và kết luận có đủ dữ liệu để so sánh hay không.

## 17. Checklist trước khi diễn giải một counter

- Metric này là counter, gauge hay high-water mark?
- Phạm vi GLOBAL hay SESSION?
- Định nghĩa và đơn vị có đúng với phiên bản MySQL đang chạy không?
- Hai snapshot có timestamp và elapsed time đáng tin cậy không?
- Cả hai có cùng server_uuid và cùng node không?
- Uptime có tăng liên tục hay có restart giữa khoảng đo?
- Có FLUSH STATUS, reset summary table hoặc thay đổi instrumentation không?
- Giá trị cuối có nhỏ hơn giá trị đầu không?
- Delta có không âm và phép tính có mẫu số hợp lệ không?
- Rate là trung bình trên cửa sổ bao lâu?
- Cửa sổ đo có che mất spike ngắn không?
- Có thể giải thích biến động bằng workload, batch, backup, deploy hoặc failover không?
- Có đối chiếu với latency, rows examined, CPU, I/O và replication không?
- Dashboard có đánh dấu reset boundary và scrape failure không?
- Alert có owner, baseline, điều kiện duy trì và runbook không?

Counter chỉ có ý nghĩa khi biết nó đã tích lũy từ lúc nào và trong phạm vi nào. Gauge cho biết trạng thái tại một thời điểm; high-water mark cho biết đỉnh trong một chu kỳ; counter cần hai snapshot hợp lệ để tính delta và rate. Khi gắn timestamp, server identity, uptime và reset event vào dữ liệu, bạn có thể phân biệt workload thật với thay đổi do restart/reset, so sánh các khoảng đo công bằng và xây dựng cảnh báo đáng tin cậy cho MySQL.
