# Đo tải đại diện, thay đổi từng yếu tố và kiểm tra hồi quy

Một truy vấn chạy nhanh trên vài trăm dòng dữ liệu chưa chứng minh MySQL sẽ đáp ứng tốt khi dữ liệu tăng lên hàng triệu dòng và nhiều giao dịch chạy đồng thời. Kết quả đo chỉ đáng tin khi tải thử phản ánh cách ứng dụng thực sự truy cập dữ liệu, môi trường được giữ ổn định và mỗi lần thử có thể so sánh với một mốc chuẩn.

Bài học này trình bày cách xây dựng tải đo đại diện, thay đổi từng yếu tố có kiểm soát và chạy lại bộ kiểm tra hiệu năng sau khi sửa SQL, index, cấu hình hoặc cách xử lý transaction. Mục tiêu là tìm ra cải thiện có thể lặp lại mà vẫn giữ đúng dữ liệu và hành vi của ứng dụng.

## 1. Xây dựng tải đo đại diện

Tải đo đại diện (representative workload) mô tả những thao tác MySQL mà ứng dụng thường thực hiện, cùng tần suất và điều kiện thực hiện của chúng. Trước khi chọn công cụ, hãy trả lời các câu hỏi sau:

- **Luồng nghiệp vụ nào tạo truy vấn?** Ví dụ: đăng nhập, tìm kiếm sản phẩm, tạo đơn hàng, cập nhật trạng thái và báo cáo.
- **Tỷ lệ đọc và ghi là bao nhiêu?** Phân biệt SELECT, INSERT, UPDATE, DELETE và các transaction gồm nhiều câu lệnh.
- **Truy vấn nào thường xuyên hoặc tốn tài nguyên?** Thu thập digest, tần suất thực thi, thời gian tổng, số dòng đọc và số dòng trả về.
- **Dữ liệu có hình dạng ra sao?** Dùng quy mô gần thực tế, phân bố giá trị, độ chọn lọc của điều kiện lọc, số lượng bản ghi liên quan và mức độ lệch dữ liệu. Một cột có phần lớn giá trị giống nhau sẽ có hành vi khác cột có giá trị phân bố đều.
- **Ứng dụng tạo tải như thế nào?** Ghi nhận số kết nối đồng thời, tốc độ gửi yêu cầu, kích thước batch, thời gian giữa các thao tác và thời lượng transaction.
- **Điều kiện cache là gì?** Phân biệt lần chạy lạnh sau khi khởi động hoặc nạp dữ liệu với các lần chạy ấm khi InnoDB Buffer Pool đã chứa phần lớn trang dữ liệu cần thiết.

Một bài đo chỉ gồm một câu SELECT lặp lại liên tục thường không đại diện cho ứng dụng có cả đọc, ghi, khóa và commit. Tương tự, dùng một bảng nhỏ vừa hoàn toàn trong RAM có thể che khuất độ trễ đọc đĩa khi dữ liệu thật lớn hơn Buffer Pool.

Nên xây dựng workload theo thứ tự:

1. Lấy danh sách luồng nghiệp vụ và truy vấn từ ứng dụng, log truy vấn đã khử dữ liệu nhạy cảm hoặc Performance Schema.
2. Nhóm truy vấn theo mẫu (digest), tham số và loại thao tác; xác định tỷ trọng của từng nhóm.
3. Tạo dữ liệu thử có quy mô và phân bố gần môi trường mục tiêu.
4. Tái hiện transaction boundary, mức đồng thời và nhịp gửi yêu cầu của ứng dụng.
5. Kiểm tra rằng workload tạo ra kết quả nghiệp vụ hợp lệ, không chỉ tạo ra QPS cao.

Có thể dùng **sysbench** để tạo mốc tải OLTP ban đầu. Với workload riêng của ứng dụng, hãy viết Lua script cho sysbench hoặc dùng công cụ phát lại tải phù hợp. Kịch bản mẫu có sẵn không thay thế được mô hình truy cập thực tế.

## 2. Chốt môi trường và mốc chuẩn

Trước khi đo, ghi lại các yếu tố có thể làm kết quả thay đổi:

| Nhóm | Thông tin cần ghi |
|---|---|
| MySQL | Phiên bản, engine, cấu hình hiệu lực, plugin và trạng thái Performance Schema |
| Máy chủ | CPU, RAM, loại lưu trữ, filesystem và giới hạn I/O |
| Dữ liệu | Kích thước, số dòng, schema, index, dữ liệu mẫu và cách khởi tạo |
| Ứng dụng | Phiên bản, connection pool, số worker và cấu hình timeout |
| Mạng | Độ trễ giữa ứng dụng và MySQL, vị trí máy chạy benchmark |
| Kịch bản | Mã workload, seed, tham số, số luồng, thời gian warm-up và thời gian đo |

Dùng cùng phiên bản MySQL, dataset, cấu hình, máy chạy tải và kịch bản giữa các lần so sánh. Nếu một yếu tố bắt buộc thay đổi, hãy ghi rõ và xem đó là một biến của thí nghiệm. Không so sánh hai lần chạy khi một lần dùng dữ liệu đã warm cache còn lần kia vừa khởi động, trừ khi mục tiêu chính là đo riêng hai trạng thái đó.

Mốc chuẩn (baseline) là kết quả đo trước khi thay đổi. Chạy thử để kiểm tra workload, cho hệ thống ổn định, sau đó thực hiện nhiều lượt đo độc lập. Ba lượt trở lên là điểm khởi đầu hữu ích; tăng số lượt nếu kết quả dao động lớn. Có thể luân phiên thứ tự chạy bản cũ và bản mới để giảm ảnh hưởng của nhiệt độ máy, tải nền hoặc biến động môi trường.

Tách rõ:

- **Warm-up:** thời gian để cache, connection pool và workload ổn định; không gộp vào số liệu đo chính.
- **Measurement window:** khoảng thời gian thu thập kết quả sau warm-up.
- **Cooldown/reset:** khôi phục trạng thái dữ liệu hoặc tài nguyên trước lượt tiếp theo khi kịch bản ghi làm thay đổi dữ liệu.

Đối với workload ghi, hãy chuẩn bị lại trạng thái dữ liệu hoặc dùng snapshot giống nhau cho từng lượt. Nếu lần chạy sau có thêm dữ liệu, index hoặc trạng thái transaction khác lần trước, kết quả không còn là phép so sánh cùng điều kiện.

## 3. Chọn chỉ số cần theo dõi

Không dùng riêng QPS hoặc TPS để kết luận. Throughput cao có thể đi cùng thời gian chờ dài và tỷ lệ lỗi tăng. Theo dõi đồng thời các nhóm sau:

| Nhóm chỉ số | Ý nghĩa |
|---|---|
| QPS / TPS | Số câu lệnh hoặc transaction hoàn thành mỗi giây |
| Latency p50, p95, p99 | Thời gian phản hồi ở trung vị và các đuôi phân phối; p95/p99 cho thấy trải nghiệm của yêu cầu chậm |
| Error / timeout | Lỗi SQL, deadlock, timeout và yêu cầu bị từ chối |
| CPU và RAM | Mức sử dụng CPU, áp lực bộ nhớ và hoạt động của Buffer Pool |
| Storage I/O | IOPS, throughput, độ trễ đọc/ghi và thời gian chờ I/O |
| InnoDB | Buffer Pool physical reads, row lock waits, redo activity và trạng thái checkpoint |
| SQL | Số dòng examined so với rows sent, full scan, temporary table và kế hoạch thực thi |
| Đồng thời | Threads running, số kết nối, lock wait và thời gian transaction |

Đo latency ở phía ứng dụng để bao gồm thời gian chờ trong connection pool, mạng và xử lý ứng dụng. Đồng thời đo tại MySQL để xác định thời gian nằm trong máy chủ. Hai phép đo này giúp phân biệt truy vấn chậm với yêu cầu phải chờ lấy kết nối hoặc truyền dữ liệu.

Với chỉ số dạng bộ đếm tích lũy trong MySQL, hãy lấy snapshot trước và sau mỗi lượt rồi tính phần chênh lệch. Không so sánh trực tiếp tổng từ lúc máy chủ khởi động nếu thời gian quan sát khác nhau. Cần ghi lại thời điểm và khoảng đo để diễn giải đúng.

## 4. Chạy một kịch bản có thể lặp lại

Ví dụ dưới đây dùng workload **oltp_read_write** của sysbench để tạo mốc kiểm tra trên môi trường thử nghiệm. Tài khoản benchmark chỉ nên có quyền cần thiết trên schema thử nghiệm.

Chuẩn bị dữ liệu:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto prepare
~~~

Chạy tải:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto run
~~~

Sau khi hoàn tất và lưu kết quả, có thể dọn dữ liệu benchmark:

~~~bash
sysbench oltp_read_write --mysql-host=127.0.0.1 --mysql-port=3306 --mysql-user=bench --mysql-password='<PASSWORD>' --mysql-db=bench --tables=16 --table-size=100000 --threads=32 --time=300 --report-interval=10 --rand-type=pareto cleanup
~~~

Thay thông tin kết nối và tham số bằng cấu hình của môi trường thử nghiệm. Không đưa mật khẩu thật vào tài liệu, log hoặc lịch sử lệnh dùng chung; dùng cơ chế cấp bí mật an toàn của môi trường. Tham số **--threads** mô phỏng số luồng chạy đồng thời, **--time** đặt thời lượng, còn **--report-interval** giúp quan sát biến động trong lúc chạy. Có thể thử nhiều mức đồng thời riêng biệt, chẳng hạn tải thấp, tải thường gặp và tải đỉnh đã quan sát.

Kết quả sysbench thường cung cấp throughput, latency trung bình và percentile, cùng số lỗi. Lưu toàn bộ đầu ra và cấu hình của lượt chạy. Với ứng dụng thực tế, bổ sung kịch bản có tham số truy vấn và ranh giới transaction giống ứng dụng; không suy ra năng lực production chỉ từ một bài OLTP tổng quát.

## 5. Quan sát truy vấn và tài nguyên MySQL

Performance Schema giúp tìm những mẫu câu lệnh tiêu tốn thời gian. Ví dụ, truy vấn sau xếp các digest theo tổng thời gian thực thi:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR AS executions,
    ROUND(SUM_TIMER_WAIT / 1e12, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1e9, 2) AS avg_ms,
    SUM_ROWS_EXAMINED AS rows_examined,
    SUM_ROWS_SENT AS rows_sent
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = 'appdb'
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 10;
~~~

Thay **appdb** bằng schema cần quan sát. Các bộ đếm trong bảng summary thường tích lũy từ khi MySQL khởi động hoặc từ lần reset thống kê gần nhất. Khi đo một lượt riêng, hãy ghi snapshot trước và sau rồi lấy chênh lệch. Kiểm tra Performance Schema và các consumer/instrument cần thiết đã được bật trước khi dựa vào số liệu.

Nếu schema **sys** có sẵn, view **sys.statement_analysis** cung cấp cách xem dễ đọc hơn:

~~~sql
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent,
    full_scans
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

Chú ý cả tổng thời gian lẫn thời gian trung bình. Một truy vấn trung bình nhanh nhưng chạy hàng triệu lần vẫn có thể tiêu thụ phần lớn tài nguyên. Ngược lại, một truy vấn hiếm có thời gian trung bình cao có thể cần được xử lý theo yêu cầu nghiệp vụ và mức độ ảnh hưởng.

Theo dõi thêm các bộ đếm phù hợp với giả thuyết, chẳng hạn **Threads_running**, **Innodb_buffer_pool_reads**, **Innodb_buffer_pool_read_requests**, **Innodb_row_lock_waits**, **Innodb_row_lock_time** và **Created_tmp_disk_tables**. Lấy chênh lệch theo cùng khoảng thời gian với benchmark. Ghép số liệu MySQL với CPU, RAM và I/O của hệ điều hành để tìm giới hạn thực tế.

Khi kiểm tra kế hoạch của một SELECT cụ thể, dùng **EXPLAIN** để xem cách optimizer dự định truy cập bảng. Trên MySQL 8.0.18 trở lên, **EXPLAIN ANALYZE** có thể cho biết thời gian và số dòng thực tế của các iterator:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC
LIMIT 50;
~~~

**EXPLAIN ANALYZE** thực thi câu SELECT để thu thập số liệu. Chạy trong môi trường kiểm thử hoặc thời điểm được kiểm soát, với truy vấn có giới hạn phù hợp. So sánh estimated rows với actual rows, số vòng lặp và thời gian từng iterator. Sai lệch lớn giữa ước lượng và thực tế có thể khiến optimizer chọn kế hoạch kém hiệu quả.

## 6. Thay đổi từng yếu tố và kiểm tra giả thuyết

Mỗi lượt thử nên có một giả thuyết cụ thể, một thay đổi chính và tiêu chí đánh giá đã xác định trước. Ví dụ:

> Giả thuyết: truy vấn tìm đơn hàng đang chờ phải đọc quá nhiều dòng vì thiếu index phù hợp. Thay đổi thử nghiệm: thêm index ghép trên (status, created_at). Kết quả mong đợi: giảm rows examined và p95 của truy vấn, đồng thời không làm chi phí ghi tăng vượt ngưỡng chấp nhận.

Một chu trình thử nghiệm có thể thực hiện như sau:

1. Ghi baseline và lưu kế hoạch thực thi của truy vấn hoặc workload liên quan.
2. Nêu giả thuyết và chỉ rõ biến sẽ thay đổi, ví dụ một index, một câu SQL, một biến cấu hình hoặc mức đồng thời.
3. Thay đổi đúng biến đó trên môi trường thử nghiệm; ghi lại cấu hình trước và sau.
4. Chạy cùng dataset, cùng workload, cùng tham số, cùng thời gian warm-up và measurement window.
5. Thu thập các chỉ số đã chọn, kiểm tra tính đúng đắn của dữ liệu và ghi nhận tác động phụ.
6. Lặp lại đủ lượt, so sánh với baseline rồi kết luận giữ, điều chỉnh hoặc hoàn tác thay đổi.

Không đồng thời thêm index, sửa SQL và tăng innodb_buffer_pool_size trong cùng một lượt rồi quy toàn bộ cải thiện cho một nguyên nhân. Khi thay nhiều biến cùng lúc, ta không biết yếu tố nào tạo ra kết quả hoặc yếu tố nào gây tác dụng phụ. Nếu nghi ngờ các biến tương tác, trước hết đo riêng từng biến; sau đó thiết kế thí nghiệm kết hợp có chủ đích và ghi rõ các tổ hợp được thử.

Ví dụ index **(status, created_at)** có thể phù hợp khi truy vấn lọc bằng điều kiện bằng trên **status**, sau đó lọc hoặc sắp xếp theo **created_at**. Cần xác nhận bằng kế hoạch thực thi và workload thực tế. Index mới chiếm dung lượng và làm INSERT/UPDATE/DELETE tốn thêm công; vì vậy bộ đo phải kiểm tra cả đọc lẫn ghi. Thời gian tạo index cũng cần được ghi nhận riêng, không trộn với thời gian truy vấn sau khi index đã ổn định.

Với thay đổi cấu hình, xác minh giá trị thực tế bằng **SHOW GLOBAL VARIABLES** hoặc truy vấn biến cụ thể; không chỉ dựa vào file cấu hình dự định. Một số thay đổi cần khởi động lại MySQL hoặc có thể làm thay đổi trạng thái cache. Hãy ghi rõ điều đó và đo trạng thái lạnh/ấm theo mục tiêu.

## 7. Đọc kết quả và xác định hồi quy

So sánh các lượt chạy bằng cùng đơn vị, cùng khoảng đo và cùng cách tính. Một bảng kết quả tối thiểu có thể gồm:

| Chỉ số | Baseline | Sau thay đổi | Chênh lệch | Đạt tiêu chí? |
|---|---:|---:|---:|---|
| TPS |  |  |  |  |
| Latency p95 |  |  |  |  |
| Latency p99 |  |  |  |  |
| Error / timeout |  |  |  |  |
| CPU trung bình / đỉnh |  |  |  |  |
| Rows examined |  |  |  |  |
| Storage read latency |  |  |  |  |

Không chỉ nhìn giá trị trung bình. p95 hoặc p99 có thể xấu đi dù average cải thiện, đặc biệt khi hệ thống gần bão hòa hoặc một số transaction phải chờ khóa. Nếu tăng số luồng mà throughput gần như không tăng nhưng latency tăng mạnh, hệ thống có thể đã chạm giới hạn CPU, I/O, connection hoặc lock contention.

Một thay đổi được xem là cải thiện khi chỉ số mục tiêu tốt lên một cách lặp lại, các chỉ số bảo vệ vẫn trong ngưỡng đã thống nhất và dữ liệu vẫn chính xác. Hãy đặt ngưỡng theo SLO và đặc tính ứng dụng, không áp dụng một tỷ lệ phần trăm chung cho mọi hệ thống. Nếu chênh lệch nhỏ hơn độ dao động giữa các lượt chạy, cần thêm lượt đo hoặc giảm nhiễu trước khi kết luận.

Phân loại kết quả để quyết định rõ ràng:

- **Cải thiện:** mục tiêu tốt hơn ổn định, không vi phạm tiêu chí bảo vệ.
- **Không khác biệt rõ:** chênh lệch nằm trong nhiễu đo hoặc quá nhỏ để có ý nghĩa vận hành.
- **Hồi quy:** latency, throughput, lỗi hoặc tài nguyên vượt ngưỡng cho phép.
- **Không hợp lệ:** môi trường, dữ liệu, workload hoặc trạng thái cache khác điều kiện đã định; cần chạy lại.

## 8. Tạo bộ kiểm tra hồi quy hiệu năng

Sau khi sửa SQL, thêm index, thay đổi schema, cấu hình hoặc logic transaction, chạy lại cùng bộ kiểm tra để phát hiện hồi quy. Một bộ kiểm tra có thể chia thành ba mức:

1. **Smoke test:** xác nhận kết nối, truy vấn chính và thao tác ghi cơ bản vẫn hoạt động.
2. **Representative test:** chạy workload mô phỏng tỷ lệ đọc/ghi, dữ liệu, transaction và đồng thời gần thực tế; đây là cơ sở so sánh hiệu năng.
3. **Stress hoặc soak test:** tăng tải có kiểm soát hoặc chạy lâu hơn để tìm điểm bão hòa, rò rỉ tài nguyên và vấn đề xuất hiện theo thời gian.

Bộ kiểm tra cần xác minh cả kết quả nghiệp vụ. Đối với transaction ghi, kiểm tra số dòng, ràng buộc, trạng thái cuối và tính nhất quán sau commit/rollback. Đối với workload đồng thời, quan sát deadlock, lock wait, timeout và thời gian giữ khóa. Nếu hệ thống có replica, kiểm tra replication lag trong tải ghi và xác nhận luồng đọc replica vẫn đáp ứng yêu cầu dữ liệu mới nhất của ứng dụng.

Lưu cùng mỗi lần chạy:

- Phiên bản ứng dụng, schema và MySQL.
- Snapshot hoặc cách tạo dataset, seed và phân bố dữ liệu.
- Cấu hình MySQL hiệu lực, cấu hình connection pool và tài nguyên máy.
- Mã workload, tham số, số luồng, thời gian warm-up và thời gian đo.
- Kết quả throughput, latency percentile, lỗi và chỉ số tài nguyên.
- Kế hoạch thực thi của truy vấn trọng yếu cùng thay đổi đã thử.
- Kết luận, tiêu chí đạt/trượt và quyết định giữ hoặc hoàn tác.

Trong CI, chỉ chạy workload nhỏ và ổn định ở mỗi thay đổi nếu môi trường CI có thể kiểm soát được nhiễu. Chạy benchmark nặng trên môi trường chuyên dụng theo lịch hoặc trước các đợt phát hành lớn. Khi phát hiện hồi quy, lưu kết quả và điều kiện tái hiện để nhóm phát triển có thể điều tra lại.

## 9. Ví dụ quy trình áp dụng

Giả sử màn hình quản trị liệt kê các đơn hàng đang chờ xử lý. Truy vấn có p95 cao và thống kê cho thấy số dòng examined lớn so với số dòng trả về.

- **Baseline:** lưu SQL, tham số thường gặp, EXPLAIN hoặc EXPLAIN ANALYZE, p50/p95/p99, rows examined, throughput và tải CPU/I/O.
- **Giả thuyết:** điều kiện lọc và sắp xếp chưa được hỗ trợ bởi index thích hợp.
- **Thử nghiệm:** trên bản sao dữ liệu, thêm index ghép (status, created_at); không sửa đồng thời SQL hay cấu hình máy chủ.
- **Đo lại:** chạy cùng workload và cùng tham số, kiểm tra kế hoạch mới, rows examined và latency.
- **Kiểm tra tác động phụ:** chạy workload tạo và cập nhật đơn hàng để đo chi phí ghi, dung lượng index và ảnh hưởng tới các truy vấn khác.
- **Kết luận:** chỉ giữ index nếu cải thiện lặp lại, đáp ứng ngưỡng latency và không làm các thao tác ghi vượt SLO. Nếu không đạt, hoàn tác và thử một giả thuyết khác.

Ví dụ này cho thấy tối ưu một truy vấn phải được đánh giá trong toàn bộ workload của hệ thống. Một index có thể làm truy vấn đọc nhanh hơn nhưng làm ghi chậm hơn; chỉ số của một màn hình riêng lẻ không thể đại diện cho toàn bộ dịch vụ.

## 10. Checklist trước khi công bố kết quả

- [ ] Workload phản ánh truy vấn, tỷ lệ đọc/ghi, transaction và mức đồng thời thực tế.
- [ ] Dataset có quy mô và phân bố đủ gần môi trường mục tiêu.
- [ ] Môi trường, phiên bản, cấu hình và trạng thái cache được ghi lại.
- [ ] Baseline có nhiều lượt đo và có khoảng warm-up riêng.
- [ ] Throughput, latency percentile, lỗi và tài nguyên được đo cùng khoảng thời gian.
- [ ] Mỗi lượt thử chỉ thay đổi biến đã nêu trong giả thuyết.
- [ ] Kết quả được kiểm tra về tính đúng đắn dữ liệu và tác động phụ lên đọc/ghi.
- [ ] Bộ kiểm tra hồi quy có thể chạy lại với cùng dataset và tham số.
- [ ] Ngưỡng đạt/trượt dựa trên SLO và độ dao động đo được.
- [ ] Kết quả, cấu hình, workload và quyết định được lưu để đối chiếu về sau.

Đo tải đại diện giúp biết MySQL đang xử lý công việc nào và chịu tải ra sao. Thay đổi từng yếu tố giúp xác định nguyên nhân của cải thiện hoặc suy giảm. Kiểm tra hồi quy biến các phép đo đó thành quy trình có thể lặp lại sau mỗi lần thay đổi SQL, index, transaction hoặc cấu hình, qua đó giữ hiệu năng ổn định cùng với tính đúng đắn của dữ liệu.

