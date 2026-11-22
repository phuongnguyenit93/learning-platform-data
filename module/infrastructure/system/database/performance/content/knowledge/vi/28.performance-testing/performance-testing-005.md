# Giới hạn của máy phát tải và cách tránh đo nhầm nút thắt

## Vì sao phải kiểm tra năng lực của máy phát tải?

Kiểm thử hiệu năng thường dùng một hoặc nhiều máy phát tải (load generator) để gửi request đến ứng dụng hoặc cơ sở dữ liệu, sau đó đo throughput, latency, tỷ lệ lỗi và mức sử dụng tài nguyên. Kết quả chỉ phản ánh đúng năng lực của hệ thống được kiểm thử khi máy phát tải có thể tạo ra workload theo lịch đã định và ghi nhận đầy đủ thời gian phản hồi.

Máy phát tải cũng là một hệ thống phần mềm có giới hạn. CPU, bộ nhớ, garbage collection, thread pool, event loop, network interface, số socket, cổng TCP tạm thời, DNS, TLS, connection pool và cách ghi kết quả đều có thể trở thành nút thắt. Khi generator bão hòa, nó có thể gửi ít request hơn dự kiến, gửi request trễ, xếp hàng ở phía client hoặc bỏ sót một phần thời gian chờ. Khi đó, throughput quan sát được có thể thấp và latency có thể bị đo sai. Nhóm kiểm thử dễ kết luận nhầm rằng database đã đạt giới hạn, trong khi máy tạo tải mới là thành phần không theo kịp.

Trong tối ưu hiệu năng cơ sở dữ liệu, sai lệch này đặc biệt nguy hiểm. Ví dụ, mục tiêu là đo 8.000 truy vấn/giây nhưng generator chỉ phát được 3.500 truy vấn/giây vì CPU của nó đã đạt 100%. Database vẫn còn CPU, I/O và connection capacity. Kết quả 3.500 truy vấn/giây không phải giới hạn của database; đó chỉ là giới hạn của cấu hình thử nghiệm hiện tại.

Cần phân biệt ba năng lực:
- **Target load:** lượng request hoặc transaction mà kịch bản dự định phát.
- **Offered load:** lượng request thực sự được đưa vào hệ thống theo thời gian.
- **Achieved throughput:** lượng request hệ thống hoàn tất thành công trong một đơn vị thời gian.

Ba giá trị này có thể khác nhau khi generator, mạng hoặc hệ thống đích bị bão hòa. Phải đo và báo cáo riêng chúng. Bài học này hướng dẫn nhận diện giới hạn generator, chọn mô hình tải, tránh coordinated omission, phân phối tải qua nhiều máy và kiểm chứng rằng số liệu latency/throughput đáng tin cậy.

## Mô hình tải quyết định cách diễn giải kết quả

### Closed workload model

Trong mô hình closed, một số lượng người dùng ảo hoặc worker cố định lặp lại chu trình:

1. Gửi request.
2. Chờ response hoàn tất.
3. Nghỉ think time nếu kịch bản có cấu hình.
4. Gửi request tiếp theo.

Số luồng hoạt động được giữ tương đối cố định. Khi hệ thống chậm, mỗi worker dành nhiều thời gian chờ response hơn và tốc độ gửi request tự giảm. Mô hình này phù hợp với câu hỏi như: “Với 200 session đồng thời, người dùng quan sát được thời gian phản hồi và throughput nào?”

Closed model phản ánh một nhóm client có concurrency giới hạn. Nhưng khi server chậm, offered load giảm theo. Nó không tự duy trì một arrival rate cố định trong lúc hệ thống quá tải. Nếu dùng closed model để mô phỏng một luồng sự kiện đến liên tục, kết quả có thể đánh giá thấp độ trễ mà hệ thống sẽ gặp khi request vẫn tiếp tục đến.

### Open workload model

Trong mô hình open, request được lên lịch đến theo một arrival rate độc lập với thời gian hoàn tất request trước đó. Ví dụ, kịch bản đặt mục tiêu gửi 2.000 request/giây trong suốt 10 phút, dù response đang mất 10 ms hay 2 giây.

Mô hình này phù hợp với workload có tốc độ sự kiện đến tương đối độc lập với khả năng xử lý tức thời của hệ thống, chẳng hạn:
- Hàng đợi sự kiện hoặc message consumer nhận dữ liệu liên tục.
- API nhận traffic từ nhiều người dùng độc lập.
- Batch ingest theo lịch.
- Một hệ thống tích hợp gửi request theo nhịp cố định.

Khi server chậm, request đang chờ có thể tích tụ ở generator hoặc ở tầng trung gian. Công cụ phải thể hiện rõ request được gửi đúng lịch, bị trì hoãn, bị drop hay bị dồn vào một đợt sau đó. Nếu generator không đủ khả năng giữ lịch, open model trên cấu hình đó cũng không còn tạo ra offered load như thiết kế.

### Chọn mô hình theo câu hỏi kiểm thử

| Câu hỏi | Mô hình phù hợp để bắt đầu | Điều cần theo dõi |
|---|---|---|
| 100 session liên tục thao tác như người dùng | Closed | Concurrency, think time, latency mỗi vòng |
| Hệ thống nhận 1.500 sự kiện/giây | Open | Scheduled arrivals, actual starts, backlog, drops |
| Tìm giới hạn throughput tối đa | Tăng tải có kiểm soát, có thể dùng cả hai | Offered load, achieved throughput, latency và lỗi |
| Đánh giá hành vi khi quá tải | Open hoặc workload có arrival rate được kiểm soát | Queue growth, rejection, timeout, recovery |
| So sánh cấu hình connection pool | Mô hình tái hiện concurrency ứng dụng | Acquisition wait, active sessions, DB capacity |

Không có một mô hình tốt nhất cho mọi bài kiểm thử. Mô hình phải tương ứng với hành vi thực tế cần mô phỏng. Cũng cần ghi rõ mô hình trong báo cáo vì kết quả của closed và open workload không thể so sánh trực tiếp nếu các điều kiện khác nhau.

## Coordinated omission và độ trễ bị đánh giá thấp

### Hiện tượng

Coordinated omission xảy ra khi máy phát tải chỉ ghi nhận latency cho những request nó thực sự gửi, trong khi bỏ qua hoặc không tính đầy đủ khoảng thời gian mà request đáng lẽ phải được gửi theo lịch nhưng bị trì hoãn do generator hoặc hệ thống đang bận.

Một ví dụ đơn giản: generator được cấu hình gửi một request mỗi 10 ms. Một request mất 1 giây mới hoàn tất. Nếu generator chỉ có một worker tuần tự và chờ response trước khi gửi request tiếp theo, nó sẽ không gửi khoảng 99 request dự kiến trong giây đó. Histogram chỉ ghi nhận request đã gửi và có thể cho thấy ít mẫu chậm hơn workload định kỳ thực tế.

Khi server bị pause, GC, I/O stall hoặc quá tải, khoảng thời gian không có request mới có thể bị bỏ qua. Histogram khi đó không phản ánh trải nghiệm của một luồng arrival cố định.

### Tác động

- Tail latency p95/p99 có thể thấp hơn thực tế.
- Số mẫu latency bị giảm trong thời điểm hệ thống chậm nhất.
- Offered load giảm theo response time, che giấu tình trạng quá tải.
- So sánh hai cấu hình có thể sai nếu một cấu hình tạo ra nhiều khoảng ngừng hơn.
- Nhóm vận hành có thể kết luận hệ thống đáp ứng SLO dù một workload arrival-rate cố định sẽ tích tụ backlog.

### Cách tránh

- Chọn open model khi nghiệp vụ có arrival rate độc lập với response time.
- Dùng công cụ hỗ trợ lịch phát request và ghi nhận scheduled time, actual start time, completion time.
- Ghi cả thời gian chờ trước khi request thực sự được gửi nếu công cụ có cơ chế đó.
- Theo dõi số request dự kiến, số request bắt đầu, số request hoàn tất, số request bị drop và backlog.
- Dùng histogram có độ phân giải đủ cho tail latency, tránh chỉ lấy average.
- Xác nhận công cụ có correction cho coordinated omission hay không và hiểu cách correction hoạt động.
- Không dùng correction như phép thay thế cho generator đủ năng lực; dữ liệu đã không được phát ra vẫn không thể đại diện hoàn toàn cho tải thực.

Một số công cụ benchmark có chế độ phát theo lịch hoặc hiệu chỉnh coordinated omission. Tên tùy chọn và semantics khác nhau. Cần đọc tài liệu công cụ, lưu cấu hình test và nêu rõ correction được bật hay tắt.

## Các giới hạn thường gặp ở máy phát tải

### CPU và lập lịch thread

CPU generator có thể bão hòa vì tạo request, serialize payload, mã hóa TLS, xử lý response, ghi log hoặc tính toán dữ liệu test. Khi CPU bị chiếm hết, worker không được scheduler cấp thời gian đúng lúc. Request có thể bắt đầu muộn dù server còn nhàn.

Dấu hiệu:
- CPU generator duy trì gần 100% trên một hoặc nhiều core.
- Run queue hoặc context switch tăng.
- Actual request starts thấp hơn scheduled arrivals.
- Thread pool có nhiều task pending.
- Latency phía client tăng nhưng server-side execution time không tăng tương ứng.

Kiểm tra mức dùng CPU theo process và core, không chỉ average toàn máy. Một event loop đơn luồng có thể bão hòa một core trong khi tổng CPU máy chỉ ở mức 25%.

### Garbage collection và áp lực bộ nhớ

Generator tạo nhiều object cho request/response, giữ payload hoặc lưu kết quả quá lâu có thể gây allocation rate cao và GC pause. Nếu test ghi toàn bộ response body hoặc lưu mọi mẫu latency trong một cấu trúc lớn, chính instrumentation có thể làm generator chậm.

Dấu hiệu:
- GC pause trùng thời điểm request start bị trễ.
- Heap tăng liên tục hoặc thường xuyên full GC.
- Allocation rate cao.
- CPU tăng khi GC hoạt động.
- Latency client có đỉnh nhưng database không có wait tương ứng.

Dùng bộ nhớ có giới hạn hợp lý, tái sử dụng buffer khi phù hợp, chỉ lưu dữ liệu cần thiết và xuất histogram định kỳ. Không tắt GC để làm đẹp kết quả; cần kiểm tra cấu hình heap và GC gần với môi trường vận hành thực tế.

### Thread pool, event loop và đồng bộ

Một generator dựa trên thread-per-request có thể cạn thread hoặc stack memory. Một generator bất đồng bộ có thể bị giới hạn bởi event loop, callback xử lý nặng hoặc queue nội bộ. Việc dùng synchronous logging, lock chung hoặc cấu trúc dữ liệu cạnh tranh cũng có thể làm request bị chặn.

Cần theo dõi:
- Active threads, queued tasks và rejected tasks.
- Event-loop utilization và thời gian callback.
- Lock contention trong chính generator.
- Số request đang mở và số request chờ gửi.
- Số connection đang dùng so với giới hạn client pool.

Đừng chỉ tăng thread count. Quá nhiều thread có thể làm tăng context switching, memory use và contention. Tìm xem worker bị chặn ở network, CPU, lock hay chờ connection.

### Network interface và đường truyền

Generator có thể hết băng thông hoặc packet processing capacity trước database. Response lớn thường làm giới hạn này xuất hiện sớm hơn request nhỏ. NIC throughput, packet rate, retransmission, dropped packet, socket buffer và network route đều ảnh hưởng.

Dấu hiệu:
- Network TX/RX tiến gần giới hạn NIC.
- Retransmission hoặc packet drop tăng.
- TCP send/receive queue tích tụ.
- Client thấy latency cao nhưng server execution time ổn định.
- Tăng số generator ở cùng một network segment không làm throughput tăng.

Đo cả hai chiều. Với truy vấn trả nhiều hàng, traffic server-to-client có thể lớn hơn request payload rất nhiều. Phải tính response bytes và số hàng trả về trong workload.

### Socket và cổng TCP tạm thời

Nếu generator mở và đóng kết nối vật lý liên tục, nó có thể tiêu thụ nhiều socket và cổng TCP tạm thời. Các kết nối đóng có thể ở trạng thái TIME_WAIT một khoảng thời gian. Khi tạo connection mới với tốc độ cao, generator có thể chạm giới hạn ephemeral ports hoặc chịu overhead TCP handshake.

Dấu hiệu:
- Số socket tăng mạnh.
- Nhiều kết nối TIME_WAIT hoặc trạng thái bất thường.
- Lỗi connect timeout hoặc address/port exhaustion.
- Connection creation rate cao trong khi request throughput không tăng.
- Database có nhiều kết nối ngắn hạn hơn dự kiến.

Dùng connection reuse khi production cũng dùng pool. Nếu mục tiêu là kiểm tra chi phí connect/disconnect, hãy tạo bài test riêng và báo cáo rõ đây là workload mở kết nối mới. Không trộn hai mục tiêu trong cùng một kết quả mà không phân biệt.

### TLS, DNS và xác thực

TLS handshake, certificate validation, DNS lookup và authentication có thể tiêu tốn CPU và round-trip. Nếu mỗi request tạo một kết nối mới, overhead này có thể chi phối phép đo. Nếu production tái sử dụng kết nối lâu dài, generator nên mô phỏng điều đó.

Đo riêng:
- DNS resolution time.
- TCP connect time.
- TLS handshake time.
- Authentication/session initialization.
- Connection pool acquisition.
- Request execution và response read.

Nếu một hostname có nhiều địa chỉ hoặc load balancer phân phối không đều, generator có thể có đường kết nối khác nhau. Kiểm tra DNS caching và endpoint resolution để bảo đảm test mô phỏng hành vi dự kiến.

### Ghi log và thu thập metric

Ghi một dòng log đồng bộ cho từng request có thể trở thành nút thắt I/O. Ghi response body lớn, stack trace hoặc metric label có cardinality rất cao cũng tiêu tốn CPU và bộ nhớ. Nếu ghi file trên cùng thiết bị với database test hoặc dùng chung network storage, phép đo có thể bị ảnh hưởng.

Dùng histogram/counter tổng hợp, sampling có kiểm soát và xuất metric theo batch. Ghi đủ dữ liệu để phân tích nhưng tránh biến công cụ đo thành workload nặng hơn workload cần đo.

## Phân biệt nút thắt của generator với nút thắt của database

### Không dựa vào một metric đơn lẻ

CPU generator cao không tự chứng minh generator là nút thắt nếu server cũng bão hòa. Ngược lại, CPU database thấp không chứng minh database còn dư năng lực nếu workload đang bị giới hạn bởi lock, I/O, connection pool hoặc network.

Cần quan sát hai phía trên cùng một trục thời gian:
- Generator: CPU, memory, GC, thread/event loop, connection pool, scheduled arrivals, actual starts, pending queue, dropped requests, network và logging.
- Ứng dụng: request queue, worker threads, connection acquisition, application CPU, serialization, retry và timeout.
- Database: active sessions, query throughput, CPU, I/O latency, lock waits, buffer/cache, temp usage, log flush, connection count và query execution time.
- Mạng: throughput, round-trip, retransmission, packet drop và queue ở các hop liên quan.

Dùng đồng bộ thời gian giữa các máy để đối chiếu sự kiện. Clock skew có thể làm sai tương quan giữa lúc generator phát request và lúc database ghi nhận truy vấn. Dùng NTP hoặc cơ chế đồng bộ phù hợp, đồng thời ưu tiên trace ID và timestamp monotonic trong từng process cho duration nội bộ.

### Ma trận dấu hiệu chẩn đoán

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| Generator CPU cao, scheduled arrivals tăng nhưng actual starts hụt; DB CPU thấp | Generator CPU hoặc scheduler bị giới hạn |
| Generator GC pause trùng với khoảng ngừng gửi; DB không có spike tương ứng | Áp lực heap/GC ở generator |
| Generator network TX/RX chạm giới hạn, response lớn | NIC hoặc đường truyền là nút thắt |
| Generator connection pool pending tăng, DB session count thấp | Pool client hoặc giới hạn connection ở tầng ứng dụng |
| DB CPU cao, active queries nhiều, generator còn headroom | Database compute hoặc query plan |
| DB I/O latency và read/write queue tăng | Storage/I/O của database |
| Lock wait tăng, CPU DB không cao | Tranh chấp transaction hoặc hot rows |
| Client latency cao, server query duration thấp, network tăng | Network, fetch hoặc client processing |
| Offered load đúng lịch, DB throughput đứng yên, queue và latency tăng | Server-side saturation hoặc giới hạn downstream |
| Throughput tăng khi thêm generator nhưng cấu hình DB không đổi | Generator trước đó có thể là giới hạn |

Đây là ma trận định hướng điều tra, không phải kết luận tự động. Cần kiểm tra cùng lúc các metric và plan của truy vấn đại diện.

### Phân rã thời gian request

Một request database có thể gồm:

~~~text
client_elapsed =
    generator_queue_wait
  + client_connection_acquire
  + network_connect_or_round_trip
  + application_or_driver_work
  + database_server_work
  + result_transfer_and_fetch
  + client_result_processing
~~~

Các thành phần có thể chồng lấp, đặc biệt khi driver dùng asynchronous I/O, streaming hoặc pipeline. Không cộng các duration nếu chúng đã bao gồm nhau. Mục tiêu là xác định điểm bắt đầu/kết thúc của từng metric và tìm phần tăng bất thường.

Nếu database query statistics báo server elapsed thấp nhưng client latency cao, hãy xem pool wait, network round-trip, fetch, response processing và generator queue. Nếu client bắt đầu request đúng lịch nhưng server elapsed tăng, hãy xem execution plan, waits, lock, CPU và I/O của database.

### Phân biệt queue ở từng tầng

Một hệ thống có thể có nhiều hàng đợi:
- Load generator queue trước khi request được gửi.
- Client connection pool queue.
- Web server hoặc application worker queue.
- Database connection/session queue.
- Lock wait hoặc I/O queue trong database.
- Network buffer/queue.
- Consumer hoặc downstream service queue.

Nếu chỉ đo end-to-end latency, tất cả có thể bị gộp thành một con số. Instrument từng queue hoặc dùng distributed tracing để tìm nơi thời gian chờ tăng lên.

## Xác minh generator có đủ năng lực phát tải

### Kiểm tra trên endpoint nhẹ hoặc hệ thống sink

Trước khi benchmark database, hãy xác minh generator có thể phát được tốc độ mục tiêu đến một endpoint nhẹ, mock server hoặc sink được kiểm soát. Endpoint này nên có chi phí xử lý thấp và khả năng tiếp nhận đủ lớn để không trở thành giới hạn mới.

Mục tiêu là đo:
- Generator phát được bao nhiêu request/giây khi response nhỏ.
- Generator xử lý được bao nhiêu response/giây với kích thước tương tự workload thật.
- CPU, GC, network và thread utilization ở mức tải mục tiêu.
- Scheduled arrivals có được bắt đầu đúng thời điểm không.
- Histogram và metric exporter có gây thêm tải đáng kể không.

Một endpoint sink chỉ kiểm tra năng lực phát tải cơ bản; nó không mô phỏng chi phí JDBC, TLS, response lớn hoặc dữ liệu database. Sau đó vẫn phải hiệu chuẩn trên đường đi gần với workload thực tế.

### Tăng tải theo từng nấc

Chạy các mức tải tăng dần, ví dụ 10%, 25%, 50%, 75%, 100% và 125% mục tiêu. Ở mỗi mức, giữ đủ thời gian để quan sát trạng thái ổn định và ghi:
- Target arrival rate.
- Actual request start rate.
- Completion throughput.
- Queue depth và dropped/rejected requests.
- Generator CPU, GC, network và connection metrics.
- Database CPU, I/O, lock, sessions và query latency.

Nếu actual start rate bắt đầu tụt so với target trước khi database bão hòa, generator hoặc đường truyền đã trở thành giới hạn. Không tiếp tục tăng concurrency một cách mù quáng; cần thêm generator, tối ưu client hoặc điều chỉnh cách phát tải rồi đo lại.

### Headroom của generator

Generator nên còn dư tài nguyên ở mức tải mục tiêu để xử lý burst và dao động. Không có một ngưỡng CPU hoặc memory chung cho mọi công cụ, nhưng nếu generator liên tục chạm giới hạn CPU, NIC, thread pool hoặc event loop thì phép thử không còn đáng tin.

Có thể bắt đầu bằng cách giữ CPU generator dưới vùng bão hòa rõ rệt, không để GC pause dài trùng thời điểm phát tải, giữ network utilization dưới giới hạn thực tế và bảo đảm queue không tăng liên tục. Mức headroom cụ thể phải được xác định qua thử nghiệm và đặc điểm môi trường.

Không chỉ nhìn average. Một core bão hòa, một event loop bị block hoặc một NIC RX queue quá tải có thể làm request trễ trong khi metric tổng của máy trông còn thấp.

### Dùng nhiều generator

Khi một máy không đủ năng lực, phân phối tải qua nhiều máy độc lập. Tổng offered load là tổng tải các generator thực sự phát được, không phải tổng target đã cấu hình.

Ví dụ, ba generator mỗi máy được cấu hình 2.000 request/giây không chứng minh hệ thống nhận 6.000 request/giây. Phải đo actual starts và completion ở từng máy, phát hiện máy yếu hoặc mất kết nối, rồi tổng hợp histogram đúng cách.

Khi scale out:
- Chia workload và dữ liệu test để tránh tất cả generator truy cập cùng một key nóng nếu production không như vậy.
- Dùng cùng phiên bản kịch bản, dữ liệu và cấu hình cần thiết.
- Đồng bộ thời gian và gắn generator ID vào metric.
- Theo dõi từng máy để phát hiện một generator bão hòa sớm.
- Tránh tất cả máy khởi tạo TLS hoặc connection đồng thời gây connection storm không giống production.
- Tổng hợp histogram từ bucket/count hoặc dữ liệu percentile có thể merge; không lấy trung bình các p95 riêng lẻ.
- Tính tổng request lỗi, timeout, dropped và backlog ở mọi máy.

Nếu mỗi generator dùng cùng seed ngẫu nhiên, chúng có thể tạo ra cùng chuỗi key và vô tình gây hot-key contention. Dùng seed khác nhau hoặc phân vùng key có chủ đích, tùy mục tiêu kiểm thử.

## Workload phải phản ánh cách ứng dụng dùng database

### Tốc độ request và thời gian suy nghĩ

Với closed model, concurrency và think time quyết định arrival rate. Một nhóm 100 virtual users với thời gian response 50 ms và think time 150 ms có thể tạo tốc độ xấp xỉ:

~~~text
throughput ~= users / (response_time + think_time)
            ~= 100 / (0.05 + 0.15)
            ~= 500 requests/second
~~~

Đây là ước lượng theo mô hình ổn định, giả định mỗi user chỉ có một request đang chạy tại một thời điểm và các thời gian được tính bằng giây. Khi response time tăng, throughput của closed model sẽ giảm nếu số user và think time giữ nguyên.

Với open model, arrival rate được cấu hình độc lập. Nếu hệ thống hoàn tất chậm hơn tốc độ request đến, backlog sẽ tăng. Phải xác định công cụ có queue không giới hạn, queue có giới hạn, drop hay schedule delay. Các hành vi này làm kết quả khác nhau.

### Phân bố dữ liệu và tính locality

Generator có thể vô tình tạo workload quá dễ cho cache hoặc quá khó so với production:
- Luôn truy vấn cùng một vài khóa làm buffer cache nóng và lock contention tập trung.
- Sinh khóa tuần tự khiến index locality khác với phân bố ngẫu nhiên.
- Chỉ dùng tenant nhỏ bỏ qua tenant lớn và skew.
- Dùng dữ liệu mới hoàn toàn làm cache lạnh trong suốt test.
- Chỉ đọc một bảng mà production thường join nhiều bảng.
- Không mô phỏng tỷ lệ read/write hoặc transaction size thực tế.

Dùng phân bố key, tenant, thời gian, trạng thái và tỷ lệ truy vấn gần với workload cần đánh giá. Nếu mục tiêu là kiểm tra worst-case, hãy thiết kế kịch bản riêng và ghi rõ đó là tải stress hoặc skew test.

### Connection reuse và transaction duration

Nếu production dùng connection pool, generator nên dùng connection reuse tương ứng. Tạo kết nối mới cho từng request sẽ biến bài test query thành bài test TCP/TLS/authentication và connection churn.

Cần mô phỏng:
- Số client/session đồng thời.
- Pool size và acquisition timeout.
- Transaction duration và số statement mỗi transaction.
- Auto-commit hay transaction nhiều bước.
- Tỷ lệ commit/rollback.
- Prepared statement và parameter distribution.
- Fetch size và lượng dữ liệu trả về.

Một generator có pool lớn hơn nhiều so với production có thể che giấu connection acquisition bottleneck ở ứng dụng. Pool nhỏ bất thường có thể tạo bottleneck giả ở phía client. Hãy ghi rõ cấu hình và mục tiêu của từng test.

## Thiết kế một phép thử đáng tin cậy

### Warm-up, ramp-up, steady state và cooldown

Một kịch bản thường chia thành:
1. **Warm-up:** khởi tạo connection, nạp JIT/cache và ổn định các thành phần.
2. **Ramp-up:** tăng tải dần để tránh một connection storm hoặc spike không chủ ý.
3. **Steady state:** giữ mức tải mục tiêu đủ lâu để đo throughput, latency và tài nguyên.
4. **Cooldown:** giảm tải có kiểm soát và quan sát backlog, queue, connection cùng tài nguyên có phục hồi không.

Không lấy thời gian warm-up vào cùng thống kê steady-state nếu mục tiêu là đo trạng thái ổn định. Nhưng cũng không bỏ qua warm-up nếu cold start là một phần của yêu cầu sản phẩm; hãy báo cáo riêng cold-start test.

### Lặp lại và so sánh

Chạy lặp lại với cùng dữ liệu, cấu hình, phiên bản, workload và môi trường. Ghi nhận biến động giữa các lần chạy. Không so sánh một lần chạy cold-cache với một lần chạy warm-cache rồi quy toàn bộ chênh lệch cho thay đổi code.

Khi so sánh hai phiên bản:
- Giữ nguyên generator count và cấu hình.
- Giữ cùng target arrival rate hoặc cùng concurrency model.
- Giữ cùng dữ liệu và phân bố key.
- Giữ cùng thời gian warm-up/steady-state.
- Theo dõi các tài nguyên của cả generator và database.
- Ghi lại deploy, background jobs, checkpoint, backup và các sự kiện có thể ảnh hưởng.

### Histogram và tail latency

Average che giấu các request chậm. Dùng histogram để tính p50, p90, p95, p99 và khi cần p99.9. Lưu ý:
- Không lấy trung bình các percentile của từng generator.
- Merge histogram bằng bucket/count hoặc cơ chế merge tương ứng.
- Đảm bảo cùng đơn vị và cùng khoảng thời gian.
- Ghi số lượng mẫu để biết percentile có đủ mẫu hay không.
- Theo dõi timeout và dropped request riêng; chúng không nên biến mất khỏi báo cáo latency.
- Không loại bỏ outlier mà không có quy tắc và lý do rõ ràng.

Nếu một request timeout sau 5 giây, ghi nó là timeout/error và tính vào tỷ lệ lỗi; không đơn giản loại khỏi histogram khiến p99 trông tốt hơn.

### Định nghĩa thành công của phép thử

Một test chỉ đạt khi đồng thời thỏa:
- Offered load thực tế đạt mục tiêu trong steady-state.
- Generator còn headroom và không có queue tăng liên tục ngoài thiết kế.
- Tỷ lệ lỗi/timeout/drop nằm trong giới hạn.
- Throughput thành công đạt yêu cầu.
- p95/p99 đáp ứng SLO.
- Database và ứng dụng không vượt giới hạn tài nguyên hoặc gây suy giảm workload khác.
- Số liệu đầy đủ để giải thích nơi phát sinh latency.

Nếu generator không đạt offered load, kết quả nên được đánh dấu **inconclusive / generator-limited**, không báo là database đã đạt capacity.

## Ví dụ: generator bị bão hòa trước database

Một nhóm muốn kiểm tra API báo cáo đọc dữ liệu từ PostgreSQL ở mức 5.000 request/giây. Kịch bản dùng một generator với 300 virtual users, mỗi request đọc 200 hàng và parse JSON response.

Kết quả đầu tiên:
- Target arrival rate: 5.000 request/giây.
- Actual request starts: dao động quanh 2.700 request/giây.
- Successful throughput: khoảng 2.650 request/giây.
- Client p99: 900 ms.
- Generator CPU: một core ở 100%, event-loop delay tăng.
- Database CPU: 42%, storage latency ổn định, active sessions thấp hơn pool limit.
- Server-side query p95: 35 ms.

Nếu chỉ nhìn successful throughput, nhóm có thể cho rằng database chỉ xử lý được khoảng 2.650 request/giây. Nhưng target và actual starts đã lệch rất xa. Server-side query duration cũng thấp hơn nhiều client latency.

Nhóm kiểm tra generator và thấy callback parse JSON đồng bộ chạy trên event loop, khiến event loop không gửi request mới đúng lịch. Sau khi chuyển xử lý response nặng sang worker phù hợp và chia tải qua hai generator, actual starts đạt gần target. Khi đó database CPU và I/O tăng, lock wait xuất hiện và server throughput bắt đầu ổn định ở một mức thấp hơn target. Đây mới là dữ liệu có thể dùng để điều tra capacity của database.

Bài học từ ví dụ:
1. Target load không chứng minh offered load đã đến server.
2. Client p99 bao gồm thời gian ở generator, network và server.
3. Server query duration thấp cùng generator event-loop delay cao là dấu hiệu cần điều tra client.
4. Sau khi sửa generator, phải chạy lại baseline vì bottleneck thực có thể thay đổi.
5. Không dùng kết quả trước khi generator đủ năng lực để kết luận giới hạn database.

Các con số chỉ minh họa cách chẩn đoán. Trong môi trường thật, phải đối chiếu trace, request counters và metric đồng bộ từ từng tầng.

## Quy trình hiệu chuẩn load generator

1. **Xác định mục tiêu:** throughput, concurrency, arrival rate, latency SLO, transaction mix và kích thước response.
2. **Chọn workload model:** closed hoặc open theo hành vi hệ thống cần mô phỏng.
3. **Kiểm tra kịch bản:** bảo đảm payload, parameter distribution, think time, transaction và connection reuse hợp lý.
4. **Chạy generator không có database bottleneck:** dùng sink hoặc endpoint nhẹ để đo năng lực phát và xử lý response.
5. **Tăng tải từng nấc:** theo dõi target, actual starts, completions, queue và drop.
6. **Theo dõi tài nguyên generator:** CPU theo core, GC, heap, threads/event loop, socket, NIC, DNS/TLS và logging.
7. **Thử kích thước response gần thực tế:** response lớn có thể làm client bão hòa sớm hơn nhiều so với response nhỏ.
8. **Thêm generator khi cần:** phân phối tải, xác nhận từng máy còn headroom và tổng offered load đạt mục tiêu.
9. **Chạy với database thật:** theo dõi đồng thời generator, ứng dụng, network và database.
10. **Phân rã latency:** tách generator queue, pool wait, network, server execution, fetch và client processing.
11. **Lặp lại phép thử:** giữ cùng điều kiện và kiểm tra độ ổn định.
12. **Gắn nhãn kết quả:** server-limited, generator-limited, network-limited, client-pool-limited hoặc inconclusive khi bằng chứng chưa đủ.

## Những câu hỏi phải trả lời trước khi công bố kết quả

### Offered load có thực sự đạt mục tiêu?

So sánh scheduled arrivals với actual request starts. Nếu công cụ không xuất scheduled count, hãy dùng metric tương đương hoặc một bộ đếm độc lập. Completion throughput không thay thế offered load vì request có thể đang chờ hoặc bị drop.

### Generator có còn headroom?

Xem CPU theo core, GC pause, event-loop delay, thread queue, memory, NIC và socket. Không chỉ xem average CPU toàn máy. Một resource bão hòa có thể giới hạn toàn bộ generator.

### Có request bị trì hoãn hoặc mất khỏi thống kê?

Kiểm tra dropped/rejected request, schedule lag, queue depth, timeout và retry. Xác định công cụ có ghi nhận coordinated omission hay correction không. Không loại timeout khỏi tỷ lệ lỗi.

### Latency được đo ở đâu?

Xác định timer bắt đầu trước hay sau khi lấy connection, trước hay sau khi request được gửi, và kết thúc khi nhận byte đầu tiên hay đọc hết response. Client elapsed và database server execution time có phạm vi khác nhau.

### Database có thực sự là nút thắt?

Đối chiếu throughput, CPU, I/O latency, lock waits, active sessions, connection queue, execution plan và wait events. Nếu database chưa bão hòa mà generator không phát đủ tải, chưa thể kết luận capacity của database.

### Workload có đại diện?

Kiểm tra tỷ lệ đọc/ghi, transaction size, query mix, dữ liệu skew, cache warmth, response size, connection reuse và concurrency. Một kịch bản quá đơn giản có thể làm database nhanh hơn thực tế; một kịch bản tạo hot key không có chủ đích có thể làm nó chậm giả tạo.

## Những sai lầm thường gặp

- **Dùng target rate làm throughput báo cáo:** target chỉ là cấu hình, phải đo actual starts và completions.
- **Coi mọi latency client là thời gian database:** client time còn gồm queue, pool, network, fetch và xử lý response.
- **Dùng closed model để kết luận về arrival rate cố định:** response chậm làm tốc độ phát tự giảm.
- **Bỏ qua coordinated omission:** các khoảng request đáng lẽ đến nhưng không được gửi có thể biến mất khỏi histogram.
- **Chỉ xem CPU tổng của generator:** một core hoặc event loop có thể bão hòa trước.
- **Dùng response nhỏ để hiệu chuẩn workload response lớn:** network và parsing cost không tương đương.
- **Tạo TCP/TLS connection cho mọi request khi production reuse connection:** vô tình đo connection churn.
- **Tăng số thread vô hạn:** context switching và memory pressure có thể làm generator tệ hơn.
- **Ghi log đồng bộ từng request:** instrumentation có thể trở thành bottleneck.
- **Chỉ xem average latency:** p95/p99 và timeout có thể rất xấu.
- **Lấy trung bình p95 giữa nhiều generator:** percentile không thể gộp bằng cách lấy trung bình các percentile.
- **Không đo backlog và dropped requests:** số liệu có thể bỏ qua phần tải chưa được xử lý.
- **Dùng cùng random seed trên mọi generator:** có thể tạo phân bố key bất thường và hot-key contention.
- **Không đồng bộ thời gian:** khó ghép request với trace và database metrics.
- **Kết luận database đã hết capacity khi generator hụt tải:** đây là phép thử generator-limited.
- **Không chạy lại sau khi sửa generator:** bottleneck thật có thể chỉ xuất hiện khi offered load đạt mục tiêu.

## Checklist đánh giá máy phát tải

- [ ] Đã xác định rõ target load, offered load và achieved throughput.
- [ ] Đã chọn closed/open workload model phù hợp.
- [ ] Đã kiểm tra scheduled arrivals và actual request starts.
- [ ] Đã xác minh công cụ xử lý coordinated omission và ghi rõ correction.
- [ ] Đã đo generator CPU theo core, GC, heap và event-loop/thread utilization.
- [ ] Đã theo dõi connection pool, socket, ephemeral ports và connection creation rate.
- [ ] Đã đo NIC throughput, packet loss, retransmission và network latency.
- [ ] Đã kiểm tra chi phí TLS, DNS, serialization, response parsing và logging.
- [ ] Đã ghi nhận pending queue, schedule lag, dropped, timeout và retry.
- [ ] Đã kiểm tra response size, data distribution và query mix đại diện.
- [ ] Đã đối chiếu generator metrics với application và database metrics cùng thời gian.
- [ ] Đã dùng histogram để đánh giá p95/p99 và merge dữ liệu nhiều generator đúng cách.
- [ ] Đã chạy ramp-up, steady-state, cooldown và lặp lại có kiểm soát.
- [ ] Đã xác nhận generator còn headroom tại mức tải được công bố.
- [ ] Nếu generator không đủ năng lực, kết quả được đánh dấu generator-limited/inconclusive.

## Kết luận

Máy phát tải là một phần của hệ thống kiểm thử và có thể trở thành nút thắt trước ứng dụng hoặc database. Khi CPU, event loop, GC, thread pool, network, socket, TLS hoặc logging của generator bị giới hạn, offered load sẽ thấp hơn target. Client latency cũng có thể bao gồm thời gian chờ ở generator và các tầng trung gian, vì vậy không thể xem nó là database execution time.

Hãy chọn workload model đúng, đo scheduled arrivals và actual starts, theo dõi queue/drop, kiểm tra coordinated omission và hiệu chuẩn generator bằng workload có kích thước response gần thực tế. Trong lúc benchmark, đối chiếu tài nguyên của generator, ứng dụng, mạng và database trên cùng khoảng thời gian. Chỉ khi generator duy trì được offered load mục tiêu với headroom và số liệu đầy đủ, throughput cùng tail latency mới có thể dùng để đánh giá giới hạn của hệ thống cơ sở dữ liệu.