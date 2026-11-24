# Thông lượng mạng, giới hạn kết nối và hiệu năng theo kích thước máy

## 1. Vì sao hiệu năng mạng phụ thuộc vào cấu hình compute?

Một ứng dụng có thể có CPU và bộ nhớ còn dư nhưng vẫn phản hồi chậm vì máy ảo không gửi hoặc nhận dữ liệu đủ nhanh. Một API có thể đạt throughput thấp khi nhiều request nhỏ làm tăng packet rate; một worker có thể không tận dụng hết CPU vì phải chờ dữ liệu qua mạng; một máy chủ có thể từ chối kết nối mới dù băng thông chưa bão hòa vì cạn file descriptor, cổng nguồn tạm thời hoặc connection tracking table.

Trong cloud, hiệu năng mạng gắn với loại và kích thước instance, số vCPU, loại NIC ảo, khả năng xử lý packet, hàng đợi mạng, chính sách chia sẻ tài nguyên và giới hạn của dịch vụ đi qua. Hai instance có cùng số vCPU nhưng khác họ máy có thể có băng thông, packet-per-second (PPS), số network queue hoặc giới hạn flow khác nhau. Ngay trong cùng một họ máy, cấu hình lớn hơn có thể tăng băng thông theo mức cố định, theo bậc hoặc theo cơ chế baseline/burst tùy nhà cung cấp.

Để chọn đúng compute, cần phân biệt **bandwidth**, **throughput**, **goodput**, **latency**, **PPS** và **connection capacity**. Các chỉ số này mô tả các giới hạn khác nhau. Tăng băng thông danh nghĩa không giải quyết được tình trạng cạn connection tracking; tăng số kết nối không giúp một luồng TCP đơn lẻ vượt giới hạn throughput của đường truyền; tăng vCPU cũng không tự động tăng hiệu năng nếu NIC hoặc dịch vụ đích đã bão hòa.

Sau bài học, người học có thể:

- Phân biệt thông lượng, băng thông, goodput, độ trễ và packet rate.
- Nhận diện các giới hạn kết nối ở hệ điều hành, NIC, NAT, load balancer và dịch vụ đích.
- Giải thích vì sao kích thước và họ instance ảnh hưởng đến băng thông, PPS và khả năng xử lý kết nối.
- Ước lượng băng thông cần thiết và số kết nối đồng thời từ đặc điểm workload.
- Đo hiệu năng mạng, tìm nút thắt và tối ưu ứng dụng cùng cấu hình compute.
- Chọn cấu hình mạng đáp ứng yêu cầu hiệu năng, độ sẵn sàng, bảo mật và chi phí.

## 2. Những chỉ số cần phân biệt

### 2.1. Bandwidth – băng thông danh nghĩa

Bandwidth là khả năng truyền dữ liệu tối đa được quảng bá hoặc cấu hình cho một liên kết hay tài nguyên mạng. Đơn vị thường là bit mỗi giây: Mbps, Gbps. Ví dụ, liên kết 10 Gbps có giới hạn lý thuyết 10 tỷ bit mỗi giây trước khi trừ overhead giao thức.

Bandwidth không đồng nghĩa với tốc độ ứng dụng thực nhận. Một instance có NIC danh nghĩa 10 Gbps vẫn có thể đạt thấp hơn do giới hạn ở host, virtual switch, route, NAT, load balancer, peer, storage service hoặc Internet gateway. Băng thông cũng có thể được chia sẻ giữa nhiều flow, nhiều NIC hoặc nhiều workload theo chính sách của nền tảng.

### 2.2. Throughput – lượng dữ liệu truyền được

Throughput là tốc độ dữ liệu thực tế đi qua một điểm đo trong một khoảng thời gian. Có thể đo theo chiều vào (ingress) và chiều ra (egress), theo một NIC, một instance, một flow hoặc toàn ứng dụng.

Khi so sánh throughput, phải xác định điểm đo và chiều truyền. Thông lượng nhận tại máy nguồn có thể khác thông lượng nhận tại máy đích nếu có retransmission, packet loss hoặc phép đo không cùng khoảng thời gian. Tổng throughput của nhiều flow cũng không nói lên hiệu năng của từng flow.

### 2.3. Goodput – dữ liệu hữu ích của ứng dụng

Goodput là phần dữ liệu hữu ích mà ứng dụng nhận được mỗi giây, sau khi loại phần overhead như Ethernet/IP/TCP/UDP header, TLS framing, retransmission và giao thức ứng dụng. Một liên kết có throughput cao nhưng nhiều retransmission hoặc nhiều overhead có thể tạo goodput thấp.

Ví dụ, truyền nhiều packet nhỏ làm tỷ lệ header trên dữ liệu hữu ích tăng. Truyền lại packet do mất gói cũng tiêu tốn băng thông mà không tăng dữ liệu ứng dụng nhận được. Khi đánh giá dịch vụ, nên theo dõi cả throughput ở tầng mạng và tốc độ hoàn thành công việc ở tầng ứng dụng.

### 2.4. Latency – độ trễ mạng

Latency là thời gian dữ liệu hoặc request đi từ điểm gửi đến điểm nhận, hoặc thời gian một thao tác mạng hoàn tất theo định nghĩa phép đo. Độ trễ thường được biểu diễn bằng millisecond (ms), đôi khi microsecond (µs) trong mạng nội bộ hiệu năng cao.

Phân biệt RTT (round-trip time) với one-way latency. RTT đo thời gian gửi đi và nhận phản hồi; one-way latency đo một chiều và cần đồng bộ thời gian giữa hai đầu nếu đo qua timestamp. Ứng dụng request/response thường chịu ảnh hưởng trực tiếp của RTT và số lần round trip.

Không chỉ theo dõi latency trung bình. p95, p99 và p99.9 giúp nhận diện các request chậm ở đuôi phân bố. Một hệ thống có RTT trung bình thấp nhưng p99 cao có thể gặp timeout, retry và tăng số kết nối đồng thời vào giờ cao điểm.

### 2.5. Packet rate – số packet mỗi giây

PPS (Packets Per Second) cho biết số packet được xử lý mỗi giây. Hai workload có cùng throughput nhưng kích thước packet khác nhau có thể có PPS rất khác nhau. Packet nhỏ tạo nhiều lần xử lý header, interrupt, lookup và kiểm tra chính sách hơn trên cùng lượng dữ liệu.

Vì vậy, workload có nhiều message nhỏ, RPC ngắn, DNS request hoặc packet telemetry có thể bị giới hạn bởi PPS hoặc CPU xử lý mạng trước khi đạt băng thông tối đa. Khi chọn instance, cần xem cả bandwidth và packet-rate capability nếu nhà cung cấp công bố.

### 2.6. Connection capacity – khả năng duy trì kết nối

Connection capacity là khả năng mở và duy trì các kết nối đồng thời. Nó không phải một con số duy nhất. Một kết nối có thể bị giới hạn bởi file descriptor, socket memory, ephemeral port, TCP backlog, connection tracking, NAT/SNAT, load balancer, firewall hoặc giới hạn của dịch vụ đích.

Phải phân biệt:

- **Concurrent connections:** số kết nối đang mở tại cùng thời điểm.
- **Connection establishment rate:** số kết nối mới được tạo mỗi giây.
- **Request rate:** số request ứng dụng xử lý mỗi giây.
- **Active flows:** số luồng mạng mà thiết bị hoặc dịch vụ đang theo dõi.

Một ứng dụng có thể xử lý hàng chục nghìn request mỗi giây qua một pool gồm vài trăm kết nối keep-alive. Ứng dụng khác có thể tạo một kết nối mới cho mỗi request và nhanh chóng chạm giới hạn connection rate hoặc cổng nguồn. Không được dùng request/s để suy ra số kết nối mà chưa biết thời gian sống và cách tái sử dụng kết nối.

## 3. Đường đi của lưu lượng trong cloud

### 3.1. Từ tiến trình đến NIC ảo

Lưu lượng từ ứng dụng thường đi qua socket API, TCP hoặc UDP stack, routing table, firewall và virtual network interface. Ở phía máy chủ cloud, NIC ảo được ánh xạ xuống hạ tầng mạng của nhà cung cấp. Một số nền tảng dùng enhanced networking, SR-IOV hoặc cơ chế tăng tốc I/O để giảm overhead của virtual switch và CPU host.

```text
Ứng dụng
   |
   v
Socket / TCP / UDP
   |
   v
Kernel networking + firewall + routing
   |
   v
Virtual NIC / network queues
   |
   v
Virtual switch / cloud fabric
   |
   +---- Load balancer / NAT / gateway
   |
   v
NIC và network stack của peer
   |
   v
Ứng dụng đích
```

Mỗi lớp có thể áp dụng giới hạn hoặc thêm độ trễ. Một route đúng không bảo đảm throughput cao nếu NIC queue bị nghẽn. Một NIC có băng thông cao không bảo đảm ứng dụng nhận được nhiều request nếu worker pool, TLS handshake hoặc database phía sau đã bão hòa.

### 3.2. Ingress và egress

Ingress là lưu lượng đi vào tài nguyên; egress là lưu lượng đi ra. Một số nền tảng áp dụng giới hạn theo từng chiều, theo tổng hai chiều hoặc theo loại đường đi. Cần xác minh cách tính của nhà cung cấp cho loại instance cụ thể.

Đường egress ra Internet có thể đi qua NAT gateway, firewall, proxy hoặc Internet gateway. Đường truy cập dịch vụ nội bộ có thể đi qua private endpoint, load balancer hoặc mạng peering. Các đường khác nhau có thể có giới hạn băng thông, số flow, chi phí và chính sách bảo mật khác nhau.

### 3.3. Giới hạn end-to-end

Thông lượng của một request bị giới hạn bởi thành phần chậm nhất trên đường đi. Có thể dùng mô hình khái quát:

\[
Throughput_{effective} \leq \min(B_1, B_2, \ldots, B_n)
\]

Trong đó mỗi \(B_i\) là giới hạn hữu hiệu của một lớp: NIC instance, host, route, NAT, load balancer, network fabric, peer hoặc dịch vụ đích. Công thức này là mô hình sàng lọc; giới hạn thực tế còn phụ thuộc số flow, packet size, congestion và cách các thành phần chia sẻ tài nguyên.

Ví dụ, instance có thể gửi tối đa 10 Gbps nhưng NAT gateway chỉ còn 4 Gbps năng lực hữu dụng cho workload tại thời điểm đó. Throughput egress của ứng dụng sẽ bị giới hạn ở NAT hoặc ở một thành phần khác trên đường đi, tùy giá trị nào thấp hơn.

## 4. Kích thước instance ảnh hưởng hiệu năng mạng như thế nào?

### 4.1. Băng thông theo họ và kích thước máy

Nhà cung cấp cloud thường công bố mức hiệu năng mạng theo họ máy và kích thước instance. Instance nhỏ có thể có băng thông thấp hơn; instance lớn hơn thường được cấp nhiều năng lực mạng hơn, nhưng mức tăng có thể theo bậc hoặc có điều kiện. Không nên giả định tăng gấp đôi vCPU sẽ làm băng thông tăng gấp đôi.

Khi đọc bảng thông số, kiểm tra:

- Băng thông tối đa và băng thông baseline.
- Hiệu năng có burst hay không và điều kiện sử dụng burst.
- Giới hạn ingress, egress hoặc tổng hai chiều.
- PPS tối đa hoặc khuyến nghị về kích thước packet.
- Số NIC, số queue và khả năng multi-queue.
- Số flow hoặc kết nối được hỗ trợ nếu nhà cung cấp công bố.
- Khả năng enhanced networking, SR-IOV hoặc accelerated networking.
- Giới hạn riêng theo vùng, host, placement group hoặc loại instance.

Tên gọi như `up to`, `maximum`, `baseline` hoặc `network optimized` có ý nghĩa khác nhau giữa nhà cung cấp. Hãy xem tài liệu đúng loại instance và kiểm chứng bằng phép đo trong vùng triển khai dự kiến.

### 4.2. vCPU và xử lý packet

CPU tham gia xử lý network stack, interrupt, encryption, checksum, packet filtering, connection tracking và ứng dụng. Khi PPS cao hoặc có nhiều kết nối ngắn, CPU có thể trở thành nút thắt trước khi NIC đạt giới hạn băng thông.

Một instance có ít vCPU nhưng NIC tốc độ cao có thể không xử lý hết packet rate của workload nhiều packet nhỏ. Ngược lại, instance có nhiều vCPU nhưng NIC giới hạn thấp vẫn không đạt throughput mong muốn. Vì vậy, chọn compute cần ghép năng lực CPU và network theo mẫu tải.

### 4.3. Network queue, RSS và multi-queue

NIC có thể sử dụng nhiều hàng đợi nhận/gửi để phân phối packet qua nhiều CPU core. Receive Side Scaling (RSS) thường dùng hash của flow để đưa packet đến queue phù hợp. Multi-queue giúp tăng khả năng xử lý song song, nhưng hiệu quả phụ thuộc số queue, CPU affinity, driver và cách ứng dụng tạo flow.

Nếu chỉ có một flow TCP lớn, hash có thể đưa flow đó vào một queue/CPU cụ thể; tổng năng lực nhiều queue không nhất thiết được một flow đơn khai thác. Nhiều flow độc lập thường phân phối tốt hơn. Kiểm tra cấu hình queue và mức sử dụng CPU theo core khi throughput thấp nhưng tổng CPU utilization vẫn có vẻ thấp.

### 4.4. Enhanced networking và đường I/O tăng tốc

Một số nền tảng cung cấp NIC ảo tăng tốc hoặc cơ chế gần với SR-IOV để giảm overhead của virtual switch và tăng throughput/PPS. Tính năng có thể yêu cầu loại instance, driver, image, kernel hoặc cấu hình cụ thể.

Đừng mặc định mọi instance đều hỗ trợ cùng một đường tăng tốc. Khi dùng VM, container hoặc bare metal, xác minh cách NIC được expose, driver tương thích và giới hạn của hypervisor. Trong môi trường container, quyền truy cập NIC/queue và cấu hình CNI cũng có thể ảnh hưởng hiệu năng.

### 4.5. Burst và baseline network performance

Một số instance có hiệu năng mạng baseline và có thể đạt mức cao hơn trong thời gian giới hạn hoặc khi còn credit. Benchmark ngắn có thể đạt kết quả cao, nhưng tải liên tục có thể giảm về baseline. Các nền tảng khác công bố một mức băng thông tối đa hoặc mức bảo đảm riêng.

Với workload chạy dài, cần đo đủ lâu để quan sát hành vi sau giai đoạn burst. Theo dõi metric credit hoặc network allowance nếu dịch vụ có cung cấp. Không thiết kế SLO dựa trên mức tối đa chỉ đạt được trong điều kiện ngắn hạn.

## 5. Hiểu giới hạn kết nối theo từng lớp

### 5.1. Giới hạn socket và file descriptor của hệ điều hành

Trên Linux, mỗi socket đang mở thường chiếm một file descriptor trong tiến trình. Nếu tiến trình chạm giới hạn `ulimit -n` hoặc giới hạn hệ thống, việc mở socket mới có thể thất bại dù mạng vẫn còn băng thông.

Các giới hạn cần xem xét:

- File descriptor limit của tiến trình và hệ thống.
- Số socket đang mở và trạng thái TCP.
- Bộ nhớ kernel dành cho socket send/receive buffer.
- TCP listen backlog và giới hạn hàng đợi SYN/accept.
- Số luồng worker và giới hạn connection pool của ứng dụng.

Tăng file descriptor có thể cần thiết cho server nhiều kết nối, nhưng không thay thế việc kiểm soát vòng đời socket và dung lượng bộ nhớ. Mỗi kết nối tiêu thụ tài nguyên ở cả client và server.

### 5.2. Ephemeral port và kết nối outbound

Khi một máy chủ mở kết nối TCP outbound, hệ điều hành thường chọn cổng nguồn tạm thời (ephemeral port). Một kết nối được nhận diện bởi tuple gồm địa chỉ IP nguồn, cổng nguồn, địa chỉ IP đích và cổng đích cùng giao thức. Với cùng một địa chỉ nguồn và cùng endpoint đích, số cổng nguồn khả dụng có thể giới hạn số kết nối đồng thời đến endpoint đó.

Điều này thường ảnh hưởng đến client tạo rất nhiều kết nối outbound đến cùng một database, API hoặc proxy. Mở rộng dải ephemeral port có thể giúp trong một số trường hợp, nhưng vẫn bị giới hạn bởi tuple, NAT, conntrack và tài nguyên phía đích. Không được coi dải cổng 16-bit là một con số kết nối tổng quát cho toàn hệ thống; nhiều địa chỉ nguồn hoặc endpoint khác nhau làm thay đổi số tuple có thể sử dụng.

Kết nối ở trạng thái `TIME_WAIT` cũng có thể giữ tuple trong một khoảng thời gian sau khi đóng. Tạo kết nối mới liên tục thay vì tái sử dụng connection pool có thể làm tăng áp lực lên cổng nguồn, CPU, TLS handshake và dịch vụ đích.

### 5.3. TCP backlog và connection establishment

Server TCP có hàng đợi cho các kết nối đang bắt tay và các kết nối đã hoàn tất handshake nhưng chưa được ứng dụng accept. Nếu ứng dụng accept chậm, backlog có thể đầy và client gặp timeout hoặc reset. Giới hạn này khác với số kết nối đang được ứng dụng phục vụ.

Khi chẩn đoán, kiểm tra listen backlog, tốc độ accept, số worker, CPU và các trạng thái TCP. Chỉ tăng backlog không giải quyết được nếu ứng dụng không xử lý kịp hoặc dịch vụ phía sau đã quá tải.

### 5.4. Connection tracking và firewall

Firewall stateful, NAT và một số lớp mạng theo dõi trạng thái flow trong connection tracking table. Mỗi flow có thể tiêu thụ một entry. Khi bảng đầy hoặc đạt quota, kết nối mới có thể bị drop dù băng thông còn dư.

Các giới hạn có thể nằm ở:

- Conntrack table trong hệ điều hành hoặc node.
- Stateful firewall hoặc security appliance.
- NAT gateway và số cổng nguồn được cấp phát.
- Cloud load balancer hoặc proxy theo số connection/flow.
- Giới hạn flow tracking của instance hoặc NIC.

Tăng conntrack maximum cần đi kèm kiểm tra RAM, timeout và tỷ lệ flow thực tế. Timeout quá dài có thể giữ entry không cần thiết; timeout quá ngắn có thể làm gián đoạn kết nối hợp lệ hoặc UDP flow. Hãy điều chỉnh theo giao thức và chính sách nền tảng.

### 5.5. NAT và giới hạn SNAT port

Khi nhiều workload outbound dùng chung một địa chỉ IP NAT, thiết bị NAT phải phân bổ cổng nguồn cho các kết nối. Nếu số kết nối mới đến cùng endpoint tăng nhanh, cổng SNAT có thể cạn hoặc đạt giới hạn phân bổ. Biểu hiện có thể là lỗi kết nối ngẫu nhiên, timeout hoặc lỗi chỉ xuất hiện khi scale-out.

Hướng xử lý có thể gồm tái sử dụng kết nối, connection pooling, phân bổ thêm địa chỉ IP/NAT capacity nếu dịch vụ hỗ trợ, dùng private endpoint cho dịch vụ nội bộ hoặc giảm số kết nối outbound đồng thời. Cần kiểm tra giới hạn chính thức của NAT service và cách nhà cung cấp phân bổ port theo destination.

### 5.6. Load balancer và dịch vụ đích

Load balancer có thể giới hạn số kết nối đồng thời, connection rate, số backend, số listener, số target hoặc throughput. Một số loại duy trì kết nối client và tạo kết nối riêng đến backend; một số dùng proxy hoặc connection multiplexing. Hành vi khác nhau ảnh hưởng cách tính connection capacity.

Dịch vụ đích cũng có giới hạn riêng: database connection limit, worker pool, thread pool, API quota hoặc số session. Tăng số instance client có thể làm tổng kết nối vượt khả năng database. Hãy tính cả số kết nối từ từng instance và tổng số instance sau autoscaling.

## 6. Ước lượng băng thông và số kết nối

### 6.1. Quy đổi bandwidth sang tốc độ dữ liệu

Với đơn vị bit/s, tốc độ byte/s lý thuyết được tính bằng cách chia cho 8:

\[
10\text{ Gbit/s} \div 8 = 1.25\text{ GB/s}
\]

Đây là giới hạn lý thuyết trước overhead Ethernet/IP/TCP, TLS, retransmission và giới hạn của các lớp khác. Goodput của ứng dụng sẽ thấp hơn. Cũng cần phân biệt GB hệ thập phân với GiB hệ nhị phân khi đối chiếu dashboard.

### 6.2. Bandwidth-delay product

Bandwidth-delay product (BDP) ước lượng lượng dữ liệu có thể đang "trên đường truyền" trong một RTT:

\[
BDP = Bandwidth \times RTT
\]

Nếu bandwidth tính bằng bit/s và RTT bằng giây, chia kết quả cho 8 để đổi sang byte. Ví dụ, đường truyền 10 Gbit/s với RTT 10 ms có BDP:

\[
10^{10} \times 0.01 \div 8 = 12.5\text{ MB}
\]

Để một TCP flow tận dụng hết băng thông trong điều kiện lý tưởng, cửa sổ dữ liệu đang outstanding phải đủ lớn so với BDP, đồng thời congestion window, receive window và hệ điều hành phải cho phép. Một TCP flow có window nhỏ hơn nhiều so với BDP có thể không đạt throughput của liên kết.

### 6.3. Ước lượng số kết nối đồng thời

Với workload request/response ổn định, định luật Little cho quan hệ gần đúng:

\[
Concurrent\ requests \approx Request\ rate \times Average\ response\ time
\]

Ví dụ, API xử lý 2.000 request/s với thời gian xử lý trung bình 150 ms có khoảng:

\[
2{,}000 \times 0.15 = 300
\]

request đang được xử lý đồng thời ở trạng thái ổn định. Đây là số request in-flight trung bình, không nhất thiết bằng số TCP connection. Một keep-alive connection có thể phục vụ nhiều request tuần tự; HTTP/2 có thể multiplex nhiều stream trên một connection; HTTP/1.1 pipeline và proxy có hành vi khác nhau.

Để ước lượng connection pool, cần biết thời gian sống kết nối, số request trên mỗi connection, mức concurrency mỗi connection, tỷ lệ kết nối idle và số client instance. Cộng thêm headroom cho burst và sự cố, nhưng không tạo pool quá lớn khiến database hoặc downstream service bị quá tải.

### 6.4. Ước lượng packet rate

PPS phụ thuộc throughput và kích thước packet trên đường truyền. Với cùng throughput, packet nhỏ tạo PPS cao hơn. Phần overhead Ethernet/IP/TCP và framing làm phép tính thực tế phức tạp hơn; dùng phép tính gần đúng để sàng lọc, sau đó đo bằng công cụ và metric của nền tảng.

Nếu workload gồm nhiều RPC nhỏ, DNS hoặc telemetry, cần kiểm tra CPU theo core, NIC queue và packet drop thay vì chỉ nhìn Gbps. Tăng kích thước payload hoặc batching có thể giảm PPS, nhưng phải cân nhắc latency và yêu cầu tương tác.

## 7. Chọn kích thước instance theo mẫu tải mạng

### 7.1. Workload throughput cao

Ví dụ: streaming, truyền tệp lớn, backup, replication hoặc API trả payload lớn. Ưu tiên instance có băng thông mạng cao, NIC phù hợp và khả năng duy trì throughput trong thời gian dài. Kiểm tra giới hạn egress/ingress, số NIC, placement và giới hạn của peer.

Đối với một luồng TCP lớn, kiểm tra RTT, BDP, cửa sổ TCP và khả năng một flow tận dụng nhiều queue. Với nhiều luồng, kiểm tra tổng throughput và fairness. Đảm bảo storage hoặc CPU xử lý dữ liệu không trở thành nút thắt sau khi tăng mạng.

### 7.2. Workload PPS cao

Ví dụ: proxy, firewall, service mesh, DNS, API với request nhỏ hoặc telemetry. Ưu tiên instance có PPS cao, đủ vCPU và network stack được tăng tốc. Kiểm tra softirq, interrupt distribution, RSS, queue count, packet drop và CPU theo core.

Một workload PPS cao có thể cần nhiều core hơn một workload truyền tệp lớn cùng băng thông. Tối ưu batching, giảm packet không cần thiết, dùng connection reuse và tránh các bước xử lý header tốn CPU nếu không cần.

### 7.3. Workload nhiều kết nối đồng thời

Ví dụ: reverse proxy, WebSocket, application gateway, API server hoặc dịch vụ có nhiều client giữ kết nối lâu. Ưu tiên instance có đủ memory cho socket buffer, file descriptor, CPU cho TLS và connection tracking. Kiểm tra giới hạn load balancer, NAT và backend.

Với kết nối lâu dài, số connection đồng thời có thể cao ngay cả khi request rate thấp. Theo dõi số socket theo trạng thái, bộ nhớ socket, connection churn và số kết nối idle. Dùng keep-alive, pool và timeout hợp lý để giảm tạo/hủy kết nối liên tục.

### 7.4. Workload nhạy độ trễ

Ví dụ: giao dịch, gaming, RPC nội bộ hoặc ứng dụng tương tác. Ưu tiên RTT thấp, đường mạng ổn định, placement phù hợp, ít hop và instance có năng lực mạng nhất quán. Đo p95/p99 theo từng vùng và giữa các thành phần.

Không phải lúc nào instance lớn nhất cũng cho latency tốt nhất. Cần kiểm tra vị trí dữ liệu, network path, congestion, CPU scheduling và hàng đợi ở load balancer. Đặt compute gần dependency thường giảm RTT, nhưng phải đáp ứng yêu cầu vùng dữ liệu và HA.

### 7.5. Bảng chọn nhanh

| Mẫu tải | Chỉ số ưu tiên | Đặc điểm instance cần xem | Tối ưu ứng dụng |
|---|---|---|---|
| Truyền dữ liệu lớn | Throughput, retransmission, RTT | Băng thông NIC, baseline/burst, placement | TCP window, batching, parallel streams khi phù hợp |
| Nhiều packet nhỏ | PPS, CPU/core, packet drops | PPS capability, vCPU, RSS/multi-queue | Giảm packet overhead, batching, tối ưu worker |
| Nhiều kết nối lâu dài | Concurrent connections, memory, FD | RAM, socket capacity, conntrack và flow limits | Keep-alive, pool, timeout, giới hạn connection |
| Nhiều kết nối ngắn | Connection rate, TIME_WAIT, SNAT | CPU, ephemeral ports, NAT/LB limits | Reuse connection, HTTP keep-alive, giảm handshake |
| RPC nhạy latency | RTT p95/p99, jitter, loss | Network path, placement, baseline ổn định | Giảm round trip, timeout và retry hợp lý |
| Egress lớn | Egress throughput, NAT capacity, cost | NIC, NAT/gateway path, quota | Private endpoint, cache, nén và phân phối dữ liệu |

## 8. Tối ưu kết nối ở tầng ứng dụng

### 8.1. Connection pooling và keep-alive

Connection pooling tái sử dụng kết nối đã mở thay vì tạo mới cho mỗi request. Điều này giảm TCP handshake, TLS handshake, CPU và áp lực lên ephemeral port/NAT. Pool cần có giới hạn kích thước, thời gian idle, thời gian sống tối đa và kiểm tra kết nối hỏng.

Pool quá nhỏ làm request phải chờ lấy connection; pool quá lớn có thể làm backend cạn connection hoặc bộ nhớ. Tổng pool trên toàn hệ thống bằng pool mỗi instance nhân với số instance. Khi autoscaling tăng số instance, cần tính lại tổng kết nối đến database hoặc API đích.

Keep-alive giúp duy trì kết nối để tái sử dụng. Cấu hình timeout ở client, load balancer, proxy và server cần tương thích. Nếu một lớp đóng kết nối sớm hơn lớp khác, ứng dụng có thể gặp lỗi trên kết nối tưởng như vẫn còn hiệu lực.

### 8.2. HTTP/2, multiplexing và HTTP/3

HTTP/2 cho phép nhiều stream chia sẻ một kết nối TCP, giúp giảm số connection trong một số workload và giảm chi phí handshake. Tuy nhiên, các stream vẫn chia sẻ một TCP connection; packet loss có thể ảnh hưởng nhiều stream do cơ chế truyền của TCP.

HTTP/3 chạy trên QUIC/UDP và có cơ chế stream riêng, có thể giảm một số ảnh hưởng head-of-line giữa các stream. Nhưng hiệu năng phụ thuộc client/server, load balancer, firewall, NAT và khả năng hỗ trợ UDP trên đường đi. Không nên chuyển giao thức chỉ dựa trên giả định HTTP/3 luôn nhanh hơn; cần benchmark theo mạng và client thật.

### 8.3. Timeout, retry và backoff

Timeout phải được đặt ở các lớp kết nối, request và downstream call. Timeout quá dài giữ connection và worker trong thời gian lâu; timeout quá ngắn tạo lỗi giả khi hệ thống có jitter bình thường.

Retry chỉ nên áp dụng với thao tác có thể retry an toàn hoặc có idempotency key. Retry đồng loạt không có backoff có thể tạo retry storm, làm tăng connection rate và đẩy dịch vụ đích vào tình trạng quá tải. Dùng exponential backoff, jitter, retry budget và circuit breaker khi phù hợp.

### 8.4. Giảm số round trip và payload

Gom nhiều thao tác nhỏ thành một request, cache dữ liệu, nén payload khi có lợi và tránh gọi chuỗi API tuần tự có thể giảm RTT tích lũy. Tuy nhiên, payload quá lớn có thể tăng memory pressure và latency đầu-cuối. Cần đo cả thời gian serialize, compression, truyền, giải nén và xử lý.

### 8.5. TLS và mã hóa

TLS bảo vệ dữ liệu khi truyền nhưng tiêu thụ CPU và thêm chi phí handshake. Tái sử dụng kết nối, session resumption và thư viện TLS được tối ưu có thể giảm overhead. Không tắt TLS để đạt benchmark trong môi trường production; thay vào đó, đo CPU, handshake rate và cấu hình cipher/protocol theo chính sách bảo mật.

## 9. Quan sát và chẩn đoán

### 9.1. Chỉ số ở cấp cloud

Theo dõi tối thiểu:

- Ingress và egress bytes/s, packets/s theo instance/NIC.
- Network bandwidth allowance, baseline/burst hoặc credit nếu dịch vụ có.
- Packet drop, error, retransmission và connection reset.
- Số flow/connection và metric của NAT, load balancer, firewall.
- Latency giữa các vùng, giữa client và backend, p50/p95/p99.
- CPU utilization theo core, softirq, memory và network queue.
- Quota, throttling và giới hạn dịch vụ đích.

Tên metric khác nhau giữa nhà cung cấp. Một số metric được lấy mẫu theo phút nên có thể không thể hiện burst ngắn. Kết hợp metric cloud với telemetry từ hệ điều hành và ứng dụng.

### 9.2. Công cụ Linux

Một số lệnh hữu ích:

```bash
# Xem địa chỉ, trạng thái và bộ đếm lỗi của interface
ip -s link

# Xem socket TCP/UDP và trạng thái kết nối
ss -s
ss -tan state established
ss -tan state time-wait

# Xem giới hạn file descriptor của shell/tiến trình
ulimit -n
cat /proc/sys/fs/file-nr

# Xem thống kê TCP/IP và retransmission
nstat -az

# Xem tốc độ interface theo thời gian (nếu đã cài sysstat)
sar -n DEV,TCP,ETCP 1
```

Tùy quyền và hệ điều hành, có thể dùng thêm `ethtool -S <interface>` để xem counter của NIC, `ethtool -l <interface>` để xem channel/queue và `conntrack -S` để xem thống kê connection tracking nếu công cụ và module được cài. Một số driver hoặc cloud NIC không expose toàn bộ counter.

Không đọc một chỉ số riêng lẻ để kết luận. Ví dụ, retransmission tăng có thể do packet loss, congestion, receiver chậm hoặc lỗi đường truyền; số `TIME_WAIT` cao có thể là hệ quả của connection churn nhưng không tự động chứng minh ephemeral port đã cạn.

### 9.3. Kiểm tra băng thông bằng iperf3

`iperf3` đo throughput giữa hai endpoint. Chạy server ở máy đích:

```bash
iperf3 -s
```

Chạy client ở máy nguồn:

```bash
iperf3 -c <server-private-ip> -t 60
```

Đo chiều ngược lại bằng reverse mode:

```bash
iperf3 -c <server-private-ip> -t 60 -R
```

Có thể thử nhiều luồng song song bằng `-P`, nhưng cần bắt đầu từ một luồng rồi tăng dần để hiểu giới hạn per-flow và aggregate. Không chạy benchmark băng thông trên mạng production nếu chưa được phép; tải thử có thể ảnh hưởng dịch vụ khác, phát sinh phí egress hoặc làm nghẽn đường truyền dùng chung. Đảm bảo firewall cho phép cổng thử nghiệm và chỉ mở trong phạm vi cần thiết.

### 9.4. Kiểm tra kết nối và cổng

Khi gặp lỗi không mở được kết nối mới, kiểm tra theo thứ tự:

1. Ứng dụng có còn file descriptor và worker capacity không?
2. Listen socket có đang bind đúng địa chỉ/cổng và backlog có đầy không?
3. Ephemeral port hoặc tuple outbound có bị cạn không?
4. Conntrack, firewall hoặc NAT có chạm giới hạn không?
5. Load balancer còn connection/flow capacity và backend healthy không?
6. Dịch vụ đích có đạt giới hạn connection, quota hoặc thread pool không?
7. Có packet drop, retransmission, DNS delay hoặc route bất thường không?

## 10. Quy trình chọn và tối ưu cấu hình mạng

### Bước 1: Mô tả workload

Ghi lại request/s, payload trung bình và tối đa, tỷ lệ ingress/egress, số kết nối đồng thời, connection rate, thời gian sống kết nối, giao thức, RTT mục tiêu và số vùng triển khai. Phân biệt tải bình thường, tải đỉnh và burst.

### Bước 2: Xác định đường truyền

Vẽ đường đi giữa client, instance, load balancer, NAT, service endpoint, database và Internet. Ghi rõ lớp nào có quota, giới hạn băng thông, PPS, connection hoặc chi phí. Xác định traffic đi trong cùng zone, giữa zone, giữa region hay ra Internet.

### Bước 3: Tìm giới hạn của instance

Đối chiếu họ và kích thước instance với thông số bandwidth, PPS, queue, NIC và enhanced networking. Kiểm tra CPU/memory đủ cho network stack, TLS và ứng dụng. Xác minh baseline/burst và quota tại vùng triển khai.

### Bước 4: Ước lượng capacity

Tính throughput từ request rate nhân payload trung bình, sau đó cộng overhead và headroom theo yêu cầu. Ước lượng request in-flight bằng request rate nhân thời gian xử lý trung bình. Từ đó tính connection pool, file descriptor, NAT/SNAT và downstream connection budget.

### Bước 5: Benchmark có kiểm soát

Đo một flow và nhiều flow; chiều ingress và egress; packet size nhỏ và lớn; tải ngắn và tải kéo dài. Theo dõi throughput, goodput, RTT, retransmission, PPS, CPU và connection metrics. Chạy thử trên loại instance và placement gần với production.

### Bước 6: Tối ưu ứng dụng và hạ tầng

Ưu tiên connection reuse, pool hợp lý, giảm round trip, tối ưu payload và phân phối worker. Chỉ tăng instance size, NIC, NAT capacity hoặc số địa chỉ nguồn khi số liệu cho thấy lớp đó là nút thắt.

### Bước 7: Kiểm thử giới hạn và sự cố

Thử scale-out, backend chậm, NAT/LB capacity, packet loss và node replacement trong môi trường kiểm thử. Đảm bảo autoscaling không làm vượt connection limit của database hoặc dịch vụ đích. Thiết lập cảnh báo và runbook trước khi đưa vào production.

## 11. Ví dụ thực tế

### Ví dụ 1: API có nhiều kết nối ngắn

Một API nhận 5.000 request/s. Mỗi request gọi một dịch vụ nội bộ, nhưng client tạo kết nối TCP mới cho từng request. Khi tải tăng, lỗi kết nối và CPU tăng dù throughput mạng chưa đạt giới hạn.

**Phân tích:** connection establishment rate rất cao; mỗi kết nối cần handshake, có thể thêm TLS handshake, chiếm ephemeral port trong thời gian hoạt động và TIME_WAIT sau khi đóng. NAT hoặc firewall có thể theo dõi quá nhiều flow. CPU tiêu tốn cho handshake thay vì xử lý nghiệp vụ.

**Hướng xử lý:** bật keep-alive, dùng connection pool có giới hạn, xem xét HTTP/2 khi phù hợp, cấu hình timeout nhất quán và đo lại connection rate, TIME_WAIT, CPU, retransmission và p99 latency. Kiểm tra tổng connection đến backend sau autoscaling.

### Ví dụ 2: Worker truyền tệp lớn

Một worker đọc dữ liệu từ object storage và gửi kết quả đến một node xử lý. Throughput chỉ đạt một phần nhỏ so với băng thông danh nghĩa của instance.

**Phân tích:** chạy iperf3 giữa hai node để kiểm tra đường mạng; so sánh một flow với nhiều flow; đo RTT, retransmission và CPU. Kiểm tra giới hạn egress của instance, NAT/gateway, endpoint storage và băng thông của node đích. Xem ứng dụng có đọc/ghi đủ song song và storage có theo kịp không.

**Hướng xử lý:** chọn instance có network baseline phù hợp, dùng private endpoint nếu phù hợp, tăng concurrency đọc theo partition, tối ưu buffer và giảm round trip. Xác minh chi phí truyền dữ liệu và không để một luồng đơn trở thành giới hạn nếu ứng dụng có thể chia tác vụ an toàn.

### Ví dụ 3: Proxy duy trì nhiều WebSocket

Một proxy giữ hàng trăm nghìn kết nối WebSocket lâu dài. Request rate không cao nhưng bộ nhớ và số file descriptor tăng nhanh.

**Phân tích:** số kết nối đồng thời khác với request rate. Mỗi socket dùng file descriptor và bộ nhớ kernel/ứng dụng. Cần theo dõi socket state, memory, FD, connection tracking, load balancer timeout và số kết nối trên mỗi instance.

**Hướng xử lý:** chọn instance có đủ RAM và vCPU, tăng giới hạn FD có kiểm soát, dùng event-driven I/O, đặt idle timeout phù hợp, phân phối kết nối qua nhiều instance và kiểm tra giới hạn LB. Đặt capacity target thấp hơn giới hạn cứng để còn headroom khi node lỗi hoặc rolling deployment.

## 12. Sai lầm thường gặp

- **Chỉ nhìn Gbps:** bỏ qua PPS, latency, connection rate và giới hạn dịch vụ trên đường đi.
- **Cho rằng instance lớn hơn luôn nhanh hơn theo tỷ lệ vCPU:** băng thông có thể tăng theo bậc hoặc bị giới hạn riêng.
- **Đồng nhất request/s với connection count:** keep-alive và multiplexing làm hai đại lượng khác nhau.
- **Cho rằng một NIC 10 Gbps bảo đảm ứng dụng đạt 10 Gbps:** host, route, NAT, LB, peer và protocol overhead có thể giới hạn.
- **Tăng connection pool không giới hạn:** có thể làm database, NAT hoặc conntrack quá tải.
- **Chỉ đo tổng CPU:** một core xử lý network/softirq có thể bão hòa trong khi tổng CPU còn thấp.
- **Chạy benchmark một luồng rồi kết luận tổng năng lực:** một flow không phản ánh aggregate throughput và PPS.
- **Bỏ qua baseline/burst:** benchmark ngắn có thể không đại diện cho tải liên tục.
- **Retry ngay lập tức:** retry storm làm tăng connection rate và gây quá tải dây chuyền.
- **Tắt timeout hoặc giữ kết nối vô hạn:** socket stale chiếm tài nguyên và làm cạn capacity.
- **Mở rộng compute mà không tính downstream:** nhiều instance hơn có thể làm vượt database connection limit.
- **Không tính chi phí egress:** lưu lượng liên vùng hoặc Internet có thể tạo chi phí đáng kể.

## 13. Checklist trước khi chốt cấu hình instance và mạng

- [ ] Đã đo ingress/egress throughput và goodput theo workload thật.
- [ ] Đã xác định RTT, p95/p99 latency, packet loss và retransmission.
- [ ] Đã xác định PPS và kích thước packet điển hình.
- [ ] Đã tách request rate, connection rate và concurrent connections.
- [ ] Đã kiểm tra FD, socket memory, backlog, ephemeral port và TIME_WAIT.
- [ ] Đã kiểm tra conntrack, NAT/SNAT, load balancer và giới hạn dịch vụ đích.
- [ ] Đã đối chiếu network bandwidth/PPS theo đúng họ và kích thước instance.
- [ ] Đã kiểm tra baseline, burst, enhanced networking, NIC queue và RSS.
- [ ] Đã tính băng thông cần thiết, BDP và connection pool theo tải.
- [ ] Đã benchmark một flow/nhiều flow, hai chiều và tải kéo dài.
- [ ] Đã tối ưu keep-alive, pooling, timeout, retry và payload.
- [ ] Đã kiểm tra tác động autoscaling đến tổng kết nối downstream.
- [ ] Đã tính chi phí NAT, egress, cross-zone/cross-region và gateway.
- [ ] Đã thiết lập dashboard, cảnh báo, quota và runbook xử lý sự cố.

## 14. Kết luận

Hiệu năng mạng của workload compute được quyết định bởi toàn bộ đường truyền và khả năng xử lý ở từng lớp. Bandwidth mô tả năng lực danh nghĩa; throughput và goodput cho biết dữ liệu thực sự đi qua; latency phản ánh thời gian; PPS thể hiện số packet cần xử lý; còn connection capacity phụ thuộc nhiều giới hạn từ socket và hệ điều hành đến NAT, load balancer và dịch vụ đích.

Kích thước instance ảnh hưởng đến băng thông, packet processing, NIC queue và khả năng duy trì kết nối, nhưng mức tăng không nhất thiết tuyến tính theo vCPU. Hãy mô tả đúng mẫu tải, tính capacity, kiểm tra giới hạn end-to-end và benchmark trong điều kiện đại diện. Tối ưu connection reuse, timeout, worker, NIC và instance theo số liệu sẽ giúp đạt hiệu năng ổn định với chi phí hợp lý.
