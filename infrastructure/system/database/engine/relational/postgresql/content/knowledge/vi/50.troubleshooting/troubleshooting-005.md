# Tăng CPU, tràn bộ nhớ và truy vấn sinh nhiều tệp tạm

Một truy vấn PostgreSQL có thể làm CPU tăng cao, khiến máy chủ thiếu RAM hoặc tạo ra rất nhiều tệp tạm trên đĩa. Ba hiện tượng này thường liên quan đến cùng một kế hoạch thực thi: truy vấn đọc quá nhiều hàng, phải sắp xếp hoặc nối tập dữ liệu lớn, và không thể giữ toàn bộ dữ liệu trung gian trong bộ nhớ. Tuy vậy, mỗi hiện tượng cần được chẩn đoán riêng. CPU cao không nhất thiết là thiếu RAM; tệp tạm tăng không nhất thiết là ổ đĩa bị lỗi; và một truy vấn đang ở trạng thái active cũng chưa chắc đang sử dụng CPU.

Bài học này trình bày cách nhận diện triệu chứng, tìm truy vấn gây tải, đọc kế hoạch thực thi, hiểu các giới hạn bộ nhớ và xử lý tệp tạm. Mục tiêu là xác định đúng nút thắt trước khi thay đổi cấu hình hoặc cấu trúc truy vấn.

## 1. Nhận diện ba nhóm sự cố

### CPU tăng cao

CPU tăng cao thường xuất hiện dưới các dấu hiệu:

- Tiến trình PostgreSQL chiếm nhiều CPU trong top, htop hoặc công cụ giám sát máy chủ.
- Thời gian phản hồi của nhiều truy vấn cùng tăng, dù dung lượng dữ liệu và số người dùng không thay đổi nhiều.
- Một hoặc một vài backend PostgreSQL sử dụng CPU liên tục.
- Các truy vấn có nhiều phép nối, sắp xếp, gom nhóm, biểu thức tính toán hoặc quét lượng dữ liệu lớn.

Một truy vấn có thời gian thực thi dài chưa chắc tiêu thụ nhiều CPU. Truy vấn có thể đang chờ khóa, chờ đọc đĩa hoặc chờ tài nguyên khác. Vì vậy, cần kết hợp số liệu PostgreSQL với số liệu hệ điều hành và thông tin chờ của backend.

### Bộ nhớ bị cạn

Sự cố bộ nhớ có thể biểu hiện qua:

- Hệ điều hành bắt đầu sử dụng swap nhiều, độ trễ tăng rõ rệt.
- Container hoặc máy ảo chạm giới hạn RAM.
- Kernel hoặc hệ điều phối container kết thúc tiến trình do OOM (Out Of Memory).
- PostgreSQL ghi lỗi cấp phát bộ nhớ hoặc các truy vấn thất bại khi xử lý tập dữ liệu lớn.
- Máy chủ vẫn hoạt động nhưng nhiều truy vấn đồng thời trở nên chậm vì phải tranh chấp bộ nhớ và I/O.

Không nên mặc định rằng PostgreSQL chỉ dùng RAM bằng giá trị shared_buffers. PostgreSQL còn có bộ nhớ riêng cho từng backend, bộ nhớ cho từng thao tác sort/hash, bộ nhớ phục vụ bảo trì, worker song song và các tiến trình khác trên máy chủ.

### Tệp tạm tăng nhanh

PostgreSQL có thể ghi dữ liệu trung gian ra đĩa khi một thao tác của truy vấn cần nhiều bộ nhớ hơn giới hạn cho phép. Các thao tác thường gặp gồm:

- ORDER BY hoặc các bước sort trong kế hoạch thực thi.
- GROUP BY, DISTINCT và các phép tổng hợp.
- Hash join và hash aggregate.
- Một số bước materialize hoặc xử lý tập kết quả trung gian.
- Truy vấn có nhiều bước xử lý dữ liệu lớn trước khi trả kết quả.

Các tệp này thường được gọi là temporary files hoặc temp files. Chúng khác với bảng tạm do ứng dụng tạo bằng CREATE TEMP TABLE. Chúng cũng khác với temp_buffers, vốn là bộ đệm dùng cho các bảng tạm tường minh.

Khi một thao tác sort hoặc hash không đủ bộ nhớ, PostgreSQL có thể chia dữ liệu thành nhiều phần, ghi các phần đó ra đĩa rồi đọc lại trong các bước tiếp theo. Cơ chế này giúp truy vấn tiếp tục chạy mà không cần giữ toàn bộ dữ liệu trong RAM, nhưng có thể làm tăng I/O, thời gian phản hồi và dung lượng đĩa sử dụng.

## 2. Hiểu cách PostgreSQL sử dụng tài nguyên

### CPU, RAM và đĩa có quan hệ với nhau

Một truy vấn có thể đi qua nhiều bước:

1. Đọc các hàng từ bảng hoặc chỉ mục.
2. Lọc hàng theo điều kiện WHERE.
3. Nối các tập dữ liệu.
4. Sắp xếp hoặc gom nhóm.
5. Tạo kết quả cuối cùng và gửi về client.

Nếu truy vấn đọc quá nhiều hàng, CPU phải xử lý nhiều dữ liệu hơn. Nếu bước sort hoặc hash cần nhiều bộ nhớ, PostgreSQL có thể sử dụng temp files. Khi phải ghi và đọc lại dữ liệu trung gian, ổ đĩa chịu thêm tải và truy vấn kéo dài. Truy vấn kéo dài cũng có thể giữ kết nối và tài nguyên lâu hơn, làm tăng áp lực khi nhiều người dùng chạy đồng thời.

Do đó, một truy vấn kém hiệu quả có thể gây ra cả ba hiện tượng. Tuy nhiên, cần xác định bước nào đang gây ra tải chính thay vì tăng đồng loạt CPU, RAM hoặc dung lượng đĩa.

### Những vùng bộ nhớ quan trọng

| Tham số | Vai trò | Điều cần lưu ý |
| --- | --- | --- |
| shared_buffers | Bộ đệm dùng chung cho dữ liệu của PostgreSQL | Không đại diện cho toàn bộ RAM PostgreSQL sử dụng |
| work_mem | Giới hạn bộ nhớ cho từng thao tác sort hoặc hash trước khi phải dùng đĩa | Một truy vấn có thể có nhiều thao tác; nhiều backend có thể chạy đồng thời |
| hash_mem_multiplier | Hệ số nhân giới hạn bộ nhớ của các thao tác hash dựa trên work_mem | Kiểm tra giá trị thực tế trên phiên bản đang chạy |
| maintenance_work_mem | Bộ nhớ cho các thao tác bảo trì như VACUUM hoặc tạo chỉ mục | Không phải tham số chính để sửa sort của truy vấn thông thường |
| autovacuum_work_mem | Bộ nhớ cho worker autovacuum | Giá trị -1 có nghĩa là dùng maintenance_work_mem |
| temp_buffers | Bộ đệm cho bảng tạm tường minh trong một phiên | Không phải giới hạn bộ nhớ của sort/hash |
| effective_cache_size | Ước lượng bộ nhớ đệm mà planner có thể tận dụng | Chỉ là thông tin cho planner, không cấp phát RAM |

Điểm quan trọng nhất là work_mem không phải ngân sách cố định cho toàn bộ truy vấn hoặc toàn bộ máy chủ. Đây là giới hạn áp dụng cho từng thao tác cần bộ nhớ. Một kế hoạch có nhiều nút sort/hash có thể sử dụng nhiều phần ngân sách. Worker song song cũng có thể cần bộ nhớ riêng. Vì vậy, đặt work_mem quá cao ở cấp toàn hệ thống có thể khiến tổng nhu cầu RAM vượt quá khả năng của máy chủ khi tải đồng thời tăng.

Có thể hình dung áp lực bộ nhớ bằng công thức ước lượng sau:

~~~text
RAM cần thiết
≈ shared_buffers
  + bộ nhớ nền của các backend đang hoạt động
  + tổng bộ nhớ sort/hash của các truy vấn đồng thời
  + bộ nhớ của worker song song
  + bộ nhớ bảo trì/autovacuum
  + hệ điều hành và các dịch vụ khác
~~~

Đây chỉ là mô hình tư duy để nhận diện rủi ro, không phải công thức dự báo chính xác. work_mem được cấp phát khi thao tác cần dùng, không phải tất cả backend đều lập tức chiếm đủ giá trị cấu hình.

### Tệp tạm không đồng nghĩa với bảng tạm

Phân biệt ba khái niệm:

- **Temp files do executor tạo:** dữ liệu trung gian của sort, hash hoặc các bước xử lý truy vấn bị tràn ra đĩa.
- **Temporary tables:** bảng do phiên hoặc giao dịch tạo bằng CREATE TEMP TABLE; dữ liệu tồn tại theo vòng đời của bảng/phiên.
- **temp_buffers:** bộ đệm trong RAM dành cho temporary tables.

Tăng temp_buffers không giải quyết trực tiếp việc sort hoặc hash sinh nhiều temp files. Tăng work_mem có thể giảm spill của một số truy vấn, nhưng cũng làm tăng nguy cơ thiếu RAM khi có nhiều thao tác đồng thời.

## 3. Quy trình điều tra trước khi thay đổi cấu hình

### Bước 1: Ghi nhận phạm vi và thời điểm

Trước khi điều chỉnh, ghi lại:

- Thời điểm bắt đầu và kết thúc sự cố.
- CPU, RAM, swap và dung lượng trống của từng filesystem liên quan.
- Số kết nối PostgreSQL và số truy vấn đang chạy.
- Database, role, ứng dụng và loại truy vấn bị ảnh hưởng.
- Sự cố xuất hiện sau khi triển khai phiên bản ứng dụng, chạy batch, tạo báo cáo hay thay đổi dữ liệu nào.

Nếu có thể, đối chiếu với cùng khung giờ của ngày trước đó. Một đợt batch hoặc báo cáo định kỳ có thể tạo ra tải lặp lại, trong khi một truy vấn mới triển khai có thể làm tải tăng đột ngột.

### Bước 2: Xem các truy vấn đang hoạt động

Chạy truy vấn sau để xem backend đang thực thi và trạng thái chờ của chúng:

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start NULLS LAST;
~~~

Các cột cần chú ý:

- pid: mã tiến trình backend, dùng để đối chiếu với tiến trình hệ điều hành.
- application_name: giúp nhận diện dịch vụ hoặc ứng dụng tạo kết nối.
- state: cho biết backend đang active, idle hoặc ở trạng thái khác.
- wait_event_type và wait_event: cho biết backend đang chờ loại sự kiện nào.
- elapsed: thời gian kể từ lúc truy vấn bắt đầu.
- query: câu lệnh đang chạy, có thể bị giới hạn theo quyền xem thống kê của người dùng hiện tại.

state = 'active' chỉ nói rằng backend đang xử lý một truy vấn. Nếu wait_event_type có giá trị, backend đang chờ sự kiện tương ứng. Nếu không có sự kiện chờ, truy vấn có thể đang thực thi trên CPU, nhưng vẫn cần đối chiếu với số liệu hệ điều hành để xác nhận.

Nếu nhiều truy vấn đang chờ khóa, xử lý nguyên nhân khóa trước. Tăng work_mem hoặc thêm CPU không giải quyết được việc một giao dịch đang giữ khóa quá lâu.

### Bước 3: Kiểm tra số liệu tệp tạm ở cấp database

View pg_stat_database cung cấp bộ đếm số tệp tạm và tổng dung lượng đã ghi:

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
~~~

- temp_files: số tệp tạm được tạo bởi các truy vấn.
- temp_bytes: tổng số byte đã ghi vào các tệp tạm.
- stats_reset: thời điểm thống kê được đặt lại, nếu có.

Đây là bộ đếm tích lũy từ lần reset thống kê gần nhất. temp_bytes không phải dung lượng tệp tạm đang chiếm trên đĩa tại đúng thời điểm truy vấn. Một truy vấn đã kết thúc có thể đã xóa tệp nhưng vẫn làm bộ đếm tăng. Vì vậy, hãy so sánh số liệu theo thời gian hoặc đối chiếu với log và filesystem.

### Bước 4: Tìm câu lệnh tạo nhiều temp blocks

Nếu đã cài pg_stat_statements, có thể xếp hạng các câu lệnh theo số block tạm đã ghi:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    temp_blks_read,
    temp_blks_written,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

temp_blks_read và temp_blks_written cho biết số block tạm đã đọc và ghi. Kích thước block thường là 8 KiB trong bản PostgreSQL phổ biến, nhưng phụ thuộc cách máy chủ được biên dịch.

Để tìm truy vấn chiếm tổng thời gian thực thi lớn, sắp xếp theo total_exec_time:

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    rows,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Không chỉ nhìn vào mean_exec_time. Một truy vấn mất 100 ms nhưng chạy hàng trăm nghìn lần có thể gây tổng tải lớn hơn truy vấn mất 20 giây nhưng chỉ chạy một lần mỗi ngày. Ngược lại, một truy vấn có mean_exec_time rất cao vẫn cần được điều tra nếu nó làm chậm một nghiệp vụ quan trọng.

total_exec_time là thời gian thực thi tích lũy, không phải số đo CPU thuần. Thời gian này có thể bao gồm thời gian chờ. Hãy kết hợp nó với wait events và số liệu CPU của hệ điều hành.

Nếu view chưa tồn tại, quản trị viên có thể bật pg_stat_statements bằng cách thêm thư viện vào shared_preload_libraries, giữ nguyên các thư viện khác đang có, rồi khởi động lại PostgreSQL. Sau khi máy chủ khởi động, tạo extension trong database cần theo dõi:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Việc thay đổi shared_preload_libraries cần restart, không chỉ reload cấu hình. Tên cột và khả năng thống kê có thể khác giữa các phiên bản PostgreSQL và phiên bản extension; hãy kiểm tra schema thực tế trước khi dùng truy vấn mẫu trên máy chủ cũ.

### Bước 5: Đối chiếu với hệ điều hành

PostgreSQL dùng nhiều tiến trình backend. Khi thấy CPU tăng, cần xác định PID nào đang sử dụng CPU và PID đó thuộc truy vấn nào.

Trên Linux, các công cụ thường dùng gồm:

~~~bash
top
htop
pidstat -p <PID> 1
vmstat 1
free -h
df -h
iostat -xz 1
~~~

- top hoặc htop: xem tiến trình PostgreSQL đang tiêu thụ CPU và RAM.
- pidstat: theo dõi mức sử dụng CPU của một PID theo thời gian.
- vmstat: xem run queue, swap và hoạt động bộ nhớ.
- free: xem RAM và swap còn khả dụng.
- df: kiểm tra dung lượng trống của filesystem.
- iostat: kiểm tra tải và độ trễ thiết bị lưu trữ.

Trong môi trường container, cần xem cả giới hạn CPU/RAM và số liệu throttling của container. Một container có thể bị giới hạn ở một phần CPU dù máy chủ vật lý còn nhiều lõi.

## 4. Phân tích và giảm tải CPU

### Xác định truy vấn thực sự gây tải

Kết hợp ba nguồn:

1. pg_stat_activity để xem truy vấn đang chạy và trạng thái chờ.
2. pg_stat_statements để tìm câu lệnh có tổng thời gian hoặc tần suất cao.
3. Công cụ hệ điều hành để đối chiếu PID và mức sử dụng CPU.

Sau khi chọn được câu lệnh nghi vấn, lấy kế hoạch thực thi:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMP '2026-01-01'
ORDER BY created_at DESC;
~~~

EXPLAIN ANALYZE thực thi câu lệnh để đo số liệu thực tế. Ví dụ trên là SELECT. Với INSERT, UPDATE, DELETE hoặc câu lệnh có tác dụng phụ, không chạy ANALYZE trên production nếu chưa đánh giá đầy đủ tác động; hãy dùng môi trường thử nghiệm hoặc một quy trình kiểm soát riêng.

Các chi tiết đáng chú ý trong kế hoạch:

- **Estimated rows và actual rows:** chênh lệch lớn có thể cho thấy thống kê không chính xác hoặc dữ liệu có phân bố lệch.
- **loops:** số lần một nút được thực thi. Một nút con có ít hàng mỗi lần nhưng chạy hàng trăm nghìn vòng vẫn có thể tạo tải lớn.
- **Rows Removed by Filter:** số hàng bị loại sau khi đọc. Giá trị lớn là tín hiệu cần xem lại điều kiện lọc và kế hoạch, nhưng không tự động chứng minh rằng cần tạo chỉ mục.
- **Buffers:** số block được đọc từ shared buffers hoặc phải đọc từ đĩa. Nhiều shared read có thể cho thấy truy vấn phải đọc nhiều dữ liệu hoặc dữ liệu chưa nằm trong cache.
- **Sort Method:** cho biết cách sort và có phải dùng đĩa hay không.
- **Hash Batches:** số batch của thao tác hash. Nhiều batch có thể cho thấy hash operation phải chia dữ liệu và sử dụng temp files.

Có thể bổ sung SETTINGS trên phiên bản hỗ trợ để xem các thiết lập planner khác mặc định:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...;
~~~

Không nên chỉ nhìn vào tổng thời gian ở cuối kế hoạch. Hãy tìm nút có nhiều hàng, nhiều vòng lặp, đọc nhiều block hoặc tạo temp read/write để hiểu chi phí phát sinh ở đâu.

### Những nguyên nhân CPU thường gặp

**Quét quá nhiều dữ liệu.** Điều kiện lọc không đủ chọn lọc, thiếu chỉ mục phù hợp hoặc truy vấn đọc nhiều cột/hàng hơn nhu cầu có thể khiến PostgreSQL phải xử lý lượng dữ liệu lớn. Tuy nhiên, sequential scan vẫn là lựa chọn tốt khi bảng nhỏ hoặc truy vấn cần phần lớn hàng của bảng.

**Nối bảng với số vòng lặp lớn.** Nested Loop có thể rất hiệu quả khi tập bên ngoài nhỏ và phía trong có đường truy cập phù hợp. Nếu phía trong bị quét lặp lại trên tập dữ liệu lớn, CPU và I/O có thể tăng mạnh. Hãy kiểm tra actual rows, loops, điều kiện join và chỉ mục của các cột liên quan.

**Sort và aggregate trên tập dữ liệu lớn.** ORDER BY, GROUP BY, DISTINCT và window functions có thể xử lý rất nhiều hàng. Nếu nghiệp vụ chỉ cần một phần kết quả, hãy xem có thể lọc sớm hơn, giới hạn kết quả bằng LIMIT hoặc tận dụng thứ tự từ một chỉ mục phù hợp hay không.

**Thống kê không phản ánh dữ liệu hiện tại.** Sau khi nạp hoặc thay đổi lượng dữ liệu lớn, planner có thể chọn kế hoạch không phù hợp nếu thống kê cũ. Có thể chạy ANALYZE trên bảng liên quan trong một thời điểm phù hợp:

~~~sql
ANALYZE orders;
~~~

Nếu nhiều cột có tương quan và planner ước lượng sai kết hợp điều kiện, extended statistics có thể hữu ích:

~~~sql
CREATE STATISTICS orders_status_region_stats (dependencies, mcv)
ON status, region_id
FROM orders;

ANALYZE orders;
~~~

Chỉ tạo thống kê mở rộng khi đã quan sát thấy sai lệch ước lượng liên quan đến các cột đó. Không cần tạo thống kê cho mọi tổ hợp cột.

**Truy vấn lặp quá nhiều.** Một truy vấn đơn lẻ có thể nhanh nhưng được gọi hàng chục nghìn lần do vòng lặp ở ứng dụng hoặc mô hình N+1. Hãy xem calls, tổng thời gian và cách ứng dụng gom nhóm thao tác.

**Song song hóa quá mức.** Parallel query có thể rút ngắn một truy vấn lớn, nhưng nhiều truy vấn song song cùng lúc cũng có thể làm CPU bão hòa và tăng nhu cầu bộ nhớ. Kiểm tra max_parallel_workers_per_gather cùng số worker thực tế trước khi tăng mức song song.

### Hướng xử lý CPU

- Viết điều kiện lọc rõ ràng và giới hạn tập dữ liệu càng sớm càng tốt, nếu vẫn giữ nguyên ý nghĩa nghiệp vụ.
- Chọn các cột cần dùng thay vì đọc toàn bộ hàng không cần thiết.
- Kiểm tra chỉ mục theo điều kiện lọc, điều kiện join và thứ tự sắp xếp thực tế. Tránh tạo chỉ mục chỉ vì thấy một cột xuất hiện trong WHERE.
- Kiểm tra kiểu dữ liệu và phép biến đổi trên cột lọc. Ép kiểu hoặc gọi hàm lên cột có thể khiến chỉ mục hiện có không được sử dụng như mong đợi.
- Xem lại join cardinality và điều kiện join để tránh nhân bản hàng ngoài ý muốn.
- Giảm tần suất gọi truy vấn lặp ở tầng ứng dụng khi có thể dùng batch hoặc truy vấn tổng hợp.
- Kiểm tra thống kê bằng ANALYZE khi dữ liệu đã thay đổi đáng kể.
- Điều chỉnh mức song song theo tải tổng thể, không chỉ theo kết quả của một truy vấn chạy riêng lẻ.

Sau mỗi thay đổi, chạy lại kế hoạch và so sánh số hàng thực tế, loops, buffers, temp blocks và thời gian. Một chỉ mục mới có thể cải thiện một truy vấn nhưng làm tăng dung lượng lưu trữ và chi phí ghi của các thao tác khác.

## 5. Xử lý áp lực bộ nhớ

### Kiểm tra cấu hình đang có hiệu lực

Không suy đoán giá trị cấu hình từ một file mẫu. Hãy đọc giá trị mà instance đang sử dụng:

~~~sql
SHOW shared_buffers;
SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW maintenance_work_mem;
SHOW autovacuum_work_mem;
SHOW temp_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
SHOW effective_cache_size;
~~~

Một số tham số chỉ có ở các phiên bản PostgreSQL nhất định. Nếu lệnh SHOW báo không tồn tại, kiểm tra phiên bản máy chủ và tài liệu tương ứng trước khi áp dụng ví dụ.

### Điều chỉnh work_mem có kiểm soát

Khi kế hoạch cho thấy một sort/hash operation bị spill, có thể thử tăng work_mem cho đúng phiên hoặc đúng truy vấn. Ví dụ:

~~~sql
BEGIN;
SET LOCAL work_mem = '128MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM ...
WHERE ...;

ROLLBACK;
~~~

SET LOCAL chỉ có hiệu lực trong giao dịch hiện tại và tự hết hiệu lực khi giao dịch kết thúc. Ví dụ trên phù hợp để thử một câu lệnh đọc. Nếu câu lệnh cần đánh giá có tác dụng phụ, không dùng EXPLAIN ANALYZE theo cách này trên production.

Sau khi thử, kiểm tra:

- Sort có còn dùng external merge hay không.
- Hash operation có giảm số batch hay không.
- Temp blocks đọc/ghi có giảm hay không.
- Thời gian truy vấn có cải thiện không.
- Tổng RAM và tải của các truy vấn khác có còn trong giới hạn an toàn không.

Không tăng work_mem toàn cục chỉ vì một truy vấn cần nhiều bộ nhớ. Nếu tăng ở cấp role hoặc database, tất cả truy vấn phù hợp với role/database đó có thể được hưởng giá trị mới trong các phiên kết nối tiếp theo. Một mức cao có thể an toàn khi chỉ có một truy vấn chạy thử nhưng nguy hiểm khi hàng chục truy vấn đồng thời thực thi nhiều sort/hash operation.

### Kiểm tra hash memory và truy vấn song song

hash_mem_multiplier quyết định giới hạn bộ nhớ hash dựa trên work_mem. Giá trị mặc định có thể thay đổi theo phiên bản, vì vậy hãy dùng SHOW hash_mem_multiplier để kiểm tra.

Nếu Hash Batches lớn, có thể thử điều chỉnh work_mem hoặc hash_mem_multiplier cho phiên thử nghiệm, nhưng trước tiên vẫn cần xác minh số hàng đầu vào và chất lượng kế hoạch. Một hash join nhận quá nhiều hàng do điều kiện join hoặc ước lượng sai sẽ tiếp tục tốn tài nguyên dù tăng bộ nhớ.

Worker song song cũng làm tăng tổng bộ nhớ có thể sử dụng. Trong một phiên thử nghiệm, có thể so sánh kế hoạch khi tắt parallel query:

~~~sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 0;
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
ROLLBACK;
~~~

Đây là phép thử so sánh, không phải khuyến nghị tắt parallel query cho toàn hệ thống. Nếu kế hoạch không song song ổn định hơn dưới tải đồng thời, hãy xem lại số worker và số truy vấn chạy song song cùng lúc.

### Kiểm soát số kết nối và hoạt động bảo trì

Mỗi backend có chi phí bộ nhớ nền. Số kết nối quá lớn có thể làm áp lực RAM tăng ngay cả khi không phải tất cả kết nối đều chạy truy vấn nặng. Với ứng dụng có nhiều kết nối ngắn, cân nhắc connection pool như PgBouncer và đặt giới hạn kết nối phù hợp.

Không quên các tác vụ bảo trì:

- CREATE INDEX và VACUUM có thể sử dụng maintenance_work_mem.
- Autovacuum worker có thể dùng autovacuum_work_mem, hoặc kế thừa maintenance_work_mem khi giá trị là -1.
- Nhiều tác vụ bảo trì chạy đồng thời cũng tạo ra nhu cầu bộ nhớ và I/O.

Nếu đang điều tra một đợt thiếu RAM, hãy ghi nhận số autovacuum worker và tác vụ bảo trì đang chạy trước khi thay đổi các tham số.

### Xem memory context khi cần điều tra sâu

Trên các phiên bản có view pg_backend_memory_contexts, có thể xem phân bố bộ nhớ của chính backend đang chạy câu lệnh:

~~~sql
SELECT
    name,
    parent,
    level,
    total_bytes,
    free_bytes,
    used_bytes
FROM pg_backend_memory_contexts
ORDER BY used_bytes DESC
LIMIT 20;
~~~

View này phản ánh backend thực thi câu lệnh xem view; nó không tự động hiển thị bộ nhớ của mọi backend khác. Nếu cần phân tích backend khác, sử dụng cơ chế chẩn đoán phù hợp với phiên bản và quyền quản trị, đồng thời cân nhắc lượng log có thể phát sinh.

## 6. Xử lý truy vấn tạo nhiều tệp tạm

### Bật log để biết tệp tạm thuộc truy vấn nào

log_temp_files cho phép PostgreSQL ghi log khi một tệp tạm được xóa. Giá trị -1 tắt log, 0 ghi mọi tệp và một giá trị dương chỉ ghi tệp có kích thước từ ngưỡng đó trở lên.

Ví dụ cấu hình ghi các tệp tạm từ 64 MB:

~~~conf
log_temp_files = 64MB
~~~

Tham số này có thể được nạp lại bằng reload cấu hình. Quản trị viên có thể dùng:

~~~sql
SELECT pg_reload_conf();
~~~

Việc thay đổi cấu hình cần quyền phù hợp và phải tuân theo cách quản lý cấu hình của môi trường. Không ghi đè danh sách shared_preload_libraries hoặc các thiết lập khác khi chỉ muốn bổ sung một tham số.

Log thường ghi kích thước tệp và thông tin tiến trình. Kết hợp PID, thời điểm và truy vấn trong log với pg_stat_activity hoặc log truy vấn để xác định workload liên quan. Nếu đặt ngưỡng bằng 0 trên hệ thống tải lớn, số lượng log có thể tăng nhanh; hãy chọn ngưỡng phù hợp và theo dõi dung lượng log.

### Đọc dấu hiệu spill trong EXPLAIN

Ví dụ một nút Sort có thể hiển thị:

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: 51200kB
  Buffers: shared hit=..., read=..., temp read=6400 written=6410
~~~

external merge cho biết thao tác sort đã dùng đĩa. Disk là dung lượng tạm mà sort báo cáo trong kế hoạch. temp read và temp written thể hiện hoạt động đọc/ghi block tạm.

Một Hash node có thể hiển thị:

~~~text
Hash
  Buckets: 131072  Batches: 8  Memory Usage: ...
~~~

Batches lớn hơn 1 cho thấy hash operation chia dữ liệu thành nhiều batch. Đây là tín hiệu cần xem lại bộ nhớ dành cho hash, số hàng đầu vào và kế hoạch join. Không phải cứ có temp blocks là phải tăng work_mem; có thể truy vấn đang xử lý nhiều dữ liệu không cần thiết.

### Giảm dữ liệu trung gian trước khi tăng giới hạn

Các hướng xử lý thường hiệu quả:

1. Lọc hàng sớm hơn nếu điều kiện lọc có thể áp dụng trước bước sort/join mà không thay đổi kết quả.
2. Chỉ chọn các cột thực sự cần thiết, tránh mang theo dữ liệu rộng qua các bước trung gian.
3. Xem lại ORDER BY, DISTINCT, GROUP BY và window functions để loại bỏ thao tác không cần thiết.
4. Kiểm tra join có làm nhân bản hàng hay không; sửa điều kiện join nếu sai về nghiệp vụ.
5. Kiểm tra chỉ mục có thể cung cấp thứ tự cần thiết cho truy vấn hay không.
6. Cập nhật thống kê nếu planner ước lượng sai số hàng.
7. Chỉ sau đó mới thử tăng work_mem có kiểm soát cho workload phù hợp.

Ví dụ, truy vấn sau cần sắp xếp tất cả đơn hàng của một tenant:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC;
~~~

Nếu nghiệp vụ chỉ cần 50 đơn gần nhất, giới hạn kết quả có thể giảm đáng kể dữ liệu phải trả về:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

Một chỉ mục ghép bắt đầu bằng tenant_id và tiếp theo là created_at có thể hỗ trợ điều kiện lọc và thứ tự trên, tùy kiểu dữ liệu, hướng sắp xếp, điều kiện truy vấn và kế hoạch mà planner chọn:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_created_at
ON orders (tenant_id, created_at DESC);
~~~

Đây chỉ là ví dụ minh họa, không phải chỉ mục nên tạo tự động cho mọi bảng. Trước khi tạo, xem xét kích thước bảng, tần suất ghi, chỉ mục đã có, mức chọn lọc và kế hoạch thực thi. CREATE INDEX CONCURRENTLY tránh khóa ghi dài như cách tạo chỉ mục thông thường trong nhiều tình huống, nhưng vẫn tiêu thụ CPU, I/O và dung lượng đĩa; nó cũng có các giới hạn riêng.

### Giới hạn dung lượng tệp tạm theo backend

temp_file_limit giới hạn tổng dung lượng tệp tạm mà một tiến trình PostgreSQL có thể sử dụng tại một thời điểm. Đây là giới hạn theo process, không phải tổng dung lượng cho toàn instance và cũng không phải giới hạn riêng cho từng câu lệnh.

Ví dụ cấu hình giới hạn cho một role:

~~~sql
ALTER ROLE reporting_user SET temp_file_limit = '20GB';
~~~

Giá trị mới áp dụng cho các phiên kết nối sau khi cấu hình có hiệu lực. Khi backend vượt giới hạn, truy vấn có thể bị hủy với lỗi vượt temp_file_limit. Đây là hàng rào bảo vệ để một backend không sử dụng đĩa không giới hạn, không phải cách sửa nguyên nhân truy vấn spill. Đặt giới hạn quá thấp có thể làm các báo cáo hợp lệ thất bại.

Giới hạn này không áp dụng cho dung lượng của các temporary tables tường minh do ứng dụng tạo. Vòng đời và dung lượng của các bảng đó cần được quản lý theo phiên/giao dịch và logic ứng dụng.

### Dùng tablespace riêng cho dữ liệu tạm khi cần

temp_tablespaces có thể định hướng một số tệp tạm sang tablespace riêng. Cách này hữu ích khi hệ thống có thiết bị lưu trữ phù hợp và muốn tách I/O tạm khỏi nơi lưu dữ liệu chính.

Trước khi dùng, cần xác minh:

- Tablespace có đủ dung lượng và được giám sát độc lập.
- Thiết bị lưu trữ có hiệu năng phù hợp với workload.
- Quyền truy cập và chính sách backup/giám sát phù hợp.
- Việc chuyển tệp tạm không làm nghẽn một thiết bị khác.

Tách tablespace chỉ chuyển vị trí I/O. Nó không làm giảm số hàng cần sort/hash và không loại bỏ chi phí xử lý của truy vấn.

## 7. Tình huống thực tế: báo cáo làm CPU và temp files tăng

Giả sử một ứng dụng báo cáo bắt đầu chạy chậm. CPU tăng, dung lượng filesystem chứa dữ liệu PostgreSQL giảm nhanh và nhiều người dùng cùng phàn nàn.

### Dấu hiệu ban đầu

Truy vấn báo cáo nối bảng orders với customers, lọc theo tenant, nhóm theo khách hàng rồi sắp xếp theo tổng tiền. Khi kiểm tra:

- pg_stat_activity cho thấy nhiều bản chạy cùng câu lệnh.
- pg_stat_statements cho thấy câu lệnh có nhiều temp_blks_written.
- pg_stat_database cho thấy temp_bytes tăng nhanh trong khoảng thời gian sự cố.
- EXPLAIN (ANALYZE, BUFFERS) hiển thị sort dùng external merge và hash join có nhiều batch.

Các dữ liệu này cho thấy truy vấn tạo tập trung gian lớn và phải spill ra đĩa. Chúng chưa đủ để kết luận rằng chỉ cần tăng work_mem.

### Điều tra nguyên nhân

Đọc kế hoạch từ đầu đến cuối và phát hiện:

- Điều kiện lọc tenant được áp dụng sau khi một tập dữ liệu lớn đã được đọc.
- Một phép join tạo ra nhiều hàng hơn dự kiến do điều kiện join chưa đầy đủ.
- Planner ước lượng số hàng thấp hơn nhiều so với số hàng thực tế.
- Ứng dụng chạy nhiều báo cáo đồng thời.

Có bốn vấn đề cần xử lý: sửa điều kiện join theo nghiệp vụ, kiểm tra đường truy cập cho bộ lọc tenant, cập nhật thống kê và kiểm soát số báo cáo chạy đồng thời.

### Thực hiện và đo lại

Sau khi sửa truy vấn và thống kê, chạy lại kế hoạch trong điều kiện tương đương. So sánh:

- Actual rows tại các nút join và sort.
- Số loops của các nút con.
- temp_blks_written và temp_blks_read.
- Thời gian thực thi và số lần gọi.
- CPU, I/O và mức sử dụng RAM khi nhiều báo cáo chạy cùng lúc.

Nếu sort vẫn spill nhưng tập dữ liệu đã hợp lý, có thể thử tăng work_mem trong phiên hoặc role chuyên chạy báo cáo. Thử tải đồng thời trước khi áp dụng rộng. Nếu một truy vấn chạy riêng lẻ tốt nhưng hệ thống vẫn thiếu RAM khi có nhiều báo cáo, cần giảm concurrency hoặc điều chỉnh ngân sách bộ nhớ cho workload.

## 8. Ứng phó khi đĩa hoặc bộ nhớ sắp cạn

### Khi filesystem chứa temp files gần đầy

1. Xác định filesystem và tablespace đang tăng dung lượng; không giả định mọi tệp tạm nằm trên cùng một mount.
2. Kiểm tra log log_temp_files, truy vấn đang chạy và PID liên quan.
3. Xác định truy vấn hoặc workload có thể tạm dừng mà không làm hỏng nghiệp vụ.
4. Nếu cần dừng một truy vấn đã xác minh, dùng pg_cancel_backend(pid) để yêu cầu hủy truy vấn:

~~~sql
SELECT pg_cancel_backend(12345);
~~~

5. Chỉ dùng pg_terminate_backend(pid) khi cần kết thúc cả phiên và đã hiểu tác động đến giao dịch của phiên đó:

~~~sql
SELECT pg_terminate_backend(12345);
~~~

Việc hủy truy vấn có thể khiến giao dịch bị rollback. Cần quyền phù hợp để gửi tín hiệu đến backend khác. Không chọn PID chỉ dựa trên mức CPU hoặc tên tiến trình; hãy đối chiếu với database, user, application và câu lệnh trước khi hành động.

Không xóa thủ công tệp trong thư mục dữ liệu PostgreSQL hoặc thư mục pgsql_tmp khi máy chủ đang chạy. PostgreSQL quản lý vòng đời các tệp này; xóa nhầm tệp đang được sử dụng có thể gây lỗi truy vấn hoặc làm hỏng hoạt động của máy chủ. Hãy xử lý workload thông qua PostgreSQL và để server dọn tệp theo cơ chế của nó.

### Khi máy chủ thiếu RAM hoặc bị OOM

- Kiểm tra RAM khả dụng, swap, giới hạn container và log OOM của hệ điều hành.
- Xác định backend và workload đang chạy; kiểm tra số kết nối, truy vấn song song, sort/hash operation và tác vụ bảo trì.
- Tạm giảm số workload nặng hoặc số truy vấn báo cáo chạy đồng thời nếu cần ổn định dịch vụ.
- Không tăng work_mem đồng loạt trong lúc máy chủ đã thiếu RAM.
- Sau khi ổn định, phân bổ lại ngân sách bộ nhớ và điều chỉnh connection pool, concurrency, worker song song hoặc tham số riêng cho workload.

temp_file_limit bảo vệ dung lượng đĩa của backend, không phải giới hạn RAM. statement_timeout có thể giới hạn thời gian chạy của truy vấn nhưng không thay thế việc sửa kế hoạch và kiểm soát tài nguyên. Nên áp dụng các giới hạn theo role/database hoặc nhóm workload sau khi hiểu yêu cầu nghiệp vụ, thay vì đặt một giá trị quá thấp cho mọi truy vấn.

## 9. Những cách xử lý dễ làm sự cố nặng hơn

| Cách làm | Vì sao rủi ro | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Tăng work_mem toàn cục thật cao | Nhiều sort/hash operation đồng thời có thể làm tổng RAM vượt giới hạn | Thử ở một phiên, đo dưới tải đồng thời rồi mới mở rộng |
| Tăng shared_buffers để chữa mọi truy vấn chậm | Không sửa được kế hoạch join, sort hoặc bộ lọc kém | Đọc kế hoạch và phân biệt cache miss với CPU, lock hoặc spill |
| Tăng temp_buffers để chữa sort spill | temp_buffers phục vụ bảng tạm tường minh | Kiểm tra work_mem, Hash Batches và Sort Method |
| Xóa tệp trong pgsql_tmp bằng tay | Có thể xóa tệp backend đang sử dụng | Xác định truy vấn và hủy workload qua PostgreSQL khi cần |
| Tạo chỉ mục cho mọi cột trong WHERE | Tăng dung lượng và chi phí ghi; planner có thể không cần chỉ mục | Dựa vào selectivity, kế hoạch và workload đọc/ghi |
| Tắt sequential scan trên toàn hệ thống | Có thể ép planner chọn kế hoạch tệ hơn | Sửa thống kê, truy vấn và chỉ mục; chỉ dùng thay đổi planner để chẩn đoán có kiểm soát |
| Chỉ xem truy vấn chậm nhất | Bỏ sót truy vấn chạy rất thường xuyên và gây tổng tải lớn | Xem cả calls, total time, mean time và temp blocks |
| Dùng VACUUM FULL để xử lý temp files | Đây là thao tác viết lại bảng, cần thêm đĩa và khóa mạnh | Xử lý truy vấn tạo temp files; chỉ vacuum theo nhu cầu quản lý dead tuples/bloat |

## 10. Bộ lệnh kiểm tra nhanh

Khi tiếp nhận sự cố, có thể dùng bộ truy vấn sau để thu thập bằng chứng ban đầu:

**Phiên bản và các tham số chính**

~~~sql
SELECT version();

SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW shared_buffers;
SHOW max_connections;
SHOW max_parallel_workers_per_gather;
SHOW temp_file_limit;
SHOW log_temp_files;
~~~

**Truy vấn đang chạy và trạng thái chờ**

~~~sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - query_start AS elapsed,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start NULLS LAST;
~~~

**Database có nhiều hoạt động ghi tệp tạm**

~~~sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_written,
    stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY temp_bytes DESC;
~~~

**Truy vấn có nhiều temp blocks**

~~~sql
SELECT
    queryid,
    calls,
    temp_blks_read,
    temp_blks_written,
    round(total_exec_time::numeric, 1) AS total_ms,
    round(mean_exec_time::numeric, 1) AS mean_ms,
    left(query, 300) AS query
FROM pg_stat_statements
ORDER BY temp_blks_written DESC
LIMIT 20;
~~~

Các truy vấn thống kê cần quyền xem phù hợp. Số liệu tích lũy có thể bị reset và có thể gộp nhiều lần thực thi của cùng một mẫu truy vấn. Hãy ghi nhận thời điểm reset, khoảng thời gian đo và tải đồng thời để tránh so sánh các số liệu không cùng điều kiện.

## 11. Trình tự xử lý nên áp dụng

Khi CPU tăng, RAM căng hoặc temp files tăng nhanh, hãy đi theo trình tự:

1. Xác nhận máy chủ, database, filesystem và khoảng thời gian bị ảnh hưởng.
2. Kiểm tra pg_stat_activity để phân biệt truy vấn đang chạy với truy vấn đang chờ.
3. Đối chiếu PID PostgreSQL với CPU, RAM, swap và I/O của hệ điều hành.
4. Dùng pg_stat_database và pg_stat_statements để tìm database và mẫu truy vấn tạo nhiều temp blocks.
5. Đọc EXPLAIN (ANALYZE, BUFFERS) trong điều kiện an toàn để tìm nút sort/hash/join gây tải.
6. Sửa nguyên nhân làm tăng dữ liệu đầu vào, sai cardinality, gọi lặp hoặc chạy quá nhiều workload đồng thời.
7. Thử thay đổi cấu hình trong phạm vi hẹp, đo lại cả khi chạy riêng và khi có tải đồng thời.
8. Bổ sung ngưỡng log, giới hạn tài nguyên và cảnh báo để phát hiện sự cố sớm hơn.

Một lần xử lý chỉ được xem là có hiệu quả khi truy vấn đạt yêu cầu nghiệp vụ, thời gian phản hồi cải thiện và mức sử dụng CPU, RAM, I/O, temp files ổn định dưới tải thực tế. Không đánh giá thành công chỉ bằng việc một truy vấn chạy nhanh hơn trong môi trường thử nghiệm có ít kết nối.
