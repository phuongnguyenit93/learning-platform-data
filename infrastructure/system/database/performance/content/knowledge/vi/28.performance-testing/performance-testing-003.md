# Kiểm thử tải ổn định, tải tăng dần, tải đột biến và chạy dài hạn

Kiểm thử hiệu năng cơ sở dữ liệu cần mô phỏng cách hệ thống được sử dụng thật: nhiều người dùng gửi yêu cầu đồng thời, dữ liệu có phân bố thực tế, truy vấn đọc và ghi xen kẽ, kết nối được tái sử dụng và tải thay đổi theo thời gian. Một lần chạy vài câu SQL đơn lẻ không đủ để kết luận hệ thống chịu được tải production. Cần kiểm thử nhiều hình dạng tải để biết hệ thống hoạt động ra sao khi tải ổn định, khi số người dùng tăng dần, khi traffic tăng đột ngột và khi chạy liên tục trong nhiều giờ.

Trong phạm vi DATABASE_PERFORMANCE, kiểm thử phải gắn với đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Mỗi loại tải có thể làm lộ một nhóm vấn đề khác nhau: tải ổn định cho thấy năng lực duy trì và độ trễ thông thường; tải tăng dần giúp tìm điểm bão hòa; tải đột biến kiểm tra khả năng hấp thụ burst và phục hồi; chạy dài hạn phát hiện rò rỉ tài nguyên, backlog và suy giảm theo thời gian. Kết quả cần được đối chiếu với SLO của ứng dụng, đồng thời quan sát CPU, bộ nhớ, I/O, cache, khóa, connection pool, log và replication.

Mục tiêu là đo năng lực phục vụ tải có thể duy trì mà vẫn đạt độ trễ, thông lượng và tính đúng đắn. Bài học này trình bày cách thiết kế workload, chọn mô hình phát tải, tổ chức từng loại kiểm thử, thu thập số liệu ở cả ứng dụng và database, tìm bottleneck và lập báo cáo có thể tái lập.

## 1. Mục tiêu của kiểm thử hiệu năng

Kiểm thử hiệu năng trả lời các câu hỏi vận hành cụ thể:

- Hệ thống xử lý được bao nhiêu giao dịch mỗi giây ở mức độ trễ mục tiêu?
- p95 và p99 thay đổi như thế nào khi concurrency tăng?
- Ở mức tải nào throughput không tăng thêm hoặc bắt đầu giảm?
- CPU, RAM, storage, buffer cache hay lock contention trở thành nút thắt trước?
- Connection pool có đủ kết nối nhưng không làm database quá tải không?
- Hệ thống có hấp thụ được burst và trở lại trạng thái bình thường sau burst không?
- Sau vài giờ chạy liên tục, độ trễ, bộ nhớ, số connection và hàng đợi có tăng dần không?
- Thay đổi SQL, index hoặc cấu hình có cải thiện workload tổng thể hay chỉ một truy vấn?

Một bài test có giá trị phải có giả thuyết, workload, dữ liệu, ngưỡng đạt và cách thu thập số liệu. Nếu không định nghĩa trước tiêu chí thành công, rất dễ chọn một chỉ số đẹp sau khi chạy và bỏ qua các dấu hiệu suy giảm khác.

### 1.1. Phân biệt hiệu năng, tải và sức chứa

- **Tải (load):** lượng công việc được gửi đến hệ thống trong một khoảng thời gian, ví dụ request/giây, transaction/giây hoặc số người dùng đồng thời.
- **Độ trễ (latency):** thời gian một yêu cầu cần để hoàn thành.
- **Thông lượng (throughput):** số yêu cầu hoặc giao dịch hoàn tất trong một đơn vị thời gian.
- **Concurrency:** số công việc đang được xử lý hoặc đang chờ tại cùng thời điểm.
- **Sức chứa (capacity):** mức tải hệ thống có thể duy trì trong khi vẫn đáp ứng các mục tiêu độ trễ, lỗi và tài nguyên.
- **Saturation:** trạng thái một hoặc nhiều tài nguyên tiến gần giới hạn, khiến hàng đợi và độ trễ tăng nhanh.

Số request được gửi không nhất thiết bằng số request hoàn tất. Khi hệ thống quá tải, request có thể bị từ chối, timeout hoặc xếp hàng. Luôn đo cả offered load và completed throughput.

### 1.2. Dùng percentile thay vì chỉ dùng trung bình

Latency trung bình có thể che giấu một nhóm request rất chậm. Ví dụ phần lớn request hoàn tất trong 40 ms nhưng một số request bị block trong 2 giây. Trung bình có thể vẫn trông chấp nhận được trong khi người dùng gặp độ trễ lớn.

Các percentile thường dùng:

- p50: một nửa request hoàn tất trong khoảng thời gian này hoặc nhanh hơn.
- p95: 95% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn.
- p99: 99% request hoàn tất trong khoảng thời gian này hoặc nhanh hơn.

Đối với hệ thống giao dịch, p95/p99 thường quan trọng hơn trung bình vì chúng phản ánh tail latency. Cần theo dõi cả timeout và request không hoàn tất; nếu chỉ tính latency của request thành công, kết quả có thể đẹp giả tạo.

## 2. Bốn hình dạng tải chính

| Loại kiểm thử | Hình dạng tải | Câu hỏi chính | Vấn đề thường phát hiện |
|---|---|---|---|
| Tải ổn định (steady-state) | Duy trì một mức tải trong thời gian xác định | Hệ thống có duy trì SLO ở tải dự kiến không? | Tài nguyên nền, latency ổn định, lock và pool |
| Tải tăng dần (ramp/load) | Tăng concurrency hoặc arrival rate theo từng bậc | Điểm bão hòa nằm ở đâu? | CPU/I/O saturation, queue growth, throughput plateau |
| Tải đột biến (spike) | Tăng nhanh từ nền lên đỉnh rồi giảm | Hệ thống phản ứng và phục hồi sau burst ra sao? | Connection storm, cache miss, autoscaling delay, timeout |
| Chạy dài hạn (soak/endurance) | Duy trì tải đại diện trong nhiều giờ | Hiệu năng có suy giảm theo thời gian không? | Leak, memory growth, backlog, log và cleanup |

Các loại test bổ sung như stress test, capacity test và scalability test có thể kết hợp với bốn hình dạng trên. Stress test cố ý vượt giới hạn để quan sát cách hệ thống suy giảm và phục hồi; capacity test tìm mức tải tối đa đạt SLO; scalability test xem năng lực thay đổi thế nào khi thêm CPU, RAM, replica hoặc node.

## 3. Thiết kế workload đại diện

Trước khi chọn công cụ, hãy mô tả workload mà database thực sự nhận được. Một workload chỉ gồm SELECT theo primary key không đại diện cho hệ thống có INSERT, UPDATE, join, báo cáo và transaction nhiều bước.

### 3.1. Xác định hỗn hợp giao dịch

Ví dụ một workload minh họa:

| Loại thao tác | Tỷ trọng giả định | Đặc điểm |
|---|---:|---|
| Đọc chi tiết theo ID | 45% | Point lookup, yêu cầu latency thấp |
| Tìm kiếm theo tenant và thời gian | 20% | Filter, range scan và phân trang |
| Tạo đơn hàng | 15% | INSERT nhiều bảng và kiểm tra FK/UNIQUE |
| Cập nhật trạng thái | 15% | UPDATE, row lock và ghi log |
| Báo cáo tổng hợp nhỏ | 5% | GROUP BY, aggregate và đọc nhiều hàng |

Tỷ trọng chỉ là ví dụ. Hãy lấy từ APM, query statistics, log đã ẩn dữ liệu nhạy cảm hoặc mô hình nghiệp vụ. Không nên tự đặt tỷ trọng rồi coi đó là workload production.

### 3.2. Mô hình tải mở và tải đóng

Có hai cách phổ biến để phát sinh tải:

- **Closed workload model:** cố định số virtual user hoặc worker. Mỗi worker gửi yêu cầu, chờ hoàn tất rồi mới gửi yêu cầu tiếp theo. Khi hệ thống chậm, tốc độ phát sinh request tự giảm.
- **Open workload model:** cố định hoặc điều khiển tốc độ request đến theo thời gian, ví dụ 200 request/giây bất kể request trước đã hoàn tất hay chưa. Khi hệ thống chậm, số request đang chờ có thể tăng.

Closed model phù hợp mô phỏng nhóm người dùng có hành vi chờ phản hồi trước khi thao tác tiếp. Open model phù hợp kiểm tra hệ thống nhận một arrival rate độc lập với thời gian xử lý.

Nếu chỉ dùng closed model, hệ thống quá tải có thể tự giảm offered load vì mỗi virtual user phải chờ response. Điều này có thể che giấu việc hệ thống không đáp ứng được tốc độ request mà upstream thực tế tiếp tục gửi. Hiện tượng đo thiếu độ trễ do generator không phát đủ request trong lúc hệ thống chậm thường được gọi là coordinated omission.

Không có mô hình nào luôn đúng. Chọn mô hình dựa trên hành vi thực tế của client và upstream; ghi rõ mô hình trong báo cáo.

### 3.3. Dữ liệu kiểm thử

Kích thước và phân bố dữ liệu ảnh hưởng trực tiếp đến execution plan, selectivity, cache và I/O. Cần chuẩn bị dữ liệu có:

- Số lượng hàng gần với quy mô mục tiêu.
- Phân bố khóa và giá trị phổ biến tương tự production.
- Độ lệch dữ liệu (skew), tenant lớn/nhỏ và khóa nóng.
- Tỷ lệ NULL, duplicate hợp lệ, trạng thái và dữ liệu lịch sử phù hợp.
- Kích thước hàng, JSON/blob hoặc cột lớn gần với thực tế.
- Tỷ lệ dữ liệu mới so với dữ liệu cũ.
- Quan hệ FK và độ rộng join thực tế.

Một bảng thử nghiệm chỉ có vài nghìn hàng có thể khiến optimizer chọn plan khác với bảng hàng chục triệu hàng. Một bộ dữ liệu phân bố đều cũng không đại diện cho hệ thống có một tenant chiếm 60% dữ liệu.

### 3.4. Tránh làm sai lệch dữ liệu trong test

Nếu mỗi vòng test liên tục tạo đơn mới, bảng và index sẽ tăng kích thước trong khi test chạy. Khi đó các vòng sau không còn dùng cùng dữ liệu như vòng đầu. Có thể dùng dữ liệu seed cố định, reset có kiểm soát hoặc tạo batch dữ liệu riêng cho từng lượt.

Đối với workload ghi, cần xác định:

- Dữ liệu có được rollback sau test không?
- Có cần dọn hàng test và index entry không?
- Sequence/identity có thể tăng liên tục không?
- Trigger, CDC, replication và audit có được kích hoạt như production không?
- Dữ liệu có thể bị trùng giữa các worker không?

Không dùng dữ liệu cá nhân hoặc dữ liệu production chưa được bảo vệ trong môi trường test. Khi cần dữ liệu tương tự production, dùng masking hoặc dữ liệu tổng hợp có phân bố tương đương.

## 4. Kiểm thử tải ổn định

Steady-state test duy trì một mức tải đã chọn sau giai đoạn khởi động. Mục tiêu là xác nhận hệ thống có thể hoạt động ổn định trong điều kiện dự kiến.

### 4.1. Cấu trúc một lượt test

Một lượt tải ổn định thường gồm:

1. **Pre-check:** xác nhận database, ứng dụng, schema, index và monitoring sẵn sàng.
2. **Warm-up:** chạy workload nhẹ để nạp connection pool, cache và plan cần thiết.
3. **Ramp-up ngắn:** tăng đến mức tải mục tiêu, tránh bước nhảy quá lớn.
4. **Steady window:** duy trì offered load/concurrency cố định đủ lâu để số liệu ổn định.
5. **Cool-down:** giảm tải và quan sát hàng đợi, transaction và I/O trở về bình thường.
6. **Review:** so sánh số liệu với baseline và ngưỡng SLO.

Không tính thời gian warm-up vào cửa sổ steady-state nếu mục tiêu là đo trạng thái ổn định. Nếu mục tiêu là đo trải nghiệm ngay sau cold start, hãy chạy một bài test riêng cho cold-cache behavior.

### 4.2. Chọn thời lượng

Thời lượng phải đủ để:

- Quan sát được nhiều chu kỳ của workload.
- Bao phủ các truy vấn quan trọng và transaction khác nhau.
- Tránh kết luận từ một burst ngắn.
- Cho phép thống kê p95/p99 có đủ mẫu.

Một bài test 10 phút có thể phù hợp với vòng thử nghiệm nhanh; kiểm chứng release có thể cần 30-60 phút hoặc lâu hơn tùy workload. Không dùng thời lượng cố định cho mọi hệ thống.

### 4.3. Tiêu chí đạt

Ví dụ:

- Offered load đạt mức mục tiêu và completed throughput không tụt dần.
- p95/p99 nằm trong SLO.
- Error/timeout rate dưới ngưỡng.
- CPU, memory, IOPS và storage latency còn khoảng dự phòng.
- Không có lock wait, deadlock hoặc pool pending tăng liên tục.
- Không có backlog replication hoặc log tăng không kiểm soát.

Một hệ thống có thể đạt p95 trong vài phút nhưng vẫn không bền vững nếu CPU luôn ở 100%, storage queue tăng hoặc connection pool không còn dự phòng. Đánh giá cả độ trễ và mức bão hòa.

## 5. Kiểm thử tải tăng dần

Ramp/load test tăng dần concurrency hoặc arrival rate theo từng bậc để tìm mối quan hệ giữa tải, throughput, latency và tài nguyên.

### 5.1. Thiết kế các bậc tải

Ví dụ:

| Giai đoạn | Offered load minh họa | Thời gian giữ | Mục tiêu |
|---|---:|---:|---|
| A | 50 request/s | 10 phút | Baseline dưới tải |
| B | 100 request/s | 10 phút | Kiểm tra tăng tải tuyến tính |
| C | 150 request/s | 10 phút | Quan sát độ trễ và tài nguyên |
| D | 200 request/s | 10 phút | Tìm dấu hiệu bão hòa |
| E | 250 request/s | 5 phút | Xác định vùng vượt SLO nếu an toàn |

Các con số chỉ minh họa. Trong thực tế, chọn bước tăng dựa trên tải bình thường, peak dự kiến và giới hạn an toàn.

### 5.2. Nhận diện điểm bão hòa

Ở vùng tải thấp, tăng offered load thường làm throughput tăng gần tương ứng. Khi một tài nguyên chạm giới hạn:

- Throughput có thể đi ngang hoặc giảm.
- Latency tăng nhanh, đặc biệt p95/p99.
- Queue depth và số request pending tăng.
- CPU, I/O, memory hoặc worker utilization đạt mức cao.
- Error, timeout và retry tăng.

Điểm bão hòa không nhất thiết trùng với 100% CPU. Storage IOPS, log flush, lock contention, connection pool hoặc giới hạn worker có thể trở thành nút thắt trước.

### 5.3. Đọc đường cong throughput và latency

Vẽ hai đường theo offered load:

- Throughput hoàn tất mỗi giây.
- p95 hoặc p99 latency.

Ở vùng tải có thể phục vụ, throughput tăng và latency tăng từ từ. Gần điểm bão hòa, latency thường tăng nhanh trong khi throughput tăng ít. Nếu tiếp tục tăng tải, hàng đợi có thể tăng theo cấp số nhân và request bắt đầu timeout.

Không chọn capacity bằng mức tải cao nhất từng đạt được. Chọn mức tải duy trì được SLO và còn headroom cho burst, batch, failover và biến động dữ liệu.

### 5.4. Thử nghiệm khả năng mở rộng

Có thể chạy lại ramp test sau khi:

- Tăng CPU hoặc RAM.
- Tăng IOPS hoặc đổi loại storage.
- Thay đổi pool size.
- Thêm read replica.
- Tối ưu index hoặc SQL.
- Chuyển báo cáo sang warehouse.

So sánh capacity trước/sau trong cùng điều kiện. Nếu tăng gấp đôi tài nguyên nhưng throughput chỉ tăng 10%, có thể bottleneck nằm ở lock, serial section, network, log hoặc một thành phần chưa được mở rộng.

## 6. Kiểm thử tải đột biến

Spike test mô phỏng traffic tăng rất nhanh từ mức nền lên mức đỉnh, giữ trong một khoảng ngắn rồi giảm về mức ban đầu.

### 6.1. Tình huống thực tế

- Flash sale hoặc mở bán vé.
- Batch đồng bộ bắt đầu cùng thời điểm.
- Nhiều client retry sau một sự cố mạng.
- Người dùng đăng nhập đồng loạt đầu giờ.
- Cache hết hạn cùng lúc.
- Một node failover khiến traffic dồn sang node còn lại.

### 6.2. Những gì cần quan sát

- Pool có tạo quá nhiều connection trong thời gian ngắn không?
- Database có chịu được số session tăng đột ngột không?
- Cache miss và physical reads có tăng mạnh không?
- Autoscaling có đủ nhanh hay chỉ hoàn tất sau khi burst đã qua?
- Hàng đợi có giới hạn và request có bị từ chối đúng cách không?
- Retry có tạo thêm tải và gây retry storm không?
- Khi spike kết thúc, queue và latency có trở về baseline không?

### 6.3. Thiết kế spike

Một kịch bản minh họa:

1. Duy trì 40 request/s trong 10 phút.
2. Tăng lên 300 request/s trong 30 giây.
3. Giữ 300 request/s trong 2 phút.
4. Giảm về 40 request/s.
5. Theo dõi thêm 10 phút để đo thời gian phục hồi.

Mức tải phải dựa trên peak dự kiến hoặc giới hạn thử nghiệm được phê duyệt. Không nhảy lên một mức tùy tiện có thể làm hỏng môi trường dùng chung.

### 6.4. Phục hồi quan trọng như thời gian chịu spike

Hệ thống có thể sống sót qua spike nhưng cần 20 phút mới xóa hết backlog. Nếu SLO yêu cầu phục hồi trong 2 phút, bài test vẫn thất bại.

Đo:

- Thời gian từ lúc giảm offered load đến khi pending về bình thường.
- Thời gian p95/p99 trở lại SLO.
- Thời gian replication lag và storage queue giảm.
- Số request thất bại hoặc phải retry.
- Có connection hoặc transaction bị giữ lại sau spike không.

## 7. Kiểm thử chạy dài hạn (soak/endurance)

Soak test duy trì tải đại diện trong nhiều giờ hoặc nhiều ngày tùy mục tiêu. Nó tìm các vấn đề khó xuất hiện trong bài test ngắn.

### 7.1. Vấn đề thường được phát hiện

- Connection leak hoặc statement/result set không được đóng.
- Bộ nhớ ứng dụng tăng dần hoặc garbage collection ngày càng thường xuyên.
- Transaction mở lâu và session idle-in-transaction.
- Hàng đợi, retry hoặc backlog tăng dần.
- Temp file, temp tablespace hoặc tempdb tăng.
- WAL/redo/binlog, checkpoint hoặc replication lag không theo kịp.
- Cache churn do working set thay đổi.
- Job bảo trì, vacuum, purge hoặc cleanup không hoàn thành.
- Index/table tăng trưởng và thay đổi phân bố dữ liệu.
- Scheduled task hoặc batch trùng thời điểm với traffic giao dịch.

Không phải mọi thay đổi dung lượng trong soak test đều là leak. Dữ liệu test có thể tăng tự nhiên do INSERT. Cần phân biệt tăng trưởng dự kiến với tài nguyên không được giải phóng hoặc backlog không được xử lý.

### 7.2. Thiết kế soak test

1. Chọn tải gần với mức vận hành dự kiến, không nhất thiết là peak.
2. Giữ tỷ lệ đọc/ghi và phân bố dữ liệu thực tế.
3. Đưa vào các tác vụ định kỳ như batch, checkpoint, backup hoặc refresh materialized view nếu chúng thuộc lịch vận hành.
4. Theo dõi metric theo chuỗi thời gian, không chỉ lấy trung bình cả ngày.
5. Ghi lại memory, connection, transaction age, queue, log, temp và replication.
6. Kiểm tra hệ thống sau khi test kết thúc để xác nhận tài nguyên trở về trạng thái bình thường.

### 7.3. Đọc xu hướng theo thời gian

Một đường metric dao động quanh mức ổn định thường ít đáng lo hơn đường tăng liên tục. Ví dụ:

- Active connections tăng khi traffic lên rồi giảm sau giờ cao điểm: có thể bình thường.
- Active connections tăng dần dù offered load cố định: có thể là leak hoặc usage time tăng.
- Replication lag tăng rồi giảm sau batch: cần đánh giá khả năng bắt kịp.
- WAL/redo tăng theo tốc độ ghi và được archive/truncate đúng hạn: có thể bình thường.
- Temp usage tăng và không giảm sau truy vấn: cần kiểm tra temp spill, session hoặc cleanup.

Soak test cần có baseline ở đầu, giữa và cuối; xem xu hướng cùng các sự kiện xảy ra tại thời điểm đó.

## 8. Ma trận chọn loại kiểm thử

| Mục tiêu | Test phù hợp | Kết quả cần thu |
|---|---|---|
| Xác nhận release ở tải thông thường | Steady-state | p95/p99, throughput, lỗi, tài nguyên |
| Tìm mức tải tối đa đạt SLO | Ramp/load và capacity | Capacity curve, điểm bão hòa, headroom |
| Kiểm tra flash sale hoặc burst | Spike | Peak latency, queue, timeout, recovery time |
| Phát hiện leak và suy giảm dài hạn | Soak/endurance | Xu hướng memory, connection, log, backlog |
| Kiểm tra tác động sau thêm tài nguyên | Ramp trước/sau | Mức tăng capacity và chi phí |
| Kiểm tra cold cache sau restart | Cold-start test riêng | Physical reads, warm-up time, p95/p99 |
| Kiểm tra giao dịch và báo cáo đồng thời | Mixed-workload test | OLTP SLO, report runtime, I/O và contention |

Một kế hoạch release thường kết hợp steady-state và spike ngắn. Capacity planning cần ramp test. Soak test phù hợp cho hệ thống có phiên chạy dài, connection pool và batch định kỳ.

## 9. Các chỉ số cần thu thập

### 9.1. Ở tầng ứng dụng và load generator

- Offered request rate và completed throughput.
- p50, p95, p99 latency.
- Error rate, timeout, retry và request bị hủy.
- Số virtual user, concurrency và queue depth.
- Pool active/idle/pending, acquire latency và usage duration.
- Thời gian serialize, network và xử lý ngoài database.
- Tài nguyên của load generator: CPU, RAM, network và số socket.

Load generator cũng có thể trở thành bottleneck. Nếu generator hết CPU hoặc không tạo đủ request, kết quả sẽ đánh giá thấp khả năng của database.

### 9.2. Ở tầng database

- CPU và thời gian CPU theo query/workload.
- Memory, buffer pool/cache hit và eviction.
- Logical reads, physical reads và số hàng được quét.
- IOPS, throughput đọc/ghi, storage latency và queue depth.
- WAL/redo/binlog volume, log flush latency và checkpoint.
- Lock wait, deadlock, latch wait và transaction age.
- Số session, active query, idle session và idle-in-transaction.
- Sort/hash spill, tempdb hoặc temporary tablespace.
- Replication lag và apply throughput.
- Query plan, estimated rows, actual rows và plan regression.

### 9.3. Đồng bộ thời gian và gắn nhãn

Đồng bộ clock giữa load generator, ứng dụng, database và hệ thống giám sát. Nếu timestamp lệch, rất khó xác định metric nào tăng trước.

Gắn nhãn mỗi lượt test bằng:

- Test ID và loại tải.
- Phiên bản ứng dụng và schema.
- Database engine/version và cấu hình.
- Dataset version hoặc seed.
- Mức tải mục tiêu và số replica.
- Thời điểm bắt đầu warm-up, steady window, spike và cool-down.

Không đưa thông tin nhạy cảm hoặc token xác thực vào nhãn và log.

## 10. Phân tích bottleneck từ số liệu

### 10.1. CPU bão hòa

Dấu hiệu:

- CPU database tăng cao và duy trì.
- Throughput không tăng tương ứng với offered load.
- Latency tăng cùng mức CPU.
- Query CPU cao, scan nhiều hàng, biểu thức hoặc join tốn kém.

Hướng điều tra:

- Execution plan và số hàng thực tế.
- Index, predicate và selectivity.
- Query lặp hoặc N+1.
- Aggregate, sort, hash và parallelism.
- Workload reporting chạy cùng thời điểm.

### 10.2. I/O bão hòa

Dấu hiệu:

- Storage latency, queue depth hoặc IOPS tăng.
- Physical reads/writes tăng.
- Query có read wait hoặc log flush wait.
- CPU có thể chưa cao nhưng throughput giảm.

Hướng điều tra:

- Full scan và range scan lớn.
- Index hoặc working set vượt cache.
- Temp spill.
- Checkpoint, backup và batch chạy đồng thời.
- Log volume và latency của thiết bị lưu log.

### 10.3. Lock contention

Dấu hiệu:

- Lock wait và deadlock tăng.
- Transaction duration tăng.
- Một số session chờ cùng blocker.
- Throughput giảm dù CPU chưa bão hòa.

Hướng điều tra:

- Transaction dài hoặc idle-in-transaction.
- Thứ tự lấy khóa không nhất quán.
- Hot row/hot key.
- Index thiếu làm phạm vi scan/lock lớn.
- Isolation level và read/write pattern.

### 10.4. Connection pool hoặc giới hạn worker

Dấu hiệu:

- Active gần maximum, pending tăng và acquire latency cao.
- Database session count cao hoặc nhiều session idle.
- Query duration bình thường nhưng request chờ trước khi SQL bắt đầu.

Hướng điều tra:

- Connection leak và usage duration.
- Pool size trên toàn bộ replica.
- Thread pool và queue limit.
- Transaction giữ connection trong lúc gọi dịch vụ ngoài.
- Database worker/session limit.

### 10.5. Memory pressure và spill

Dấu hiệu:

- Sort/hash spill tăng.
- Temp I/O tăng.
- Memory grant bị chờ hoặc bị giảm.
- Cache eviction tăng và physical reads tăng.

Hướng điều tra:

- Kích thước working set.
- Cardinality estimate và plan.
- Số truy vấn phân tích đồng thời.
- Memory grant/work_mem và số node sort/hash.
- Cấu hình buffer pool và bộ nhớ dành cho hệ điều hành.

## 11. Kiểm soát tính đúng đắn trong khi tải cao

Kiểm thử hiệu năng không chỉ đo tốc độ. Nếu ứng dụng trả response nhanh nhưng ghi sai dữ liệu, bài test không đạt.

Đối với workload ghi, xác minh:

- Tổng số giao dịch thành công phù hợp với số response thành công.
- Không tạo duplicate ngoài quy tắc nghiệp vụ.
- Số dư, tồn kho hoặc trạng thái không vi phạm invariant.
- Foreign key và unique constraint vẫn được thực thi.
- Retry không tạo tác dụng phụ trùng lặp.
- Rollback và timeout không để transaction dở dang.
- Dữ liệu sau test có thể đối soát bằng ID hoặc checksum.

Nên dùng dữ liệu test có thể nhận diện, idempotency key và kiểm tra hậu điều kiện. Không chỉ dựa vào mã HTTP 200 hoặc số lượng request gửi đi.

## 12. Ví dụ kịch bản kiểm thử bằng k6

k6 có thể phát sinh tải ở tầng HTTP trong khi database được quan sát bằng công cụ riêng. Ví dụ sau dùng mô hình arrival-rate để duy trì tốc độ request đến theo các giai đoạn:

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    database_workload: {
      executor: 'ramping-arrival-rate',
      startRate: 40,
      timeUnit: '1s',
      preAllocatedVUs: 80,
      maxVUs: 300,
      stages: [
        { target: 40, duration: '5m' },
        { target: 40, duration: '10m' },
        { target: 80, duration: '5m' },
        { target: 80, duration: '10m' },
        { target: 0, duration: '2m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<300', 'p(99)<800']
  }
};

export default function () {
  const id = (__VU % 10000) + 1;
  const response = http.get(__ENV.BASE_URL + '/orders/' + id);

  check(response, {
    'request succeeded': (r) => r.status >= 200 && r.status < 300
  });
}
~~~

Đây là template cần điều chỉnh theo endpoint, dữ liệu và authentication của môi trường test. Hai giai đoạn giữ 40 request/giây tạo tải ổn định sau ramp-up; giai đoạn 80 request/giây tăng tải; giai đoạn cuối giảm tải. Để kiểm tra spike, thay các stage bằng một bước tăng rất nhanh và một khoảng giữ ngắn. Để kiểm tra soak, giữ arrival rate đại diện trong nhiều giờ.

Với mô hình arrival-rate, nếu load generator không có đủ VU để phát tốc độ mục tiêu, k6 có thể không đạt offered rate. Theo dõi dropped iterations và tài nguyên generator. Threshold trong script chỉ là tiêu chí ví dụ; SLO thực tế cần được thống nhất và áp dụng cho endpoint cùng workload.

### 12.1. Kiểm thử trực tiếp database

Các công cụ như pgbench, sysbench hoặc benchmark chuyên biệt của engine có thể dùng để kiểm tra database ở mức thấp hơn HTTP. Chúng hữu ích để cô lập tác động của SQL, storage hoặc engine, nhưng workload benchmark mặc định có thể khác ứng dụng thực.

Nên dùng hai lớp:

- Benchmark database để đo một nhóm thao tác hoặc truy vấn có kiểm soát.
- Load test qua ứng dụng để đo toàn bộ đường đi gồm pool, transaction, serialization và mạng.

Không so sánh kết quả của hai công cụ nếu dataset, transaction mix, concurrency, cache state và cách tính throughput khác nhau.

## 13. Quy trình thực hiện một chiến dịch kiểm thử

1. **Đặt mục tiêu:** xác định câu hỏi cần trả lời và SLO cần xác minh.
2. **Chọn hình dạng tải:** steady-state, ramp, spike, soak hoặc tổ hợp.
3. **Xác định workload:** tỷ lệ đọc/ghi, transaction, query, arrival rate và concurrency.
4. **Chuẩn bị dữ liệu:** kích thước, phân bố, skew, tenant, hot key và dữ liệu lịch sử.
5. **Chuẩn bị môi trường:** cấu hình tương đương mục tiêu, giới hạn tài nguyên và load generator đủ năng lực.
6. **Thiết lập quan sát:** dashboard, tracing, database statistics, log và đồng bộ thời gian.
7. **Chạy baseline:** đo trước thay đổi hoặc ở mức tải thấp.
8. **Chạy test theo kịch bản:** ghi rõ warm-up, ramp, hold, spike, soak và cool-down.
9. **Kiểm tra tính đúng đắn:** đối soát dữ liệu ghi, lỗi và rollback.
10. **Phân tích bottleneck:** liên hệ latency với CPU, I/O, memory, lock, pool và execution plan.
11. **Thử một thay đổi có kiểm soát:** index, SQL, pool, resource limit hoặc kiến trúc.
12. **Chạy lại cùng điều kiện:** giữ dữ liệu, workload, cấu hình và cách đo tương đương.
13. **Đánh giá trade-off:** throughput, p95/p99, error rate, tài nguyên và chi phí.
14. **Lưu kết quả:** báo cáo, biểu đồ, query plan, cấu hình và khuyến nghị.

Chỉ thay đổi một nhóm yếu tố chính trong mỗi vòng so sánh nếu muốn biết nguyên nhân cải thiện. Nếu đồng thời thay index, pool size, RAM và query, sẽ khó xác định yếu tố nào tạo ra kết quả.

## 14. Tiêu chí dừng và an toàn cho bài test

Một chiến dịch cần điều kiện dừng rõ ràng:

- Error rate hoặc timeout vượt ngưỡng cho phép.
- p99 vượt giới hạn trong một khoảng liên tục.
- CPU, I/O latency, storage queue hoặc memory pressure vượt mức bảo vệ.
- Connection pool hoặc database session đạt giới hạn.
- Replication lag, log backlog hoặc transaction age tăng không kiểm soát.
- Load generator hoặc môi trường dùng chung bị ảnh hưởng.
- Kiểm tra tính đúng đắn phát hiện dữ liệu sai.

Test tải lớn nên chạy trong môi trường chuyên dụng hoặc cửa sổ đã được phê duyệt với giới hạn và người chịu trách nhiệm. Nếu chạy trên production theo hình thức canary, chỉ dùng tải nhỏ có kiểm soát, có kill switch và giám sát trực tiếp. Không tạo spike hoặc stress vượt giới hạn trên hệ thống dùng chung mà chưa có kế hoạch bảo vệ.

Sau khi dừng, xác nhận:

- Generator đã ngừng gửi request.
- Request và job còn lại đã được xử lý hoặc hủy.
- Transaction không còn mở ngoài dự kiến.
- Connection pool và session trở lại bình thường.
- Queue và replication backlog đã giảm.
- Dữ liệu test đã được dọn theo kế hoạch.

## 15. Báo cáo kết quả

Một báo cáo kiểm thử nên có:

| Mục | Nội dung cần ghi |
|---|---|
| Mục tiêu | SLO và câu hỏi kiểm thử |
| Môi trường | Engine/version, CPU, RAM, storage, network, replica |
| Ứng dụng | Version, pool, thread/concurrency, cấu hình timeout |
| Dữ liệu | Kích thước, phân bố, seed hoặc snapshot |
| Workload | Tỷ lệ thao tác, query mix, arrival rate và concurrency |
| Hình dạng tải | Warm-up, steady, ramp, spike, soak và thời lượng |
| Kết quả | Offered load, throughput, p50/p95/p99, lỗi và timeout |
| Database | CPU, memory, I/O, cache, locks, log, temp và replication |
| Execution plan | Plan quan trọng, estimated/actual rows và thay đổi |
| Kết luận | SLO đạt/không đạt, bottleneck và capacity an toàn |
| Giới hạn | Khác biệt môi trường, dữ liệu hoặc công cụ so với production |
| Hành động | Thay đổi đề xuất, chủ sở hữu và phép đo cần chạy lại |

Không chỉ lưu ảnh dashboard. Lưu dữ liệu thô hoặc chuỗi metric có thể truy vấn lại, test script, tham số, query fingerprint và execution plan phù hợp để có thể tái lập.

## 16. Những sai lầm thường gặp

- **Chỉ chạy một lượt tải ngắn:** không đủ mẫu để đánh giá p95/p99 và trạng thái ổn định.
- **Dùng dữ liệu quá nhỏ:** optimizer chọn plan và cache behavior khác production.
- **Chỉ dùng closed workload:** offered load tự giảm khi hệ thống chậm và có thể che overload.
- **Chỉ báo cáo request đã thành công:** bỏ qua timeout và dropped iteration.
- **Không đo load generator:** generator có thể là bottleneck.
- **Tăng concurrency quá nhanh:** không xác định được điểm tải bắt đầu gây suy giảm.
- **Không giữ giai đoạn plateau:** khó phân biệt tác động ngắn hạn và trạng thái ổn định.
- **Bỏ qua recovery sau spike:** hệ thống có thể chịu được peak nhưng backlog không được xóa kịp.
- **Soak test chỉ xem tổng trung bình:** che giấu xu hướng memory, connection hoặc backlog tăng dần.
- **Không kiểm tra tính đúng đắn:** throughput cao nhưng dữ liệu ghi sai vẫn bị coi là thành công.
- **Thay nhiều cấu hình cùng lúc:** không biết nguyên nhân tạo ra cải thiện.
- **Dùng một ngưỡng CPU cố định làm tiêu chí duy nhất:** bỏ qua I/O, lock, memory và tail latency.
- **Không kiểm soát cache state:** so sánh một lần cold cache với một lần warm cache rồi kết luận sai.
- **Không ghi phiên bản và dữ liệu:** kết quả không thể tái lập.
- **Không có điều kiện dừng:** bài test có thể làm ảnh hưởng môi trường dùng chung.

## 17. Checklist kiểm thử tải

- [ ] Đã xác định SLO và mục tiêu đo cho giao dịch, báo cáo và database.
- [ ] Đã chọn steady-state, ramp, spike, soak theo câu hỏi cần trả lời.
- [ ] Đã xác định open/closed workload model và lý do lựa chọn.
- [ ] Đã mô phỏng tỷ lệ đọc/ghi, transaction và query mix thực tế.
- [ ] Dữ liệu có quy mô, phân bố, skew và hot key phù hợp.
- [ ] Load generator đủ CPU, RAM, network và VU để phát tải mục tiêu.
- [ ] Có warm-up và phân biệt cold-cache với warm-cache test.
- [ ] Đã đo offered load, completed throughput, p50/p95/p99 và error rate.
- [ ] Đã thu thập CPU, memory, I/O, cache, lock, pool, log và replication.
- [ ] Có dashboard/trace đồng bộ thời gian và gắn nhãn test run.
- [ ] Ramp test có bước tăng và thời gian giữ đủ để nhận diện saturation.
- [ ] Spike test đo cả peak và recovery time.
- [ ] Soak test theo dõi xu hướng tài nguyên và backlog trong thời gian dài.
- [ ] Đã kiểm tra tính đúng đắn của dữ liệu ghi và hành vi retry/rollback.
- [ ] Có ngưỡng dừng và quy trình dọn dẹp sau test.
- [ ] So sánh trước/sau trong điều kiện tương đương.
- [ ] Báo cáo có execution plan, số liệu, giới hạn và hành động tiếp theo.

Kiểm thử tải ổn định, tải tăng dần, tải đột biến và chạy dài hạn bổ sung cho nhau. Steady-state xác nhận SLO ở mức tải dự kiến; ramp test tìm điểm bão hòa và headroom; spike test kiểm tra phản ứng cùng thời gian phục hồi; soak test phát hiện suy giảm tích lũy. Khi kết hợp workload đại diện, dữ liệu thực tế, số liệu ở cả ứng dụng và database, kết quả sẽ chỉ ra rõ hệ thống có thể phục vụ bao nhiêu tải và cần cải thiện tài nguyên, SQL, index, transaction hay điều phối kết nối ở đâu.
