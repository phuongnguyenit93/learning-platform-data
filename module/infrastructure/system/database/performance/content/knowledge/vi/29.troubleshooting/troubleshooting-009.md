# Sự cố bản sao đọc chậm và chuyển tải làm quá tải máy chính

## Vì sao replica chậm có thể làm primary quá tải?

Nhiều hệ thống cơ sở dữ liệu dùng bản sao đọc (read replica) để phân phối truy vấn đọc, giảm tải cho máy chính (primary) và tăng khả năng phục vụ báo cáo. Primary tiếp nhận ghi, tạo transaction log hoặc WAL rồi truyền thay đổi đến replica. Replica nhận log, áp dụng thay đổi và phục vụ các truy vấn đọc trên trạng thái dữ liệu của nó.

Nếu replica áp dụng log chậm, dữ liệu trên replica có thể cũ hơn primary. Bộ định tuyến truy vấn hoặc lớp ứng dụng có thể đánh dấu replica là không khỏe, ngừng gửi truy vấn đến replica và chuyển chúng về primary. Cách xử lý này bảo đảm truy vấn tiếp tục được phục vụ trong một số tình huống, nhưng có thể tạo ra vòng phản hồi nguy hiểm:

1. Replica bị lag do tải đọc, tải áp dụng log, I/O hoặc mạng.
2. Bộ định tuyến giảm hoặc ngừng gửi truy vấn đọc đến replica.
3. Các truy vấn đọc dồn về primary.
4. Primary phải vừa xử lý ghi vừa xử lý thêm đọc.
5. CPU, I/O, cache, connection và lock trên primary tăng.
6. Ghi chậm hơn, log được tạo hoặc checkpoint xử lý chậm hơn; replica có thể càng khó bắt kịp.
7. Bộ định tuyến tiếp tục loại replica và giữ tải ở primary.

Kết quả có thể là cả primary lẫn replica đều chậm. Đây là sự cố chuyển tải (fallback/rerouting overload), không chỉ là vấn đề replication lag đơn lẻ.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần quan sát đồng thời replication, tải đọc/ghi, chính sách định tuyến và năng lực dự phòng của primary. Không thể coi replica là nơi có thể nhận toàn bộ truy vấn đọc thay cho primary trong mọi tình huống. Primary thường cần phần năng lực dự trữ cho ghi, transaction quan trọng, phục hồi replica và các tác vụ quản trị.

Bài học này trình bày cách phân biệt transport lag và apply lag, nhận diện replica chậm, hiểu tác động của stale read, thiết kế chính sách routing/fallback có giới hạn, giảm tải khi primary tiến gần bão hòa và đưa replica trở lại phục vụ theo cách có kiểm soát.

## Mô hình primary và read replica

### Luồng thay đổi dữ liệu

Trong mô hình replication phổ biến:
- Ứng dụng gửi INSERT, UPDATE, DELETE hoặc transaction ghi đến primary.
- Primary tạo transaction log/WAL/binlog hoặc luồng thay đổi tương đương.
- Log được gửi qua mạng đến replica.
- Replica nhận và lưu log vào vùng chờ.
- Replication receiver/IO thread hoặc thành phần tương đương chuyển log vào nơi lưu trữ.
- Replication applier/redo thread áp dụng thay đổi lên dữ liệu replica.
- Truy vấn đọc trên replica nhìn thấy dữ liệu theo mức độ log đã được áp dụng và quy tắc nhất quán của engine.

Tên tiến trình và chi tiết phụ thuộc hệ quản trị. PostgreSQL physical streaming replication dùng WAL sender/receiver và startup/recovery process; MySQL replication có receiver và applier worker; SQL Server Availability Groups có log transport và redo. Một số hệ thống phân tán có replication theo partition hoặc theo consensus.

### Transport lag và apply lag

Cần phân biệt ít nhất hai giai đoạn:

- **Transport/send lag:** log đã được primary tạo nhưng chưa được chuyển đến replica hoặc chưa được replica nhận đầy đủ. Nguyên nhân thường liên quan network, sender queue, receiver, băng thông hoặc khả năng ghi log nhận.
- **Apply/replay lag:** log đã đến replica nhưng replica chưa áp dụng kịp vào trạng thái dữ liệu có thể đọc. Nguyên nhân có thể là CPU, I/O, redo/applier throughput, transaction lớn, lock hoặc tranh chấp với workload đọc.

Một replica có thể nhận log gần như tức thời nhưng replay chậm. Khi đó tăng băng thông mạng không giải quyết được nút thắt. Ngược lại, nếu log chưa đến replica, tối ưu query đọc trên replica có thể không giải quyết nguyên nhân chính.

### Sơ đồ luồng và vòng phản hồi

~~~mermaid
flowchart TD
    A[Ứng dụng ghi] --> P[Primary]
    P --> L[Transaction log / WAL]
    L --> T[Truyền log qua mạng]
    T --> R[Replica nhận log]
    R --> AP[Replica áp dụng log]
    AP --> Q[Replica phục vụ truy vấn đọc]
    Q --> U[Ứng dụng đọc]

    AP --> H{Replica đủ mới và khỏe?}
    H -->|Có| Q
    H -->|Không| RT[Router giảm hoặc dừng traffic]
    RT --> F[Fallback đọc về primary]
    F --> P
    F --> O[Primary tăng CPU, I/O, cache và connection]
    O --> W[Ghi và xử lý log chậm hơn]
    W --> L
~~~

Fallback giúp duy trì khả năng đọc khi replica không đáp ứng chính sách, nhưng nếu không giới hạn có thể tạo vòng phản hồi làm primary quá tải. Chính sách routing phải tính đến năng lực dự phòng, không chỉ trạng thái up/down của replica.

## Các loại lag và cách đo

### Lag theo vị trí log

Một cách đo là so sánh vị trí log mà primary đã tạo với vị trí replica đã nhận hoặc đã áp dụng. Với PostgreSQL, có thể quan sát LSN của WAL và các vị trí write/flush/replay. Với MySQL, có thể so sánh source log coordinates hoặc GTID với trạng thái replica. Với SQL Server, có thể theo dõi log send queue và redo queue.

Khoảng cách log phản ánh lượng công việc còn phải truyền hoặc áp dụng, nhưng không trực tiếp bằng số giây trễ. Cùng một lượng byte log có thể mất vài giây để áp dụng khi tải thấp, nhưng mất lâu hơn nhiều khi replica đang bận hoặc transaction có chi phí redo cao.

### Lag theo thời gian

Một số hệ thống báo thời gian trễ ước lượng:
- MySQL có Seconds_Behind_Source hoặc trường tương đương theo phiên bản và topology.
- PostgreSQL có thể ước lượng replay delay bằng timestamp hoặc so sánh vị trí WAL, nhưng cách diễn giải phụ thuộc workload và hoạt động ghi.
- SQL Server cung cấp các chỉ số queue và thời gian gửi/redo theo DMV.

Không dùng một trường seconds-behind làm thước đo duy nhất. Nếu primary không có ghi mới, timestamp cuối cùng có thể cũ dù replica đã theo kịp toàn bộ log. Một transaction lớn hoặc workload burst cũng có thể làm số đo thời gian thay đổi theo cách không phản ánh chính xác độ trễ của từng hàng.

### Đo riêng send, receive, flush và apply

Tùy engine, nên thu thập các mốc:
- Log được tạo tại primary.
- Log được gửi đi.
- Log đã được replica nhận.
- Log đã được flush bền vững tại replica.
- Log đã được replay/redo và có thể đọc.
- Replica đã xác nhận trạng thái đồng bộ nếu topology yêu cầu.

Phân biệt các mốc này giúp xác định log đang bị nghẽn ở mạng, ghi log replica hay apply. Trong hệ thống đồng bộ, một số mốc còn quyết định khi nào primary được phép xác nhận commit.

### Các chỉ số nên theo dõi

| Nhóm | Chỉ số | Câu hỏi chẩn đoán |
|---|---|---|
| Replication | Send queue / receive queue | Log có bị tồn trước khi đến replica không? |
| Replication | Replay/redo/apply queue | Replica có nhận log nhưng áp dụng chậm không? |
| Replication | LSN/GTID/log position gap | Khoảng cách log tăng hay giảm? |
| Replication | Apply throughput, bytes/sec | Replica áp dụng được bao nhiêu log mỗi giây? |
| Replica | CPU, I/O latency, queue depth | Tài nguyên nào giới hạn apply? |
| Replica | Active queries, lock waits | Truy vấn đọc có cạnh tranh với apply không? |
| Primary | CPU, I/O, log generation, sessions | Primary còn đủ headroom cho fallback không? |
| Router | Traffic theo node, retry, fallback count | Bao nhiêu tải đang bị chuyển về primary? |
| Application | Read latency, timeout, stale-read rate | Ảnh hưởng người dùng là gì? |
| Network | Throughput, RTT, retransmission | Đường truyền có giới hạn replication không? |

Theo dõi cả giá trị hiện tại, tốc độ thay đổi và xu hướng trong một cửa sổ thời gian. Một queue lớn nhưng đang giảm có thể đang hồi phục; queue nhỏ nhưng tăng nhanh có thể là dấu hiệu sắp mất khả năng bắt kịp.

## Vì sao replica bị chậm?

### Tải đọc cạnh tranh với replication apply

Replica vừa áp dụng thay đổi vừa phục vụ truy vấn đọc. Query scan lớn, sort, hash join hoặc aggregation có thể chiếm CPU, memory và I/O, khiến applier ít tài nguyên hơn. Tùy engine và cơ chế replication, truy vấn đọc dài còn có thể giữ snapshot hoặc gây xung đột với việc dọn phiên bản cũ.

Ví dụ, một báo cáo quét nhiều tháng dữ liệu trên replica có thể làm I/O queue tăng. Applier phải chờ I/O, replay lag tăng và router loại replica khỏi nhóm đọc. Sau đó báo cáo và truy vấn OLTP cùng dồn về primary.

Cần phân biệt:
- Replica chậm vì truy vấn đọc tiêu thụ tài nguyên.
- Replica chậm vì log apply cần CPU/I/O nhiều.
- Replica chậm vì một transaction lớn hoặc DDL gây chặn.
- Replica chậm vì conflict giữa query snapshot và recovery/applier.

Biện pháp có thể là giới hạn concurrency của báo cáo, tách replica OLAP khỏi replica OLTP, giảm truy vấn scan, tăng tài nguyên replica hoặc dùng cơ chế ưu tiên tài nguyên nếu engine hỗ trợ.

### Transaction lớn và burst ghi

Một transaction lớn có thể tạo nhiều log và cần nhiều công việc redo. Một burst ghi trên primary có thể tạo log nhanh hơn khả năng truyền hoặc áp dụng của replica.

Các tình huống thường gặp:
- Bulk update hoặc batch import.
- Rebuild index hoặc DDL có ảnh hưởng replication.
- Xóa dữ liệu lớn.
- Cập nhật nhiều hàng trong cùng transaction.
- Tăng đột biến số event hoặc order.
- Một thay đổi schema khiến replica phải thực hiện công việc tốn kém.

Cần xem log generation rate so với send/apply rate. Nếu tốc độ tạo log liên tục cao hơn tốc độ áp dụng, lag sẽ tăng dù replica không có query đọc. Điều chỉnh batch size, chia transaction, giới hạn tốc độ ghi hoặc lên lịch maintenance có thể giúp giảm burst, nhưng phải giữ đúng yêu cầu atomicity và nghiệp vụ.

### Nút thắt CPU hoặc I/O ở replica

Nếu apply throughput thấp và CPU replica bão hòa, kiểm tra số worker, redo parallelism, CPU quota, context switching và các truy vấn đọc đang chạy. Nếu I/O latency cao, kiểm tra data file, log file, temp storage, queue depth và giới hạn volume.

Tăng số applier worker không phải lúc nào cũng tăng tốc. Các transaction có phụ thuộc hoặc cập nhật cùng vùng dữ liệu có thể bị tuần tự hóa; thêm worker có thể tăng contention. Hãy đo trước/sau và xem khả năng song song hóa thực tế của engine.

### Mạng hoặc cấu hình replication

Transport lag có thể do:
- Băng thông mạng không đủ.
- RTT cao hoặc packet retransmission.
- Primary sender bị giới hạn CPU hoặc I/O.
- Replica receiver ghi log nhận chậm.
- TLS hoặc proxy tạo overhead.
- Replication slot hoặc log retention làm tăng áp lực lưu trữ.
- Cấu hình đồng bộ/async hoặc compression không phù hợp.

Kiểm tra log send rate, receive rate, network throughput, RTT và lỗi kết nối. Không đổi replication mode hoặc tắt durability để che lag mà chưa đánh giá khả năng mất dữ liệu và RPO.

### Query đọc dài và xung đột recovery

Một số engine có thể hủy truy vấn trên standby/replica nếu truy vấn giữ snapshot quá lâu và xung đột với việc áp dụng thay đổi hoặc dọn dữ liệu cũ. PostgreSQL hot standby có thể báo conflict với recovery; SQL Server readable secondary và các engine khác có quy tắc riêng.

Điều chỉnh thời gian chờ hoặc cho phép delay recovery có thể giảm query cancellation nhưng làm tăng replication lag. Đây là đánh đổi giữa freshness và khả năng phục vụ truy vấn dài. Cần đặt giới hạn rõ ràng và tách workload phù hợp.

## Vì sao fallback có thể làm primary quá tải?

### Mất năng lực đọc dự phòng

Giả sử hệ thống có một primary và hai read replica. Mỗi replica bình thường xử lý 35% traffic đọc; primary xử lý 30% traffic đọc cùng toàn bộ ghi. Nếu một replica bị loại, traffic của nó có thể được chia cho replica còn lại và primary. Nếu cả hai replica bị loại, toàn bộ traffic đọc có thể dồn về primary.

Primary vốn đã xử lý:
- Transaction ghi và log generation.
- Index maintenance và constraint checks.
- Checkpoint, vacuum/cleanup hoặc background tasks.
- Các truy vấn đọc quan trọng không thể chuyển.
- Replication sender và các tác vụ quản trị.

Do đó, tổng năng lực đọc của replica không thể mặc định được thay thế bằng primary.

### Queueing và độ trễ tăng phi tuyến

Khi utilization của tài nguyên tiến gần 100%, thời gian chờ có thể tăng nhanh. Một primary đang sử dụng 70% CPU có thể vẫn có vẻ còn dư, nhưng khi thêm tải đọc, cache miss, I/O và lock contention có thể làm utilization vượt vùng an toàn. Queue tăng, latency tăng và connection bị giữ lâu hơn. Điều đó khiến pool ứng dụng đầy, retry tăng và tải tiếp tục dồn vào primary.

Không chỉ tính CPU. Primary có thể bão hòa ở:
- IOPS hoặc storage throughput.
- Log flush latency.
- Buffer/cache và memory bandwidth.
- Connection/session limit.
- Lock/latch contention.
- Temp storage.
- Network egress.
- Replication sender.

### Retry storm và chuyển tải lặp

Nếu router đánh dấu replica unhealthy theo một lần kiểm tra hoặc một ngưỡng lag quá nhạy, nó có thể liên tục thêm/bớt replica. Request lỗi hoặc timeout có thể được retry trên primary, làm tăng số truy vấn thực tế. Một truy vấn đã chạy lâu trên replica có thể vẫn đang tiêu thụ tài nguyên trong lúc ứng dụng retry lại trên primary nếu cancellation không được truyền đúng.

Cần có:
- Hysteresis: ngưỡng loại và ngưỡng phục hồi khác nhau.
- Thời gian quan sát liên tục trước khi đổi trạng thái.
- Giới hạn retry và backoff có jitter.
- Cancellation hoặc deadline để tránh truy vấn trùng.
- Fallback có giới hạn và ưu tiên theo loại request.
- Circuit breaker để ngăn chuyển tải không kiểm soát.

## Nhất quán dữ liệu khi đọc replica

### Eventual consistency và stale read

Với asynchronous replication, primary có thể xác nhận commit trước khi replica nhận hoặc áp dụng log tương ứng. Một truy vấn đọc ngay sau commit trên replica có thể không thấy dữ liệu mới. Đây là stale read.

Ví dụ:
1. Người dùng tạo đơn hàng trên primary.
2. Primary commit và trả thành công.
3. Ứng dụng chuyển sang trang chi tiết nhưng đọc từ replica.
4. Replica chưa replay transaction.
5. Trang chi tiết không tìm thấy đơn hoặc hiển thị trạng thái cũ.

Nếu ứng dụng retry đọc trên primary, kết quả có thể đúng nhưng tạo thêm tải. Nếu mọi request sau ghi đều bị pin vào primary quá lâu, primary có thể mất lợi ích read scaling.

### Read-after-write consistency

Các cách xử lý phổ biến:
- Gửi các truy vấn cần thấy ngay dữ liệu vừa ghi đến primary.
- Gắn session/request vào primary trong một khoảng thời gian hoặc đến khi replica bắt kịp vị trí log của transaction.
- Trả về commit position/LSN/GTID rồi chỉ đọc replica khi replica đã replay đến vị trí đó, nếu engine và router hỗ trợ.
- Dùng synchronous replication cho các yêu cầu cần bảo đảm mạnh hơn, sau khi đánh giá latency và failure semantics.
- Thiết kế UI/API chấp nhận trạng thái pending hoặc eventual consistency khi nghiệp vụ cho phép.

Không giả định mọi replica đều có thể cung cấp read-after-write chỉ bằng cách đợi một khoảng cố định. Lag thay đổi theo tải; một sleep 100 ms không phải bảo đảm nhất quán.

### Monotonic reads và session consistency

Một người dùng có thể đọc từ replica A rồi request sau được gửi đến replica B có lag lớn hơn, khiến dữ liệu hiển thị lùi về trạng thái cũ. Đây là vấn đề monotonic reads.

Có thể duy trì session affinity đến cùng replica, nhưng affinity không bảo đảm replica luôn bắt kịp. Với thao tác quan trọng, cần route theo consistency requirement hoặc kiểm tra replication position. Nếu replica mất khả năng đáp ứng, fallback phải tuân theo cùng chính sách consistency.

### Phân loại truy vấn theo yêu cầu nhất quán

| Loại truy vấn | Nơi đọc phù hợp | Lưu ý |
|---|---|---|
| Đọc ngay sau ghi trong cùng luồng nghiệp vụ | Primary hoặc replica đã xác nhận replay đến commit position | Bảo đảm read-after-write |
| Số dư, tồn kho, quyền truy cập cần dữ liệu mới | Primary hoặc cơ chế consistency mạnh | Tránh quyết định nghiệp vụ trên dữ liệu cũ |
| Dashboard có thể trễ vài giây/phút | Replica | Công bố freshness hoặc watermark |
| Báo cáo lịch sử nặng | Replica phân tích hoặc warehouse | Giới hạn concurrency và thời gian chạy |
| Cache/reference data ít thay đổi | Cache hoặc replica | Có quy tắc invalidation/freshness |
| Truy vấn phục vụ audit hoặc đối soát | Theo yêu cầu consistency được định nghĩa | Không route chỉ dựa trên latency |

## Thiết kế chính sách routing và fallback

### Health không chỉ là ping

Một replica trả lời TCP hoặc health check đơn giản không đồng nghĩa nó đủ khả năng phục vụ truy vấn. Health nên xem:
- Kết nối và trạng thái replication.
- Transport/apply lag và xu hướng.
- CPU, I/O, memory và queue.
- Query latency và lỗi.
- Khả năng đáp ứng consistency requirement.
- Số connection đang dùng và tải đọc hiện tại.

Có thể chia trạng thái:
- **Healthy:** đáp ứng freshness và latency mục tiêu, còn capacity.
- **Degraded:** lag hoặc tải tăng nhưng vẫn phục vụ một số workload chấp nhận độ trễ.
- **Read-ineligible:** không đủ freshness hoặc tài nguyên cho nhóm truy vấn yêu cầu.
- **Recovering:** đang bắt kịp log hoặc làm nóng cache; chưa nhận toàn bộ traffic.
- **Unavailable:** không kết nối hoặc không thể phục vụ.

Không nên dùng một ngưỡng lag chung cho mọi query. Dashboard có thể chấp nhận 30 giây; trang xác nhận đơn hàng có thể cần đọc primary hoặc kiểm tra commit position.

### Ngưỡng loại và phục hồi có hysteresis

Nếu loại replica khi lag vượt 2 giây và đưa lại ngay khi lag xuống dưới 2 giây, trạng thái có thể dao động liên tục quanh ngưỡng. Dùng hai ngưỡng:
- Ngưỡng loại: lag vượt mức cao trong một khoảng thời gian hoặc queue tiếp tục tăng.
- Ngưỡng phục hồi: lag xuống thấp hơn mức an toàn trong một khoảng ổn định, đồng thời tài nguyên và query latency đạt yêu cầu.

Ví dụ minh họa:
- Loại khỏi nhóm query freshness nghiêm ngặt khi replay lag trên 5 giây liên tục 30 giây.
- Chỉ đưa lại khi lag dưới 1 giây liên tục 2 phút và replica còn headroom.

Các giá trị này không phải cấu hình chung. Cần xác định theo nghiệp vụ, tốc độ ghi, RPO/RTO, query SLO và khả năng của hạ tầng.

### Fallback có giới hạn

Khi replica bị loại, router không nên mặc định chuyển 100% traffic sang primary. Các lựa chọn:
- Chỉ chuyển nhóm truy vấn quan trọng cần dữ liệu mới.
- Giới hạn tỷ lệ fallback hoặc số request đồng thời.
- Dùng hàng đợi có giới hạn và trả lỗi có kiểm soát khi hết capacity.
- Từ chối hoặc trì hoãn báo cáo không quan trọng.
- Trả dữ liệu cache có timestamp/freshness rõ ràng nếu nghiệp vụ chấp nhận.
- Giảm tần suất refresh dashboard hoặc hạ độ chi tiết.
- Dùng replica khác chỉ khi nó có capacity và đáp ứng consistency.
- Áp dụng admission control theo endpoint hoặc workload class.

Fallback limit phải có cơ chế rõ ràng để không tạo queue vô hạn. Nếu primary gần bão hòa, trả lỗi có kiểm soát hoặc degraded response có thể bảo vệ transaction ghi quan trọng tốt hơn việc nhận mọi request rồi timeout hàng loạt.

### Circuit breaker và retry

Circuit breaker ngăn tiếp tục gửi request đến một endpoint đang thất bại hoặc quá tải trong một khoảng thời gian. Nhưng circuit breaker ở replica không tự giải quyết capacity của primary. Nếu mở circuit và mọi request chuyển sang primary, hệ thống có thể chuyển sự cố từ replica sang primary.

Cần:
- Giới hạn retry, chỉ retry lỗi tạm thời có thể phục hồi.
- Backoff có jitter.
- Không retry query không idempotent nếu có side effect.
- Hủy truy vấn ở node cũ trước hoặc khi chuyển sang node mới khi driver/protocol hỗ trợ.
- Dùng request deadline chung.
- Giới hạn concurrency fallback.
- Phân biệt lỗi connection, timeout, stale read và lỗi SQL.

Một query SELECT thường không thay đổi dữ liệu, nhưng có thể rất tốn tài nguyên. Retry SELECT không giới hạn vẫn có thể gây quá tải.

## Giảm tải primary trong lúc replica chậm

### Bảo vệ năng lực cho ghi

Khi primary bị dồn đọc, ưu tiên giữ năng lực cho transaction ghi và hoạt động phục hồi. Có thể:
- Giới hạn số truy vấn đọc fallback đồng thời.
- Ưu tiên truy vấn đọc phục vụ giao dịch quan trọng.
- Tạm dừng hoặc giảm concurrency của báo cáo, export và batch đọc nặng.
- Giảm số hàng/cột trả về.
- Giảm tần suất polling và refresh.
- Dùng cache có TTL hoặc stale-while-revalidate nếu nghiệp vụ cho phép.
- Áp dụng rate limit và admission control theo workload.
- Giữ connection pool hoặc workload group riêng cho ghi và đọc nếu kiến trúc hỗ trợ.

Không để truy vấn báo cáo dài chiếm hết connection hoặc memory grant của primary khi transaction ghi đang có SLO nghiêm ngặt.

### Giảm chi phí truy vấn fallback

Truy vấn chuyển về primary cần được đánh giá riêng vì primary đang có workload ghi. Kiểm tra:
- Execution plan và index.
- Logical reads và số hàng trả về.
- Sort/hash spill và temp I/O.
- Lock wait và transaction duration.
- Các truy vấn scan lớn hoặc N+1.
- Parameter distribution và plan regression.

Có thể giới hạn báo cáo theo khoảng thời gian, phân trang, dùng summary table hoặc cache. Nhưng thay đổi phải giữ đúng kết quả và freshness mà nghiệp vụ yêu cầu.

### Dùng cache và degraded response

Cache có thể giảm tải khi replica không đủ mới hoặc primary gần quá tải. Một số lựa chọn:
- Cache kết quả dashboard trong một khoảng TTL ngắn.
- Trả timestamp cập nhật gần nhất.
- Dùng stale-while-revalidate để tiếp tục trả dữ liệu cũ trong giới hạn cho phép.
- Tạm ẩn widget báo cáo không thiết yếu.
- Giảm tần suất truy vấn polling.
- Gộp nhiều request đọc giống nhau bằng request coalescing.

Không cache dữ liệu nhạy cảm hoặc dữ liệu có yêu cầu nhất quán mạnh mà chưa thiết kế key, invalidation, authorization và freshness rõ ràng. Không trả dữ liệu cũ cho quyết định tồn kho, thanh toán hoặc phân quyền nếu nghiệp vụ không cho phép.

### Kiểm soát nguồn gốc tải

Cần gắn workload class hoặc application name để biết request nào đang chạy trên primary do fallback. Theo dõi riêng:
- Read bình thường trên primary.
- Read fallback từ replica.
- Write transaction.
- Admin/maintenance.
- Batch/reporting.
- Retry và request bị chuyển nhiều lần.

Nếu tất cả request xuất hiện dưới cùng một application name, khó xác định phần tải tăng đến từ đâu. Trace ID và route reason giúp nối request với quyết định routing.

## Phục hồi replica và đưa trở lại nhóm đọc

### Đừng đưa replica trở lại ngay khi lag giảm

Replica có thể bắt kịp log nhưng vẫn chưa đủ khả năng nhận traffic:
- Cache còn lạnh.
- Query plan hoặc thống kê cần cập nhật.
- I/O queue vẫn cao.
- Applier vừa hoàn tất backlog và có thể chưa ổn định.
- Connection pool chưa warm.
- Replica có thể tiếp tục lag khi tải đọc quay lại.

Trạng thái recovering nên được giữ đến khi replica ổn định theo nhiều chỉ số, không chỉ một số đo lag.

### Quy trình phục hồi từ từ

1. Xác nhận nguyên nhân lag đã được xử lý: mạng, I/O, CPU, query đọc hoặc burst ghi.
2. Kiểm tra replica đã nhận và áp dụng log đến vị trí cần thiết.
3. Kiểm tra queue không tăng trở lại trong cửa sổ quan sát.
4. Kiểm tra query latency, CPU, I/O và connection capacity.
5. Warm connection pool và các cache cần thiết có kiểm soát.
6. Cho một tỷ lệ nhỏ truy vấn ít nhạy freshness quay lại replica.
7. Theo dõi lag và latency sau mỗi bước tăng traffic.
8. Tăng tỷ lệ theo từng nấc nếu replica còn headroom.
9. Dừng tăng hoặc đưa replica về recovering nếu queue/lag tăng vượt ngưỡng.
10. Chỉ phục hồi đầy đủ sau khi đạt điều kiện ổn định.

Failback là thay đổi routing, không nhất thiết là database failover. Không nhầm việc đưa replica trở lại nhóm đọc với chuyển primary role. Nếu primary role đã thay đổi do failover, cần một quy trình topology và consistency riêng.

## Ví dụ chẩn đoán: replica lag kéo tải về primary

Một hệ thống thương mại điện tử có một primary và hai read replica. Bình thường, primary xử lý toàn bộ ghi và khoảng 25% truy vấn đọc; hai replica chia phần còn lại. Đầu giờ sáng, một báo cáo quét lịch sử bắt đầu chạy trên replica A.

Số liệu quan sát:
- Replica A: CPU 90%, I/O latency tăng, apply queue tăng liên tục.
- Replica B: lag thấp, CPU 55%, còn capacity nhưng không đủ nhận toàn bộ traffic A.
- Router: loại replica A khỏi nhóm đọc sau khi lag vượt ngưỡng.
- Primary: read traffic tăng gần gấp đôi, CPU từ 65% lên 92%, connection active gần giới hạn.
- Write latency p95 tăng, lock wait và timeout bắt đầu xuất hiện.
- Ứng dụng retry một số request đọc timeout, làm read traffic tăng thêm.

Nếu chỉ xử lý replica A bằng cách tăng applier worker, có thể không giải quyết được vì báo cáo đang chiếm I/O và CPU. Nếu router chuyển toàn bộ traffic A sang primary, transaction ghi bị ảnh hưởng.

Cách xử lý có kiểm soát:
1. Giảm hoặc tạm dừng báo cáo nặng trên replica A; xác định query fingerprint và phạm vi scan.
2. Giữ replica A ở trạng thái recovering/read-ineligible cho truy vấn cần freshness.
3. Chuyển một phần workload đọc ít quan trọng sang replica B trong giới hạn capacity.
4. Giới hạn concurrency và rate của fallback về primary.
5. Ưu tiên transaction ghi và truy vấn đọc quan trọng; trì hoãn export/dashboard nếu cần.
6. Giảm retry, áp dụng backoff và hủy request đã hết deadline.
7. Theo dõi apply queue của A, primary CPU/I/O, write p95, fallback count và error rate.
8. Khi A bắt kịp và ổn định, đưa lại một phần traffic dashboard rồi tăng dần.

Kết quả cần đánh giá không chỉ là lag của A giảm. Cần xác nhận primary write latency trở về SLO, queue không tăng, replica B không bị quá tải và tổng lỗi người dùng giảm.

## Quy trình ứng phó sự cố

### Phát hiện và xác định phạm vi

- Xác định replica nào lag và lag ở transport hay apply.
- Xem lag theo vị trí log và tốc độ thay đổi, không chỉ một trường seconds-behind.
- Xác định thời điểm bắt đầu, workload mới, deploy, batch, DDL hoặc thay đổi hạ tầng.
- Kiểm tra traffic routing và số request đã fallback.
- Đo primary CPU, I/O, log flush, active sessions, write latency và connection usage.

### Khoanh vùng nguyên nhân

- Nếu send/receive queue tăng: kiểm tra network, sender, receiver và log transport.
- Nếu replay/redo queue tăng: kiểm tra CPU/I/O replica, applier throughput, query read contention và transaction lớn.
- Nếu replica lag chỉ tăng khi báo cáo chạy: giới hạn hoặc chuyển báo cáo sang hệ thống phù hợp.
- Nếu primary quá tải sau fallback: kiểm tra fallback rate, retry, query cost và năng lực dự phòng.
- Nếu lag thấp nhưng người dùng vẫn thấy dữ liệu cũ: kiểm tra routing consistency, session affinity và mốc commit/replay.

### Giảm tác động

1. Bảo vệ primary bằng fallback limit và admission control.
2. Ưu tiên write và read path quan trọng.
3. Giảm hoặc dừng workload phân tích không thiết yếu.
4. Giảm retry và request trùng.
5. Dùng cache/degraded response nếu freshness cho phép.
6. Chỉ chuyển traffic sang replica khác khi replica đó còn capacity và đáp ứng consistency.
7. Không đổi replication mode hoặc tắt durability trong lúc sự cố nếu chưa có đánh giá RPO và phê duyệt phù hợp.

### Phục hồi và xác minh

- Xử lý nguyên nhân gốc.
- Xác nhận log đã được nhận và áp dụng.
- Quan sát queue và lag ổn định trong một cửa sổ đủ dài.
- Thử tải nhỏ trên replica trước khi mở routing đầy đủ.
- Tăng traffic theo nấc.
- Kiểm tra primary write latency, replica read latency, lag, fallback và retry.
- Ghi lại timeline, ngưỡng kích hoạt và quyết định để cải thiện runbook.

## Những sai lầm thường gặp

- **Chỉ kiểm tra replica có kết nối được hay không:** replica có thể up nhưng lag lớn hoặc không đủ capacity.
- **Dùng một chỉ số lag duy nhất:** không phân biệt log chưa truyền và log chưa áp dụng.
- **Chuyển toàn bộ read traffic về primary:** có thể làm primary mất khả năng phục vụ ghi.
- **Coi primary là dự phòng đọc miễn phí:** primary đã có workload ghi và cần headroom.
- **Đưa replica trở lại ngay khi lag chạm ngưỡng:** cache lạnh và backlog mới có thể làm lag tăng lại.
- **Đặt ngưỡng loại/phục hồi giống nhau:** router dao động liên tục quanh ngưỡng.
- **Retry mọi truy vấn timeout:** tạo retry storm và truy vấn trùng.
- **Không phân loại consistency:** stale read có thể gây lỗi nghiệp vụ dù latency thấp.
- **Dùng sleep cố định để chờ replica bắt kịp:** lag thay đổi theo tải, không có bảo đảm.
- **Tăng applier worker không đo:** có thể làm contention tăng mà throughput không cải thiện.
- **Để báo cáo nặng chạy chung replica OLTP:** query scan có thể cạnh tranh với apply.
- **Không gắn nhãn fallback traffic:** khó biết vì sao primary tải tăng.
- **Nhầm failback read routing với database failover:** hai thao tác có rủi ro và điều kiện khác nhau.
- **Chỉ xác nhận replica khỏe mà bỏ qua primary:** sự cố chỉ được coi là phục hồi khi toàn bộ workload trở lại giới hạn an toàn.

## Checklist kiểm soát replica lag và fallback

- [ ] Phân biệt send/transport lag với receive/flush/apply lag.
- [ ] Theo dõi log position gap, queue size, apply throughput và xu hướng lag.
- [ ] Đo CPU, I/O, memory, active queries và lock waits trên từng replica.
- [ ] Theo dõi primary CPU, I/O, log generation, write latency và session count.
- [ ] Đo read traffic, fallback rate, retry và query latency theo từng node.
- [ ] Phân loại query theo yêu cầu freshness và read-after-write.
- [ ] Có routing health state rõ ràng: healthy, degraded, read-ineligible, recovering.
- [ ] Dùng hysteresis và thời gian quan sát để tránh trạng thái dao động.
- [ ] Giới hạn fallback concurrency/rate và có admission control.
- [ ] Bảo vệ workload ghi quan trọng trên primary.
- [ ] Có retry limit, backoff, jitter, deadline và cancellation.
- [ ] Dùng cache/degraded response chỉ khi nghiệp vụ chấp nhận stale data.
- [ ] Có quy trình đưa replica trở lại theo từng nấc.
- [ ] Xác minh lag, primary write SLO và replica capacity sau phục hồi.
- [ ] Ghi lại nguyên nhân, timeline, tác động và điều chỉnh runbook.

## Kết luận

Replica đọc chậm có thể làm router chuyển tải về primary, khiến máy chính phải xử lý thêm truy vấn đọc trong khi vẫn duy trì toàn bộ workload ghi. Nếu fallback không có giới hạn, retry không được kiểm soát và replica bị loại quá nhạy, sự cố có thể lan rộng thành primary overload, write latency tăng và cả cụm mất ổn định.

Hãy đo riêng log transport và apply, đối chiếu lag với tải đọc, CPU, I/O và queue trên từng node. Phân loại truy vấn theo yêu cầu nhất quán, thiết kế fallback có giới hạn và bảo vệ năng lực cho transaction ghi. Khi replica phục hồi, đưa nó trở lại nhóm đọc theo từng nấc sau khi xác nhận log đã áp dụng và tài nguyên ổn định. Thành công phải được đánh giá trên toàn hệ thống: dữ liệu đủ mới, truy vấn đọc đáp ứng mục tiêu, primary giữ được SLO ghi và không còn vòng chuyển tải gây quá tải.