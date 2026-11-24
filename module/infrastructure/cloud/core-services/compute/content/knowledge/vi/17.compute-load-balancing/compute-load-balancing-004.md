# Thuật toán phân phối tải và giới hạn kết nối

Load balancer tiếp nhận lưu lượng từ client rồi phân phối tới các backend như máy ảo, container hoặc service compute. Cách chọn backend ảnh hưởng trực tiếp đến độ trễ, mức sử dụng tài nguyên, khả năng chịu lỗi và hiệu quả mở rộng. Nếu thuật toán không phù hợp, một máy có thể quá tải trong khi các máy khác còn rảnh; nếu giới hạn kết nối không được sizing, load balancer hoặc backend có thể từ chối request dù tổng năng lực CPU vẫn còn.

Thiết kế cân bằng tải cần trả lời hai câu hỏi: **request nào sẽ được gửi tới backend nào** và **mỗi lớp được phép giữ bao nhiêu kết nối hoặc công việc đồng thời**. Câu trả lời phụ thuộc giao thức, thời gian xử lý, trạng thái phiên, đặc tính kết nối dài/ngắn và giới hạn của nền tảng cloud.

## 1. Load balancing ở lớp L4 và L7

Load balancer có thể phân phối lưu lượng ở nhiều lớp mạng:

- **Layer 4 (L4):** quyết định dựa trên thông tin vận chuyển như IP nguồn/đích, port và protocol TCP/UDP. L4 thường chuyển tiếp kết nối hoặc luồng packet mà không cần hiểu nội dung HTTP.
- **Layer 7 (L7):** hiểu giao thức ứng dụng như HTTP/HTTPS, có thể định tuyến theo host, path, header, cookie hoặc thuộc tính request.

| Đặc điểm | L4 | L7 |
|---|---|---|
| Thông tin định tuyến | IP, port, protocol và flow | Host, path, header, cookie, method hoặc nội dung giao thức được hỗ trợ |
| Đơn vị phân phối thường gặp | Kết nối/flow | Request hoặc stream ở tầng ứng dụng |
| Chi phí xử lý | Thường thấp hơn do ít phân tích nội dung | Có thêm chi phí parse, TLS termination, policy và routing |
| Tính năng | TCP/UDP forwarding, NAT, flow affinity | TLS offload, host/path routing, cookie affinity, header rewrite |
| Trường hợp phù hợp | Database proxy, TCP service, game/streaming, lưu lượng không phải HTTP | Web/API, microservices HTTP, định tuyến theo hostname hoặc URL |

Một điểm quan trọng: L4 thường chọn backend khi tạo flow/kết nối. Nếu một TCP connection tồn tại lâu, nhiều dữ liệu trên connection đó tiếp tục đi tới cùng backend. L7 có thể chọn backend cho từng HTTP request, nhưng hành vi còn phụ thuộc protocol và cấu hình proxy. Với HTTP/2 hoặc HTTP/3, nhiều request/stream có thể được multiplex trên một kết nối; không nên mặc định một connection tương ứng với một request.

## 2. Round Robin

**Round Robin (RR)** phân phối lần lượt từng kết nối hoặc request tới các backend theo thứ tự vòng tròn. Với ba backend A, B và C, chuỗi lựa chọn có thể là A → B → C → A → B → C.

Ưu điểm:

- Đơn giản, dễ hiểu và dễ dự đoán.
- Phân phối khá đều khi backend tương đương và request có chi phí xử lý gần nhau.
- Không cần duy trì bộ đếm kết nối phức tạp ngoài trạng thái vòng quay.

Hạn chế:

- Không xét backend hiện đang bận bao nhiêu.
- Request có thời gian xử lý rất khác nhau có thể làm một backend tích lũy nhiều công việc nặng.
- Nếu các backend có cấu hình khác nhau, chia đều số request có thể không chia đều tải.

RR phù hợp khi các máy có năng lực tương đương, request tương đối đồng nhất và thời gian xử lý ngắn. Với workload xử lý báo cáo, upload lớn hoặc truy vấn có chi phí khác nhau, cần cân nhắc thuật toán khác.

## 3. Weighted Round Robin

**Weighted Round Robin (WRR)** gán trọng số cho mỗi backend để máy có năng lực lớn hơn nhận tỷ lệ request cao hơn. Nếu A có weight 5, B có weight 3 và C có weight 2, tỷ lệ phân phối mục tiêu xấp xỉ 50%, 30% và 20% trong một chu kỳ đủ lớn.

Tỷ lệ mục tiêu của backend `i` có thể ước lượng:

\[
P_i = \frac{w_i}{\sum_{j=1}^{n} w_j}
\]

Trong đó `w_i` là trọng số của backend `i` và mẫu số là tổng trọng số của các backend đang đủ điều kiện nhận tải.

Ví dụ, một nhóm máy có hai instance 8 vCPU và một instance 4 vCPU. Có thể bắt đầu thử nghiệm với weight 2:2:1 nếu benchmark cho thấy năng lực xử lý tương ứng gần tỷ lệ đó. Không nên suy ra weight chỉ từ số vCPU: hiệu năng còn phụ thuộc thế hệ CPU, RAM, cache, I/O, giới hạn mạng và đặc tính ứng dụng.

WRR hữu ích khi backend khác cấu hình hoặc cần rollout canary. Có thể đặt weight thấp cho phiên bản mới, quan sát lỗi và latency rồi tăng dần. Khi dùng weight để canary, vẫn cần health check, giới hạn tải và tiêu chí rollback rõ ràng.

## 4. Least Connections và Weighted Least Connections

**Least Connections** chọn backend đang có ít kết nối hoạt động nhất. Ý tưởng là backend ít kết nối thường có khả năng nhận thêm việc. Thuật toán phù hợp hơn RR khi thời gian tồn tại của kết nối khác nhau đáng kể.

Ví dụ, A đang có 80 kết nối, B có 25 và C có 40. Một kết nối mới có thể được gửi tới B. Tuy nhiên, số kết nối không luôn phản ánh chính xác công việc: một connection nhàn rỗi có thể nhẹ hơn một connection đang chạy truy vấn nặng.

**Weighted Least Connections** kết hợp số kết nối với trọng số năng lực. Một cách diễn giải phổ biến là so sánh tỷ lệ kết nối hiện tại trên weight; backend có tỷ lệ thấp hơn được ưu tiên. Cách tính chính xác thay đổi theo sản phẩm, vì vậy cần xem tài liệu của load balancer.

Least Connections phù hợp với TCP connection có thời gian sống khác nhau hoặc backend xử lý request lâu. Nó có thể không hiệu quả nếu:

- HTTP/2 multiplex nhiều request trên một connection.
- Backend giữ nhiều keep-alive connection nhàn rỗi.
- Một số connection rất nặng nhưng được đếm ngang với connection nhẹ.
- Trạng thái kết nối phân tán giữa nhiều node load balancer không được đồng bộ.

Với HTTP/2, L7 proxy có thể cần thuật toán dựa trên active requests/streams hoặc load metric ở tầng ứng dụng thay vì chỉ đếm TCP connection.

## 5. Least Response Time và thuật toán thích ứng

**Least Response Time** ưu tiên backend có thời gian phản hồi quan sát được thấp, thường kết hợp số kết nối hoặc trọng số. Ý tưởng là gửi thêm tải tới máy đang phục vụ nhanh hơn.

Thuật toán thích ứng có thể dùng nhiều tín hiệu:

- Thời gian phản hồi trung bình hoặc EWMA (Exponentially Weighted Moving Average).
- Số request đang hoạt động hoặc queue depth.
- CPU/memory pressure hoặc metric ứng dụng.
- Error rate, timeout và trạng thái health.
- Trọng số cấu hình của backend.

Một mô hình khái niệm có thể đánh giá điểm backend:

\[
Score_i = \alpha \cdot Latency_i + \beta \cdot ActiveWork_i + \gamma \cdot ErrorPenalty_i
\]

Backend có điểm thấp hơn được ưu tiên, sau khi áp dụng trọng số và điều kiện health. Đây chỉ là mô hình giải thích; sản phẩm thực tế có thể dùng công thức và tín hiệu khác.

Thuật toán thích ứng có thể phản ứng tốt với tải biến động, nhưng dễ dao động nếu metric nhiễu hoặc cập nhật quá nhanh. Nếu tất cả request đột ngột chuyển sang máy đang nhanh nhất, máy đó có thể trở nên quá tải rồi bị loại khỏi ưu tiên; hệ thống có thể dao động qua lại. Dùng smoothing, giới hạn thay đổi weight và kiểm thử khi backend chậm dần để tránh hiện tượng này.

## 6. Random và Power of Two Choices

**Random** chọn ngẫu nhiên một backend đủ điều kiện. Với số lượng request lớn và backend tương đương, phân phối thường tiến gần đều theo thời gian. Random đơn giản và tránh một số chi phí duy trì thứ tự.

**Power of Two Choices** chọn ngẫu nhiên hai backend rồi gửi tới backend có ít kết nối hoặc ít công việc hơn. Cách này có thể cải thiện độ cân bằng đáng kể so với chọn ngẫu nhiên đơn thuần mà không cần thu thập trạng thái của mọi backend cho mỗi quyết định.

Thuật toán này hữu ích trong hệ thống nhiều backend và tải lớn. Chất lượng kết quả phụ thuộc độ mới của số liệu load, cách định nghĩa active work và việc backend có được chọn đồng đều trong nhóm ứng viên hay không.

## 7. Hash theo client, URL hoặc khóa nghiệp vụ

Một số workload cần cùng client hoặc cùng khóa dữ liệu thường xuyên tới cùng backend. Các thuật toán hash có thể cung cấp tính ổn định:

- **Source IP hash:** hash địa chỉ IP nguồn để chọn backend. Nhiều người dùng sau NAT có thể cùng một IP, khiến phân phối mất cân bằng.
- **Consistent hashing:** ánh xạ key lên vòng hash để giảm số key phải chuyển backend khi thêm/bớt node.
- **URI/path hash:** dùng URI hoặc path để giữ các request liên quan trên cùng backend nếu sản phẩm hỗ trợ.
- **Header/cookie affinity:** dùng thuộc tính request hoặc cookie để duy trì session affinity.

Hash phù hợp khi có cache cục bộ, dữ liệu partitioned hoặc ứng dụng cũ lưu session trong bộ nhớ instance. Tuy nhiên, affinity có thể làm giảm khả năng cân bằng khi một client tạo tải lớn hoặc một key trở nên phổ biến. Khi backend bị lỗi hoặc topology thay đổi, key có thể được ánh xạ sang node khác; ứng dụng cần xử lý cache miss và session recovery.

Không dùng source IP hash như cơ chế nhận diện người dùng chính xác. Một IP có thể đại diện cho hàng nghìn client sau NAT, proxy hoặc mạng di động; địa chỉ IP cũng có thể thay đổi trong phiên.

## 8. Session affinity và trạng thái ứng dụng

Session affinity (sticky session) cố gắng gửi các request của cùng client tới cùng backend trong một khoảng thời gian. Nó hữu ích khi ứng dụng giữ session trong RAM cục bộ hoặc dùng cache không chia sẻ.

Nhược điểm của sticky session:

- Tải có thể lệch nếu một số client hoạt động nhiều hơn phần còn lại.
- Backend hỏng có thể làm mất session nếu trạng thái chỉ nằm trong RAM của node.
- Scale in hoặc thay đổi topology có thể khiến affinity bị phá vỡ.
- Cookie affinity cần cấu hình domain, secure, expiry và bảo vệ dữ liệu đúng cách.

Thiết kế bền vững hơn thường lưu session trong kho dùng chung hoặc dùng token stateless đã được bảo vệ. Khi đó, load balancer có thể phân phối linh hoạt hơn và backend dễ thay thế. Nếu sticky session là bắt buộc, hãy đặt TTL phù hợp, kiểm thử backend failure và theo dõi phân phối tải theo từng node.

## 9. Hiểu giới hạn kết nối ở từng lớp

Một request có thể đi qua nhiều thành phần, mỗi thành phần có giới hạn riêng. Không có một con số “max connections” duy nhất cho toàn hệ thống.

| Lớp | Giới hạn thường gặp | Hệ quả khi chạm giới hạn |
|---|---|---|
| Client | Socket, connection pool, ephemeral port | Không tạo được kết nối mới hoặc timeout |
| Edge/load balancer | Concurrent connection, new connection rate, stream/request rate | Từ chối, reset, queue hoặc throttle theo sản phẩm |
| Proxy/gateway | Client connection, backend connection, worker/thread, buffer | Queue tăng, 502/503/504 hoặc connection reset |
| Backend instance | FD, listen backlog, thread pool, worker, connection pool | Accept thất bại, request chờ hoặc lỗi ứng dụng |
| Database/cache | Max client, connection pool, query concurrency | Connection refused, pool exhausted hoặc query queue |
| NAT/firewall | Session table, port mapping, throughput, PPS | Kết nối mới thất bại hoặc timeout |

Giới hạn được tính theo cách khác nhau giữa nhà cung cấp. Một số dịch vụ giới hạn kết nối đồng thời theo listener hoặc load balancer; một số tính theo target, zone, loại instance hoặc số request/stream. Hãy phân biệt **connection rate** (kết nối mới mỗi giây), **concurrent connections** (kết nối đang tồn tại), **request rate** (request mỗi giây) và **active requests** (request đang xử lý).

## 10. Sizing giới hạn kết nối cho backend

Giới hạn backend cần dựa trên năng lực xử lý và số kết nối thực sự được giữ. Với mỗi backend, có thể ước lượng số kết nối đồng thời bằng định luật Little:

\[
L = \lambda \times W
\]

Trong đó `L` là số request trung bình đang ở trong hệ thống, `λ` là tốc độ request đến (request/giây) và `W` là thời gian phản hồi trung bình (giây). Công thức cho số request đồng thời trung bình; nó không tự động bằng số TCP connection nếu keep-alive hoặc HTTP/2 multiplex được sử dụng.

Ví dụ, một backend nhận 400 request/giây và thời gian xử lý trung bình là 50 ms:

\[
L = 400 \times 0,05 = 20\text{ request đồng thời}
\]

Nếu p95 latency hoặc thời gian xử lý tăng, concurrency cần thiết có thể cao hơn. Phải đo ở tải đỉnh và xem phân phối latency thay vì chỉ dùng trung bình.

Một cách sizing ban đầu cho connection limit:

1. Đo mức kết nối và request đồng thời ở tải bình thường.
2. Xác định peak RPS, burst, latency p95/p99 và thời gian sống của kết nối.
3. Xác định năng lực backend trước khi queue hoặc error rate tăng mạnh.
4. Dành headroom cho health check, quản trị, rollout và failover.
5. Đặt giới hạn để một backend không nhận quá nhiều kết nối khi các node khác bị lỗi.
6. Kiểm thử giới hạn khi scale in, mất một AZ hoặc một backend bị chậm.

Không đặt max connection quá cao chỉ để tránh lỗi. Nếu backend nhận nhiều request hơn khả năng xử lý, queue và latency có thể tăng vô hạn trước khi tài nguyên cạn. Một giới hạn hữu ích phải bảo vệ backend khỏi overload và tạo tín hiệu rõ ràng để client retry hoặc giảm tải.

## 11. Giới hạn connection pool và số kết nối tới dependency

Ứng dụng thường giữ pool kết nối tới database, cache hoặc HTTP service. Pool quá nhỏ khiến request chờ dù dependency còn capacity; pool quá lớn có thể làm database hoặc dịch vụ đích bị quá tải.

Ví dụ, nếu có 10 backend instance và mỗi instance cấu hình pool database tối đa 50 kết nối, tổng khả năng tạo kết nối có thể lên tới 500, chưa tính worker, migration, monitoring và các ứng dụng khác. Database phải có capacity cho tổng số client thực tế.

Khi sizing pool, xem xét:

- Số instance tối đa khi autoscaling và khi failover.
- Số connection cần thiết để đạt throughput mục tiêu.
- Thời gian query và tỷ lệ request thực sự cần DB.
- Giới hạn connection của database và các client khác.
- Timeout lấy connection, idle timeout và thời gian giữ connection.
- Khả năng dùng proxy/pooler trung gian để multiplex kết nối.

Pool connection cần có timeout hữu hạn, giới hạn tối đa và metric về active/idle/pending. Nếu pool exhausted, tăng pool không phải lúc nào cũng đúng; query chậm hoặc connection leak có thể là nguyên nhân. Theo dõi cả thời gian chờ pool và thời gian thực thi query.

## 12. Queue, timeout và hành vi khi quá tải

Khi tất cả backend đã đạt giới hạn, load balancer hoặc proxy có thể queue request, từ chối kết nối hoặc trả lỗi. Queue có thể hấp thụ burst ngắn nhưng không giải quyết được tình trạng tải đến lâu dài cao hơn năng lực xử lý.

Một queue cần có:

- Giới hạn chiều dài hoặc dung lượng.
- Timeout tối đa mà request được phép chờ.
- Chính sách ưu tiên hoặc loại bỏ công việc nếu phù hợp.
- Metric về queue depth, queue wait time và số request bị loại.
- Backpressure để client hoặc upstream giảm tốc độ gửi.

Nếu queue không giới hạn, request cũ có thể chờ lâu đến khi client đã timeout, tạo ra công việc vô ích và làm hệ thống phục hồi chậm. Đôi khi từ chối sớm bằng `429 Too Many Requests` hoặc `503 Service Unavailable` tốt hơn giữ request quá lâu. Với API có thể retry, cần trả `Retry-After` khi phù hợp và thiết kế retry có exponential backoff cùng jitter.

Timeout cần được phối hợp giữa client, load balancer, proxy và backend. Timeout của tầng ngoài nên đủ dài cho các bước bên trong nhưng không dài đến mức giữ tài nguyên vô ích. Tránh cấu hình retry ở mọi tầng mà không giới hạn; nhiều lớp retry có thể khuếch đại tải khi backend đang lỗi.

## 13. Connection draining và slow start

Khi backend cần bảo trì, scale in hoặc thay phiên bản, load balancer nên ngừng gửi công việc mới tới node đó nhưng cho phép kết nối đang hoạt động hoàn tất trong khoảng thời gian quy định. Cơ chế này thường được gọi là **connection draining** hoặc deregistration delay.

Quy trình cơ bản:

1. Đánh dấu backend không nhận kết nối/request mới.
2. Ngừng chọn backend trong thuật toán phân phối.
3. Chờ request đang chạy và connection cần thiết hoàn tất trong giới hạn drain.
4. Đóng các kết nối còn lại khi hết deadline theo chính sách.
5. Thực hiện restart, thay máy hoặc cập nhật ứng dụng.

Thời gian drain phải phù hợp với thời gian xử lý tối đa và giao thức. WebSocket, TCP stream, gRPC stream hoặc download dài có thể tồn tại lâu; cần chính sách riêng để không chờ vô hạn. Ứng dụng cũng nên hỗ trợ graceful shutdown và ngừng nhận việc mới trước khi tiến trình kết thúc.

**Slow start** tăng dần lượng tải gửi tới backend mới sau khi nó healthy. Điều này giúp cache nóng lên, connection pool được tạo và ứng dụng không bị dồn tải đột ngột. Slow start đặc biệt hữu ích sau khi scale out hoặc deploy phiên bản mới. Thời gian và cách tăng tải phụ thuộc sản phẩm; cần đo thời gian warm-up thực tế.

## 14. Health check và loại backend khỏi vòng phân phối

Load balancer thường kiểm tra backend bằng health check định kỳ. Nếu backend không đạt điều kiện, nó có thể bị loại khỏi nhóm nhận tải. Health check có thể ở lớp TCP hoặc HTTP:

- TCP check xác nhận cổng có thể thiết lập kết nối.
- HTTP check gọi endpoint để xác nhận ứng dụng trả trạng thái mong muốn.
- Một số hệ thống hỗ trợ kiểm tra nội dung response hoặc kiểm tra nhiều điều kiện.

Health check nên kiểm tra readiness cần thiết cho việc phục vụ request, không chỉ kiểm tra tiến trình còn sống. Nếu endpoint phụ thuộc quá nhiều dịch vụ không bắt buộc, một dependency phụ lỗi có thể làm toàn bộ backend bị loại dù chức năng chính vẫn phục vụ được.

Các tham số cần thiết kế:

- Interval giữa các lần kiểm tra.
- Timeout cho một lần health check.
- Số lần thất bại liên tiếp trước khi đánh dấu unhealthy.
- Số lần thành công để đưa backend trở lại healthy.
- Cổng, path, protocol và nguồn mạng của health checker.
- Tác động của health check lên ứng dụng và database.

Health check quá nhanh hoặc quá nhạy có thể gây flapping: backend liên tục bị thêm vào rồi loại ra. Health check quá chậm khiến backend lỗi vẫn tiếp tục nhận tải. Theo dõi số lần chuyển trạng thái và chọn ngưỡng theo thời gian phục hồi thực tế.

## 15. Giới hạn kết nối và giới hạn tài nguyên của máy ảo

Một backend VM phải có đủ tài nguyên để phục vụ số kết nối được load balancer gửi tới. Các giới hạn liên quan gồm:

- File descriptor (`RLIMIT_NOFILE`) cho socket và file đang mở.
- TCP listen backlog và hàng đợi accept.
- Ephemeral port khi tạo nhiều kết nối outbound.
- Số thread, worker, event loop và giới hạn process.
- CPU, RAM, kernel memory và network PPS/throughput của loại instance.
- Connection pool tới database/cache và giới hạn của dịch vụ đích.

Nếu load balancer cho phép 100.000 kết nối đồng thời nhưng mỗi VM chỉ chịu được 5.000 kết nối theo cấu hình và tải thực tế, cần chia capacity theo số backend khỏe mạnh và tình huống mất node. Không chỉ nhìn giới hạn lý thuyết của load balancer.

Với Linux, theo dõi FD count, `ss -s`, listen queue, CPU, memory, socket state và network metric. Nếu backend có nhiều kết nối nhưng request rate thấp, có thể keep-alive hoặc connection dài đang giữ socket. Nếu request rate cao và FD tăng liên tục, kiểm tra connection leak hoặc pool không đóng đúng cách.

## 16. Ví dụ cấu hình NGINX upstream

NGINX có thể phân phối request tới upstream theo round robin mặc định hoặc `least_conn`. Ví dụ:

```nginx
upstream orders_api {
    least_conn;
    server 10.20.16.11:8080 max_conns=300;
    server 10.20.16.12:8080 max_conns=300;
    server 10.20.16.13:8080 max_conns=150;
    keepalive 64;
}

server {
    listen 443 ssl;
    server_name orders.example.internal;

    location / {
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_pass http://orders_api;
        proxy_connect_timeout 3s;
        proxy_read_timeout 30s;
    }
}
```

Đây là ví dụ minh họa cho NGINX OSS; cần kiểm tra phiên bản và ngữ cảnh cấu hình thực tế. `least_conn` chọn upstream có ít kết nối đang hoạt động hơn. `max_conns` giới hạn số kết nối hoạt động tới một upstream server; nếu không dùng shared memory zone, giới hạn có thể được áp dụng riêng theo worker process. Các kết nối idle trong keepalive cache không được tính giống kết nối active và tổng socket có thể lớn hơn giá trị `max_conns`. Vì vậy, cần kiểm tra tài liệu NGINX và đo thực tế khi dùng nhiều worker.

`keepalive 64` đặt số kết nối idle được cache cho mỗi worker trong upstream group theo semantics của NGINX; nó không phải tổng số kết nối backend tối đa. `proxy_read_timeout` là timeout giữa hai lần đọc liên tiếp từ upstream, không nhất thiết là giới hạn tổng thời gian xử lý request. Hãy phân biệt connect timeout, send timeout, read timeout và timeout tổng của client.

## 17. Ví dụ chọn thuật toán cho từng loại workload

| Workload | Thuật toán/cơ chế có thể phù hợp | Lý do và điểm cần kiểm tra |
|---|---|---|
| API stateless, request tương đối đồng đều | Round Robin hoặc Weighted Round Robin | Đơn giản; weight nếu backend khác năng lực |
| API có request thời gian xử lý rất khác nhau | Least Connections hoặc thuật toán dựa trên active request | Giảm dồn việc vào node đang bận; cần hiểu HTTP/2 và keep-alive |
| TCP stream dài | Least Connections hoặc hash tùy tính chất phiên | Số connection có thể phản ánh mức sử dụng tốt hơn RR; stream lâu cần drain |
| Backend có cache cục bộ theo key | Consistent hashing | Giữ key gần node cũ khi topology thay đổi; xử lý cache miss khi node lỗi |
| Ứng dụng phụ thuộc session trong RAM | Sticky session tạm thời | Dễ tương thích ứng dụng cũ nhưng giảm khả năng cân bằng và phục hồi |
| Backend khác cấu hình | Weighted Round Robin/Weighted Least Connections | Tỷ lệ tải phản ánh capacity đo được |
| Fleet lớn, cần thuật toán nhẹ | Random hoặc Power of Two Choices | Ít chi phí trạng thái; cần kiểm tra độ cân bằng |
| Rollout canary | Weighted routing | Tăng dần traffic tới phiên bản mới theo tiêu chí an toàn |

Không có thuật toán tốt nhất trong mọi tình huống. Hãy benchmark bằng traffic profile gần với thực tế, gồm tỷ lệ request, thời gian xử lý, keep-alive, HTTP/2, payload và hành vi retry.

## 18. Tình huống minh họa: backend chạm giới hạn kết nối

Một API có ba VM backend. Load balancer dùng round robin. Trong giờ cao điểm, VM thứ nhất thường xuyên trả 503 và log ghi nhận `Too many open files`, trong khi hai VM còn lại có CPU thấp hơn.

Quy trình điều tra có thể là:

1. So sánh request rate, active connections và latency theo từng backend.
2. Kiểm tra FD count, `RLIMIT_NOFILE`, socket state và connection pool trên từng VM.
3. Xác định có client giữ keep-alive lâu, request nặng hay kết nối bị leak không.
4. Kiểm tra thuật toán RR có đang chia đều connection nhưng không chia đều công việc không.
5. Sizing lại giới hạn backend theo capacity đã đo; sửa leak hoặc giới hạn concurrency nếu cần.
6. Thử least connections hoặc thuật toán dựa trên active requests nếu workload phù hợp.
7. Đặt max connection/queue và timeout để bảo vệ backend; theo dõi 503, queue wait và p99.
8. Kiểm thử khi một VM bị loại khỏi pool để xác nhận hai VM còn lại chịu được tải failover.

Nếu chỉ đổi từ RR sang least connections, vấn đề có thể giảm nhưng không chắc biến mất. Nếu VM thứ nhất có FD leak, nó vẫn có thể chạm giới hạn theo thời gian. Cần sửa nguyên nhân ở backend và xác nhận tải được phân phối đúng trong cả điều kiện bình thường lẫn failover.

## 19. Các lỗi thiết kế thường gặp

- **Dùng RR cho backend khác năng lực:** số request bằng nhau nhưng tài nguyên không cân bằng. Dùng weight dựa trên benchmark.
- **Dùng Least Connections cho HTTP/2 mà không xét stream:** một connection có thể chứa nhiều request đồng thời. Theo dõi active request hoặc stream nếu nền tảng hỗ trợ.
- **Dùng sticky session quá rộng:** một nhóm client lớn có thể dồn tải lên một node. Ưu tiên session store dùng chung khi có thể.
- **Đặt connection limit quá cao:** backend nhận nhiều kết nối hơn khả năng xử lý, làm queue và latency tăng. Giới hạn theo capacity thực.
- **Đặt limit quá thấp:** request bị từ chối dù backend còn khả năng. Benchmark và điều chỉnh theo peak.
- **Queue không giới hạn:** giữ request quá lâu và làm tăng latency. Đặt queue size và timeout hữu hạn.
- **Retry đồng loạt:** client retry cùng lúc sau lỗi, tạo retry storm. Dùng backoff, jitter và giới hạn retry.
- **Health check không phản ánh readiness:** backend nhận tải khi ứng dụng chưa sẵn sàng hoặc bị loại do dependency tùy chọn. Thiết kế endpoint phù hợp.
- **Không drain khi scale in:** request đang chạy bị ngắt. Dùng deregistration delay và graceful shutdown.
- **Không kiểm thử mất node/AZ:** capacity bình thường đủ nhưng failover làm các node còn lại quá tải. Tính N-1 capacity.

## 20. Checklist lựa chọn thuật toán và giới hạn kết nối

- [ ] Đã xác định load balancer hoạt động ở L4 hay L7 và đơn vị phân phối là flow, connection, request hay stream.
- [ ] Đã đo đặc tính request, connection lifetime, keep-alive và HTTP/2 multiplexing.
- [ ] Thuật toán RR/WRR/Least Connections/Hash/Adaptive được chọn theo workload và năng lực backend.
- [ ] Weight phản ánh capacity đo được, không chỉ dựa trên số vCPU.
- [ ] Sticky session chỉ bật khi có lý do và đã kiểm tra backend failure.
- [ ] Đã phân biệt connection rate, concurrent connection, request rate và active request.
- [ ] Đã sizing connection limit ở load balancer, proxy, backend và dependency.
- [ ] Connection pool có max size, timeout, metric active/idle/pending và không tạo connection vô hạn.
- [ ] Queue có giới hạn, timeout, backpressure và hành vi overload rõ ràng.
- [ ] Health check đo readiness phù hợp và tránh flapping.
- [ ] Có connection draining, graceful shutdown và slow start khi rollout/scale.
- [ ] Đã kiểm thử burst, backend chậm, backend lỗi, scale in và mất một AZ.
- [ ] Theo dõi request rate, active connection, queue, latency p95/p99, error rate và backend saturation.

Thuật toán phân phối tải quyết định cách công việc được chia giữa các backend, còn giới hạn kết nối bảo vệ từng thành phần khỏi bị quá tải. Khi chọn thuật toán theo đặc tính giao thức và workload, sizing giới hạn theo capacity đo được, đặt queue/timeout hữu hạn và kiểm thử failover, hệ thống cân bằng tải có thể duy trì độ trễ ổn định và sử dụng compute hiệu quả hơn.
