# Lập kế hoạch dung lượng và dự phòng tài nguyên

Một ứng dụng cloud có thể chạy ổn định trong ngày bình thường nhưng thất bại đúng lúc nhu cầu tăng cao hoặc một vùng hạ tầng bị gián đoạn. Nguyên nhân đôi khi không nằm ở thuật toán hay lỗi phần mềm: CPU đã chạm giới hạn, database hết connection, hàng đợi tăng nhanh hơn tốc độ xử lý, quota không đủ để mở rộng, hoặc phần tài nguyên dự phòng không thể gánh tải khi một failure domain mất đi.

**Lập kế hoạch dung lượng (capacity planning)** là quá trình dự báo nhu cầu tài nguyên và kiểm tra hệ thống có thể đáp ứng nhu cầu đó trong những điều kiện dự kiến. **Dự phòng tài nguyên (resource redundancy)** là bố trí đủ thành phần thay thế hoặc năng lực còn lại để hệ thống duy trì hay phục hồi dịch vụ khi một thành phần gặp lỗi hoặc cần bảo trì.

Hai việc này phải được thiết kế cùng nhau. Một hệ thống có đủ compute cho ngày thường nhưng không còn năng lực khi mất một zone chưa đáp ứng mục tiêu sẵn sàng. Ngược lại, nhân đôi tất cả tài nguyên mà không dự báo tải có thể tạo hóa đơn lớn, tăng độ phức tạp và vẫn không bảo vệ được database, quota hoặc dependency dùng chung.

Bài học thuộc chương **Kiến trúc tính toán** của module **CLOUD_ARCHITECTURE**. Mục tiêu là chuyển yêu cầu nghiệp vụ thành mô hình tải, dự báo compute và các giới hạn liên quan, lựa chọn cơ chế mở rộng và dự phòng, sau đó kiểm chứng các đánh đổi về độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Chuyển số liệu người dùng, giao dịch, lưu lượng và mức tăng trưởng thành mô hình nhu cầu tài nguyên.
2. Phân biệt **capacity**, **utilization**, **throughput**, **concurrency**, **headroom**, **quota** và **saturation**.
3. Ước lượng nhu cầu compute, memory, network, storage IOPS, database connections và khả năng xử lý queue.
4. Phân biệt scale up, scale out, autoscaling, load balancing và các chiến lược dự phòng N+1/N+2.
5. Xác định tài nguyên cần dư sau khi mất instance, node, zone hoặc region theo mục tiêu RTO/RPO/SLO.
6. Thiết kế load test, stress test, soak test và diễn tập failover để kiểm tra giả định dung lượng.
7. Lập kế hoạch quota, rollout, warm-up, bảo trì, ngân sách và cảnh báo để hệ thống hoạt động ổn định.

## 2. Khái niệm nền tảng về dung lượng

### 2.1. Capacity và utilization

- **Capacity (năng lực tối đa hữu dụng):** mức tải một tài nguyên hoặc hệ thống có thể phục vụ mà vẫn đáp ứng các yêu cầu về độ trễ, tỷ lệ lỗi, tính đúng đắn và độ ổn định đã đặt ra.
- **Utilization (mức sử dụng):** phần năng lực đang được tiêu thụ, ví dụ CPU 65%, memory 70%, database connection pool 80%.
- **Throughput (thông lượng):** số lượng công việc hoàn thành trong một đơn vị thời gian, chẳng hạn 2.000 request/giây hoặc 500 giao dịch/phút.
- **Concurrency (mức đồng thời):** số request, phiên, worker hoặc tác vụ đang hoạt động tại cùng thời điểm.
- **Headroom (dư địa):** phần năng lực còn lại để hấp thụ biến động, đỉnh tải, thời gian scale hoặc suy giảm một phần.
- **Saturation (bão hòa):** trạng thái tài nguyên hoặc hệ thống không thể nhận thêm tải mà vẫn giữ chất lượng dịch vụ chấp nhận được; có thể biểu hiện qua queue, độ trễ và lỗi tăng nhanh.

Không có một ngưỡng utilization phù hợp cho mọi tài nguyên. CPU 80% trong một khoảng ngắn có thể bình thường với workload xử lý theo batch, nhưng memory 95% liên tục có thể nguy hiểm nếu ứng dụng cần heap mở rộng hoặc hệ điều hành bắt đầu reclaim/swap. Database connection 90% cũng có thể là dấu hiệu hết năng lực dù CPU còn thấp.

### 2.2. Tài nguyên khai báo và năng lực thực tế

Một VM được khai báo 8 vCPU và 32 GiB RAM không đồng nghĩa ứng dụng có thể phục vụ một lượng request cố định. Năng lực hữu dụng phụ thuộc:

- Loại CPU, kiến trúc máy, giới hạn burst/credit, hiệu năng single-thread và cấu hình nền tảng.
- Working set memory, cache, heap, garbage collection, thread/process count và bộ đệm.
- Kiểu I/O, kích thước request, truy vấn DB, số lần gọi dịch vụ ngoài và tỷ lệ cache hit.
- Giới hạn connection, file descriptor, ephemeral port, socket, queue, IOPS, bandwidth và quota.
- Độ trễ mục tiêu, tỷ lệ lỗi chấp nhận, cơ chế retry và đặc tính tải theo thời gian.

Vì vậy, capacity phải được xác định bằng **workload thực tế hoặc mô phỏng có cơ sở**, không chỉ bằng số vCPU/RAM trong bảng giá.

### 2.3. Công thức cơ bản cần biết

~~~text
Utilization = Tài nguyên đang dùng / Năng lực khả dụng
Headroom = Năng lực khả dụng - Nhu cầu hiện tại
Số instance sơ bộ = ceil(Nhu cầu tải / Năng lực hữu dụng mỗi instance)
~~~

Trong đó, ceil là làm tròn lên. Năng lực hữu dụng mỗi instance cần lấy từ benchmark ở mức latency/error mục tiêu, không phải mức tối đa ngay trước khi quá tải.

Với hệ thống cần chịu lỗi, công thức phải tính trên số instance còn lại sau khi mất failure domain. Không chỉ chia tải cho tổng số instance lúc đầy đủ.

## 3. Chuyển yêu cầu nghiệp vụ thành mô hình tải

### 3.1. Bắt đầu từ hành vi người dùng

Không nên bắt đầu capacity planning bằng câu “cần bao nhiêu máy chủ?”. Trước hết cần hiểu ứng dụng đang phục vụ ai và những thao tác nào tạo tải.

Ví dụ một nền tảng đặt chỗ:

| Hoạt động nghiệp vụ | Số liệu đầu vào | Tài nguyên chịu ảnh hưởng |
|---|---|---|
| Người dùng mở trang tìm kiếm | Lượt truy cập, số lần tìm kiếm mỗi phiên | CDN, frontend, Search API, cache |
| Xem chi tiết chỗ ở | Request/phiên, payload, tỷ lệ tải ảnh | API, object storage, CDN, database đọc |
| Tạo booking | Giao dịch/giây, tỷ lệ retry, số bước workflow | Booking API, database ghi, queue, Payment API |
| Gửi email/thông báo | Số sự kiện và thời điểm phát sinh | Worker, broker, dịch vụ gửi bên ngoài |
| Báo cáo cuối ngày | Thời điểm chạy, kích thước dữ liệu, truy vấn | Database đọc, batch worker, storage |

Từng thao tác có chi phí tài nguyên khác nhau. Một trang search có thể tạo 5 request API, 2 cache lookup và 1 query; một booking có thể tạo nhiều transaction và event. Chỉ đếm số người đăng nhập không phản ánh lượng công việc thực tế.

### 3.2. Các loại tải cần dự báo

| Loại tải | Câu hỏi | Ví dụ |
|---|---|---|
| **Average load** | Nhu cầu trung bình trong kỳ là bao nhiêu? | 400 request/giây trung bình |
| **Peak load** | Đỉnh tải theo giờ/ngày/sự kiện là bao nhiêu? | 2.000 request/giây trong đợt mở bán |
| **Burst load** | Tải tăng nhanh đến mức nào? | 500 lên 1.800 request/giây trong 30 giây |
| **Sustained load** | Mức tải cao kéo dài bao lâu? | 1.200 request/giây trong 3 giờ |
| **Seasonal load** | Tải thay đổi theo chu kỳ nào? | Cuối tuần hoặc mùa du lịch |
| **Growth load** | Số người dùng/dữ liệu tăng theo tốc độ nào? | Tăng 12% mỗi tháng |
| **Failure load** | Phần hệ thống còn lại nhận bao nhiêu tải khi lỗi? | Mất một zone, lưu lượng dồn sang zone còn lại |
| **Recovery load** | Tải phát sinh khi hệ thống phục hồi là gì? | Queue backlog, cache cold start, đồng bộ dữ liệu |

Nên ghi cả thời gian đỉnh, tốc độ thay đổi và khoảng thời gian kéo dài. Autoscaling phản ứng tốt với tải tăng từ từ có thể không kịp với spike đột ngột.

### 3.3. Tính request rate từ hành vi

Giả sử hệ thống có 100.000 người dùng hoạt động trong một ngày. Trung bình mỗi người tạo 20 API request/ngày:

~~~text
Tổng request/ngày = 100.000 * 20 = 2.000.000
Request/giây trung bình = 2.000.000 / 86.400
                         ≈ 23,15 request/giây
~~~

Con số trung bình này chưa đủ để thiết kế production. Nếu 30% request tập trung trong một giờ cao điểm thì:

~~~text
Request trong giờ cao điểm = 2.000.000 * 30% = 600.000
Request/giây trong giờ đó ≈ 600.000 / 3.600
                            ≈ 166,7 request/giây
~~~

Nếu traffic tăng gấp ba trong một sự kiện, tải có thể tiến tới khoảng 500 request/giây trong thời gian ngắn. Mô hình thực tế cần tách theo endpoint, loại thao tác và phân bố thời gian, thay vì áp cùng một hệ số cho mọi request.

### 3.4. Concurrency và thời gian xử lý

Có thể sử dụng định luật Little trong điều kiện hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request/công việc trung bình đang nằm trong hệ thống (concurrency).
- \(\lambda\): throughput trung bình (request/giây).
- \(W\): thời gian trung bình một request nằm trong hệ thống (giây).

Ví dụ, nếu API xử lý 200 request/giây và thời gian trung bình là 0,25 giây:

\[
L = 200 \times 0,25 = 50
\]

Trung bình có khoảng 50 request đồng thời. Đây là ước lượng trạng thái ổn định; không dùng trực tiếp để suy ra số thread hoặc connection pool khi latency có đuôi dài, tải dao động mạnh hoặc queue không ổn định.

## 4. Ước lượng năng lực mỗi instance

### 4.1. Benchmark ở mức chất lượng chấp nhận được

Giả sử một instance Booking API trên cấu hình compute được chọn có thể xử lý **120 request/giây** ở p95 latency dưới 200 ms và tỷ lệ lỗi dưới ngưỡng quy định. Khi vượt khoảng đó, p95 tăng nhanh và connection pool bắt đầu bão hòa.

120 request/giây là **năng lực hữu dụng** cho workload benchmark cụ thể, không phải giới hạn cố định của mọi instance có cùng cấu hình. Khi code, dữ liệu, dependency hoặc instance type thay đổi, benchmark cần được cập nhật.

### 4.2. Công thức chọn số instance ban đầu

~~~text
N = ceil(Peak request rate / Tested sustainable RPS per instance)
~~~

Với peak 500 request/giây và năng lực hữu dụng 120 request/giây:

~~~text
N = ceil(500 / 120) = 5 instances
~~~

Năm instance chỉ vừa đủ xử lý peak khi tất cả đều khỏe theo benchmark. Nếu cần mất một instance vẫn chịu được tải, cần tính dự phòng riêng.

### 4.3. Tính dự phòng N+1

Với N+1 cho trường hợp mất một instance:

\[
(N-1)\times C \geq D
\]

Trong đó \(C\) là năng lực hữu dụng của một instance và \(D\) là nhu cầu tải thiết kế.

Với C = 120 RPS, D = 500 RPS:

\[
N \geq \lceil 500/120 \rceil + 1 = 6
\]

Sáu instance cho phép còn năm instance sau khi mất một instance, tổng năng lực benchmark còn 600 RPS. Nhưng sáu instance có thể vẫn chưa đủ nếu một zone chứa nhiều instance bị mất cùng lúc.

### 4.4. Tính capacity sau khi mất zone

Giả sử sáu instance được phân bố đều ở ba zone, mỗi zone có hai instance. Khi mất một zone, chỉ còn bốn instance:

\[
4\times120 = 480\ \text{RPS}
\]

480 RPS thấp hơn nhu cầu thiết kế 500 RPS. Cấu hình đạt N+1 instance nhưng **không đạt yêu cầu mất một zone**.

Để chịu được mất một trong ba zone ở cùng mức tải:

\[
(3-1)\times k\times120 \geq 500
\]

Với \(k\) là số instance ở mỗi zone:

\[
k \geq \lceil 500/(2\times120) \rceil = 3
\]

Cần ít nhất ba instance mỗi zone, tổng cộng chín instance theo mô hình đơn giản này. Đây là giả định traffic có thể được phân phối đều và mọi thành phần liên quan đều chịu lỗi zone; cần kiểm tra network, load balancer, database và dependency trước khi tuyên bố đạt HA.

## 5. Lập kế hoạch cho toàn bộ chuỗi tài nguyên

Compute không hoạt động độc lập. Một API có thể còn CPU nhưng vẫn không phục vụ được vì database, cache, network, broker hoặc quota đã hết năng lực.

### 5.1. CPU và memory

**CPU:**

- Theo dõi utilization trung bình và p95/p99 theo khoảng thời gian.
- Phân biệt workload CPU-bound với I/O-bound; CPU thấp có thể là dấu hiệu thread đang chờ I/O hoặc connection bị nghẽn.
- Theo dõi CPU throttling ở container, burst credits ở instance burstable và thời gian chạy garbage collection.
- Kiểm tra hiệu năng đơn luồng nếu workload có thread nóng hoặc lock contention.

**Memory:**

- Đo resident set/working set, heap, non-heap, cache, buffer và memory limit.
- Theo dõi OOM kill, swap, paging, GC pause và memory leak theo thời gian.
- Với container, request/limit ảnh hưởng scheduler và giới hạn thực tế; đặt limit quá thấp có thể gây OOM dù node còn RAM.
- Dự phòng cho sidecar, agent, log buffer và hệ điều hành/runtime, không tính riêng tiến trình ứng dụng.

### 5.2. Network và kết nối

Các giới hạn cần tính:

- Băng thông ingress/egress và thông lượng của NIC hoặc instance type.
- Số connection đồng thời, connection churn, TLS handshake và ephemeral port.
- Giới hạn connection của load balancer, NAT gateway, firewall, API gateway và service mesh.
- Egress và inter-zone/inter-region transfer, kể cả lưu lượng replication, telemetry và backup.
- Tác động của retry, payload lớn, websocket/streaming và kết nối idle.

Một hệ thống có đủ CPU có thể bị giới hạn bởi NAT port exhaustion hoặc giới hạn kết nối của API gateway. Việc scale out thêm instance đôi khi làm tăng số connection tới một thành phần giới hạn, khiến tình trạng tệ hơn.

### 5.3. Database và storage

Không chỉ tính dung lượng GB. Cần theo dõi:

| Chỉ số | Ý nghĩa | Hệ quả khi thiếu năng lực |
|---|---|---|
| IOPS | Số thao tác đọc/ghi trong một giây | I/O queue, latency truy vấn tăng |
| Throughput | Lượng dữ liệu truyền mỗi giây | Scan, backup hoặc workload lớn bị chậm |
| Connection count | Số kết nối database đồng thời | API timeout hoặc pool chờ |
| Transaction rate | Số transaction mỗi giây | Lock, contention và log pressure |
| Storage growth | Tốc độ tăng dữ liệu | Hết dung lượng hoặc tăng thời gian backup/restore |
| Replication lag | Độ trễ bản sao | Read replica cũ, DR có RPO xấu |
| Cache hit ratio | Tỷ lệ request được cache đáp ứng | Miss tăng khiến database bị dồn tải |
| Queue depth / disk latency | Hàng đợi I/O và thời gian phản hồi | Tác vụ ghi/đọc bị tồn đọng |

Tăng compute API có thể khiến database nhận nhiều request hơn và trở thành nút thắt. Capacity planning phải xem toàn bộ dependency graph và giới hạn của các dịch vụ dùng chung.

### 5.4. Queue và worker

Nếu một producer gửi công việc nhanh hơn tốc độ consumer xử lý, queue depth sẽ tăng. Một mô hình gần đúng:

~~~text
Tốc độ backlog tăng = Producer rate - Consumer processing rate

Thời gian xử lý backlog gần đúng
  = Số message tồn / Tốc độ xử lý ròng sau khi nguồn vào được kiểm soát
~~~

Ví dụ, producer phát 900 message/giây, worker xử lý 700 message/giây. Backlog tăng khoảng 200 message/giây. Sau 10 phút, có thể tồn gần 120.000 message nếu không có giới hạn hoặc thay đổi tải.

Autoscaling worker theo queue depth hoặc age of oldest message có thể giúp, nhưng phải tính giới hạn concurrency của database và API ngoài. Scale consumer không giới hạn có thể làm dependency quá tải, gây retry storm.

### 5.5. Mô hình capacity theo dependency

Một bảng capacity nên chỉ ra:

| Thành phần | Nhu cầu thiết kế | Năng lực đo/giới hạn | Điểm nghẽn | Dự phòng |
|---|---|---|---|---|
| API compute | Peak 500 RPS | 120 RPS/instance theo benchmark | CPU, p95 latency | N+1 và mất một zone |
| Database | 1.000 query/s, 150 write txn/s | Theo benchmark và quota DB | IOPS, connection, lock | HA, replica và backup |
| Worker | 800 message/s | 250 message/s/worker | CPU và downstream API | Queue buffer, worker pool |
| Cache | 20.000 ops/s | Theo instance/cluster benchmark | Memory, network, hot key | Replication và failover |
| NAT/egress | 4 Gbps và connection peak | Quota/throughput của dịch vụ | Port, bandwidth, quota | Nhiều gateway/đường ra nếu kiến trúc hỗ trợ |

Các số trên chỉ là ví dụ minh họa, không phải benchmark hay quota của nhà cung cấp.

## 6. Dự phòng tài nguyên và các mô hình N+1

### 6.1. Dự phòng theo đơn vị lỗi

Không nên chỉ hỏi “có bao nhiêu instance?”. Hãy hỏi cần chịu lỗi ở cấp nào:

- **Process/instance:** một tiến trình hoặc VM bị lỗi.
- **Node:** máy vật lý hoặc worker node gặp sự cố.
- **Rack/power/network segment:** nhóm tài nguyên cùng hạ tầng vật lý hoặc mạng.
- **Availability zone:** một failure domain trong region.
- **Region:** dịch vụ hoặc khu vực cloud bị gián đoạn.
- **Provider/dependency:** dịch vụ ngoài hoặc nhà cung cấp không hoạt động.

Hai instance trên cùng một node không tương đương hai instance tách node. Hai node trong cùng zone không đồng nghĩa chịu được lỗi zone. Phạm vi độc lập phải dựa vào topology và cam kết dịch vụ cụ thể.

### 6.2. N, N+1 và N+2

- **N:** số đơn vị năng lực tối thiểu để đáp ứng tải thiết kế khi mọi thành phần khỏe.
- **N+1:** thêm một đơn vị năng lực để chịu được lỗi một đơn vị trong phạm vi đã định nghĩa.
- **N+2:** thêm hai đơn vị để chịu được hai lỗi độc lập trong cùng phạm vi tính toán, hoặc đáp ứng quy tắc bảo trì và lỗi đồng thời.

N+1 không có nghĩa “hệ thống không thể hỏng”. Nó chỉ mô tả khả năng còn lại với giả định một phần tử lỗi. Nếu hai instance cùng nằm trong một zone và zone mất, chúng có thể mất đồng thời.

### 6.3. Active-active và active-passive

| Mô hình | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Active-active** | Nhiều đơn vị cùng phục vụ traffic | Dùng năng lực dự phòng ngay trong hoạt động bình thường; có thể phân phối gần người dùng | Phải xử lý state, đồng bộ, routing và lỗi đồng thời |
| **Active-passive** | Một bên hoạt động, bên kia chờ hoặc duy trì một phần | Dễ kiểm soát đường ghi trong một số kiến trúc | Tài nguyên chờ vẫn tốn phí; cần thời gian kích hoạt/failover và kiểm chứng dữ liệu |
| **Warm standby** | Bên dự phòng chạy ở công suất thấp hơn, có thể mở rộng khi cần | Cân bằng chi phí và thời gian phục hồi | Scale-up có thể chậm; capacity lúc failover chưa chắc sẵn sàng |
| **Pilot light** | Chỉ giữ các thành phần nền tảng tối thiểu, khởi chạy compute khi DR | Chi phí duy trì thấp hơn | RTO phụ thuộc nhiều bước triển khai, quota, khởi tạo và kiểm tra |
| **Backup/restore** | Khôi phục từ bản sao lưu vào môi trường mới | Bảo vệ khỏi một số dạng hỏng dữ liệu và sự cố lớn | RTO có thể dài; cần bảo đảm backup có thể đọc, key còn dùng và runbook hoạt động |

Không có mô hình dự phòng tốt nhất cho mọi workload. Cần xét mức độ quan trọng nghiệp vụ, RTO/RPO, trạng thái dữ liệu, khả năng vận hành và ngân sách.

### 6.4. Dự phòng compute nhưng quên dependency

Một cụm API có thể có N+1, nhưng vẫn thất bại khi:

- Database chỉ có một instance hoặc không còn connection.
- Broker, DNS, NAT, secret manager hoặc identity endpoint bị lỗi.
- Load balancer có quota thấp hơn lưu lượng failover.
- Region dự phòng chưa được cấp quota instance hoặc IP.
- Bản sao dữ liệu chưa đồng bộ theo RPO.
- Image/container chưa được kéo sẵn hoặc startup phụ thuộc artifact registry không truy cập được.
- Autoscaler và control plane bị gián đoạn đúng lúc cần mở rộng.

Phân tích dự phòng phải theo **dependency và failure mode**, không chỉ theo sơ đồ compute.

## 7. Scaling: tăng năng lực theo cách phù hợp

### 7.1. Vertical scaling (scale up)

Tăng CPU, RAM, IOPS hoặc kích thước một node/instance.

**Phù hợp:** workload khó chia nhỏ, database hoặc ứng dụng legacy, cần cách tăng năng lực đơn giản trong ngắn hạn.

**Giới hạn:** trần kích thước instance, downtime/restart khi đổi loại máy, chi phí tăng theo cấp, điểm lỗi đơn và một số workload không tận dụng thêm CPU.

### 7.2. Horizontal scaling (scale out)

Thêm nhiều instance/node/worker cùng loại để chia tải.

**Phù hợp:** API stateless, worker có thể phân chia công việc, workload có nhiều request độc lập.

**Giới hạn:** session/state phải được chia sẻ hoặc tái tạo; database và dependency có thể trở thành nút thắt; việc điều phối tăng phức tạp.

### 7.3. Autoscaling

Autoscaling điều chỉnh số lượng hoặc kích cỡ tài nguyên theo policy. Các cơ chế thường gặp:

| Kiểu scaling | Tín hiệu | Dùng khi |
|---|---|---|
| Target tracking | CPU, memory, request/instance, custom metric | Muốn giữ metric quanh một mục tiêu |
| Step scaling | Mức metric vượt ngưỡng theo các bậc | Phản ứng khác nhau khi tải tăng mạnh |
| Scheduled scaling | Lịch biết trước | Sự kiện, giờ làm việc, batch định kỳ |
| Predictive scaling | Mẫu tải lịch sử và dự báo | Tải có tính chu kỳ đủ ổn định |
| Queue-based scaling | Queue depth, message age, processing lag | Worker xử lý bất đồng bộ |
| Manual scaling | Quyết định vận hành | Sự kiện đặc biệt hoặc môi trường ít biến động |

Autoscaling thường có độ trễ: cần phát hiện tải, quyết định scale, cấp tài nguyên, tải image, khởi động ứng dụng, warm cache và vượt health check. Vì thế, không thể dựa hoàn toàn vào autoscaling để hấp thụ spike tức thời.

### 7.4. Min/max, warm pool và giới hạn mở rộng

Một policy phải xác định:

- **Minimum capacity:** mức tối thiểu để duy trì tính sẵn sàng và thời gian phản hồi.
- **Maximum capacity:** giới hạn chi phí, quota và bảo vệ dependency.
- **Desired capacity:** số tài nguyên hiện được điều khiển.
- **Cooldown/stabilization:** tránh scale lên xuống liên tục do metric dao động.
- **Warm pool/pre-warmed instances:** giảm thời gian khởi động cho workload nhạy thời gian.
- **Scale-in protection/draining:** không chấm dứt instance đang xử lý transaction hoặc job chưa an toàn.

Scale-out và scale-in cần đối xứng về an toàn: scale-out phải xác minh target khỏe trước khi nhận tải; scale-in phải drain kết nối, hoàn thành/đưa lại công việc và xử lý session hợp lệ.

## 8. Buffer capacity và nguyên tắc headroom

### 8.1. Vì sao không nên chạy liên tục ở sát giới hạn?

Khi utilization gần 100%, một lượng tải nhỏ tăng thêm có thể làm hàng đợi tăng, latency tăng và retry tạo thêm tải. Các request chậm giữ connection lâu hơn, khiến concurrency và số connection đồng thời tăng, tạo vòng khuếch đại quá tải.

**Headroom** giúp hệ thống hấp thụ đỉnh tải, sai số dự báo, scale-up delay, biến động độ trễ và lỗi một thành phần. Tuy nhiên, headroom không có một tỷ lệ chuẩn áp dụng chung; cần xác định qua load test, failure scenario và thời gian phản ứng của scaling.

### 8.2. Ví dụ tính headroom theo mức tải

Giả sử mỗi instance có năng lực hữu dụng 120 RPS và thiết kế muốn vận hành tối đa ở 70% mức đó trong điều kiện bình thường:

~~~text
Năng lực mục tiêu mỗi instance = 120 * 70% = 84 RPS
Peak demand = 500 RPS
Số instance theo mục tiêu utilization = ceil(500 / 84) = 6
~~~

Nếu cần một instance dự phòng độc lập, có thể cần ít nhất 7 instance; nếu cần chịu mất zone, tiếp tục tính theo số instance còn lại sau khi zone lỗi. 70% là giả định minh họa, chỉ có thể được chọn sau khi kiểm thử xác nhận độ trễ và độ ổn định.

### 8.3. Headroom cần gắn với thời gian scale

Nếu demand tăng 20% mỗi phút và autoscaler cần 3 phút để tạo instance mới, hệ thống phải có dư địa đủ hấp thụ tải tăng trong 3 phút đó. Tương tự, khi mất một zone, năng lực còn lại phải ngay lập tức tiếp nhận tải nếu RTO không cho phép chờ scale.

Kế hoạch có thể dùng:

- Provisioned baseline cho tải tối thiểu và yêu cầu sẵn sàng.
- Headroom đủ cho biến động thường gặp và thời gian scale.
- Pre-scale theo lịch khi đỉnh tải dự báo được.
- Rate limit/backpressure khi vượt max capacity.
- Shed load hoặc tắt tính năng không trọng yếu để bảo vệ luồng nghiệp vụ quan trọng.

## 9. Autoscaling không thay thế thiết kế tải

### 9.1. Điều kiện để scale-out có hiệu quả

Ứng dụng nên stateless hoặc quản lý state ở nơi phù hợp; các instance có thể khởi động độc lập, nhận cùng cấu hình an toàn, truy cập secret và dependency, vượt health check và phục vụ request nhất quán. Nếu startup cần migration dài hoặc khởi động cache rất chậm, scale-out có thể không kịp.

### 9.2. Chọn metric đúng

CPU dễ đo nhưng không phải lúc nào cũng là tín hiệu tốt. Với API I/O-bound, request per instance, active request, latency hoặc queue depth có thể phản ánh nhu cầu tốt hơn. Với worker, age of oldest message thường cho biết độ trễ nghiệp vụ hữu ích hơn CPU.

Không scale theo metric nhiễu hoặc trễ quá lâu. Metric phải liên quan đến bottleneck và được đánh giá cùng giới hạn dependency.

### 9.3. Backpressure, rate limit và load shedding

Khi tải vượt khả năng phục vụ:

- **Backpressure:** làm chậm producer hoặc từ chối nhận thêm công việc khi consumer không theo kịp.
- **Rate limiting:** giới hạn request theo user, tenant, token hoặc loại thao tác.
- **Queue buffering:** hấp thụ đỉnh ngắn hạn cho công việc có thể xử lý trễ.
- **Load shedding:** từ chối hoặc bỏ tác vụ không trọng yếu để giữ tài nguyên cho luồng ưu tiên.
- **Graceful degradation:** tắt tính năng phụ, cache kết quả, giảm độ chi tiết hoặc hoãn báo cáo.

Ví dụ, khi lượng tìm kiếm tăng đột biến, hệ thống có thể trả kết quả cache gần đây hoặc giới hạn filter nâng cao, nhưng vẫn ưu tiên luồng tạo/hủy booking. Quy tắc suy giảm phải được nghiệp vụ chấp nhận và giao diện cần thông báo chính xác.

## 10. Quota và giới hạn dịch vụ cloud

Dung lượng theo lý thuyết có thể lớn nhưng tài khoản cloud vẫn không scale được do quota:

- Số vCPU, instance, node hoặc địa chỉ IP trong region.
- Số load balancer, target group, NAT gateway, public IP và connection.
- API request rate, rate limit control plane, số database connection, storage throughput.
- Số volume, dung lượng, snapshot, queue, subscription hoặc concurrent function.
- Số network route, security rule, attachment và tài nguyên global.

**Service quota khác capacity benchmark.** Benchmark cho biết workload xử lý được bao nhiêu trong điều kiện thử; quota cho biết nền tảng cho phép tạo/dùng tối đa bao nhiêu tài nguyên. Cả hai phải đủ.

### 10.1. Lập kế hoạch quota cho tình huống lỗi

Nếu bình thường mỗi region dùng 20 instance, khi một region lỗi và toàn bộ traffic dồn sang region kia, region dự phòng có thể cần gấp đôi capacity. Phải yêu cầu quota dựa trên **mức failover**, không chỉ mức sử dụng trung bình. Cần kiểm tra quota theo tài khoản/project, region, loại instance và các quota phụ thuộc.

Đừng đợi tới khi xảy ra sự cố mới xin tăng quota; quy trình phê duyệt và thời gian áp dụng có thể kéo dài. Một số quota tăng tự động, số khác cần yêu cầu hoặc hỗ trợ nhà cung cấp.

### 10.2. Quota của dependency bên thứ ba

Payment API, email, SMS, bản đồ, identity provider và dịch vụ dữ liệu ngoài cũng có giới hạn. Tăng worker hoặc API instance có thể làm vượt rate limit của đối tác. Cần inventory những dependency này, giới hạn concurrency, backoff, circuit breaker và kế hoạch khi quota bên thứ ba hết.

## 11. Load testing và xác minh capacity

### 11.1. Các loại kiểm thử

| Kiểu kiểm thử | Mục tiêu | Cách thực hiện |
|---|---|---|
| **Load test** | Xác minh ở tải mục tiêu | Tăng dần tới tải dự kiến và quan sát latency/error |
| **Stress test** | Tìm giới hạn và chế độ thất bại | Tiếp tục tăng tải vượt mức thiết kế có kiểm soát |
| **Spike test** | Kiểm tra burst và khả năng scale nhanh | Tăng tải đột ngột, giữ ngắn, theo dõi thời gian phản ứng |
| **Soak/endurance test** | Phát hiện suy giảm khi chạy lâu | Giữ tải ổn định nhiều giờ, theo dõi leak, queue và storage |
| **Volume test** | Kiểm tra dữ liệu lớn | Dùng dung lượng/bản ghi gần thực tế |
| **Failover test** | Kiểm tra năng lực còn lại khi lỗi | Mất instance/node/zone hoặc giả lập dependency lỗi |
| **Recovery test** | Xác minh khả năng phục hồi sau gián đoạn | Phục hồi DB, worker, queue, cache và đo thời gian |

### 11.2. Dữ liệu thử phải đại diện

Benchmark với một bảng trống và cache nóng có thể cho kết quả tốt giả tạo. Nên mô phỏng kích thước payload, phân bố truy vấn, tỷ lệ cache hit/miss, số tenant, phân bố hot key, concurrency, dữ liệu lớn và hành vi retry gần thực tế.

Không chạy load test mạnh trực tiếp trên production hoặc dịch vụ bên thứ ba khi chưa có phê duyệt và kế hoạch bảo vệ. Dùng môi trường phù hợp, kiểm tra giới hạn nhà cung cấp và bảo đảm dữ liệu thử không chứa thông tin thật không cần thiết.

### 11.3. Theo dõi nhiều tầng trong cùng một lần thử

Tối thiểu theo dõi:

- Request rate, throughput hoàn thành, error rate và p50/p95/p99 latency.
- CPU, memory, throttling, restart, GC, thread và active request.
- Database CPU, IOPS, locks, connection pool, slow query, storage và replication lag.
- Queue depth, age of oldest message, consumer lag, retries và DLQ.
- Network throughput, retransmit, connection count, gateway/NAT saturation.
- Autoscaler decision, thời gian provisioning, boot, health check, warm-up và scale-in.
- Chi phí và lượng tài nguyên tạo ra trong test.

Nên tìm **bottleneck đầu tiên** và bottleneck tiếp theo sau khi đã xử lý nó. Tăng capacity API có thể phơi bày giới hạn DB; tăng DB có thể phơi bày giới hạn network hoặc lock contention.

## 12. Capacity khi rollout, bảo trì và khôi phục

### 12.1. Rolling deployment

Khi cập nhật ứng dụng theo kiểu rolling, một phần instance bị rút khỏi pool trong lúc phiên bản mới khởi động. Capacity còn lại phải đủ phục vụ tải trong thời gian rollout.

Ví dụ, cụm có 10 instance và rollout tối đa làm unavailable 2 instance. Nếu tải bình thường đã tiêu thụ gần 100% năng lực của 10 instance, rollout có thể gây quá tải. Cần tính surge capacity, maxUnavailable/maxSurge, startup time, readiness và drain duration.

### 12.2. Blue-green và canary

- **Blue-green:** duy trì hai nhóm triển khai, chuyển traffic giữa nhóm cũ và mới. Dễ rollback ở tầng traffic nhưng có thể phải trả chi phí compute gấp đôi tạm thời; database migration phải tương thích hai phiên bản.
- **Canary:** đưa một phần traffic sang phiên bản mới. Cần đủ capacity cho cả hai nhóm, quan sát lỗi theo phiên bản và tránh chia tải quá nhỏ làm tín hiệu khó đánh giá.
- **Rolling:** thay dần instance. Tiết kiệm tài nguyên dư hơn nhưng cần capacity còn lại và kiểm soát tương thích phiên bản.

### 12.3. Bảo trì và sự cố

Capacity phải bao gồm node bị drain, zone không khả dụng, nâng cấp managed service, backup, restore và tăng tải sau recovery. Tác vụ batch hoặc re-index có thể tranh CPU, I/O và connection với request online. Nên lập khung giờ, priority, throttling và giới hạn tài nguyên cho workload nền.

Khi recovery, queue backlog có thể tạo ra **đỉnh tải thứ hai**. Nếu bật tất cả worker ở tốc độ tối đa, hệ thống có thể làm database hoặc dịch vụ ngoài quá tải. Recovery plan nên có tốc độ replay/consumer ramp-up và điều kiện dừng.

## 13. Ví dụ hoàn chỉnh: lập dung lượng cho nền tảng đặt chỗ

Giả sử một nền tảng đặt chỗ có các mục tiêu minh họa:

- Peak traffic 500 request/giây.
- Một instance Booking API xử lý ổn định 120 RPS ở ngưỡng latency/error đã chốt.
- Cần chịu lỗi một availability zone.
- Ba zone được giả định có thể phân bố tài nguyên tương đương và load balancer có thể phân phối sang zone còn lại.
- Database là managed service có phương án HA đa zone, nhưng năng lực phải benchmark độc lập.

### 13.1. Tính compute API

Nếu chỉ xét tải khi tất cả instance khỏe và chia đều ba zone:

~~~text
N tối thiểu về throughput = ceil(500 / 120) = 5 instances
Phân bố cân bằng 3 zone: 2 + 2 + 1
~~~

Nếu mất zone chứa hai instance, còn ba instance:

~~~text
Capacity còn lại = 3 * 120 = 360 RPS
~~~

Không đủ 500 RPS. Nếu phân bố 3 + 3 + 3:

~~~text
Sau khi mất 1 zone: 2 zones * 3 instances = 6 instances
Capacity còn lại = 6 * 120 = 720 RPS
~~~

Phương án 9 instance đạt mô hình capacity đơn giản cho 500 RPS sau khi mất một zone. Tuy nhiên, nếu mục tiêu utilization 70% thì capacity thiết kế sau mất zone là:

~~~text
6 * 120 * 70% = 504 RPS
~~~

Chỉ nhỉnh hơn nhu cầu 500 RPS, nên sai số benchmark, chênh lệch request hoặc tải nền có thể làm mất headroom. Có thể cần tăng năng lực mỗi zone, dùng instance lớn hơn, thêm instance mỗi zone hoặc đặt mức peak/rate limit hợp lý.

### 13.2. Kiểm tra database

Không kết luận database chịu được 500 RPS chỉ từ số API instance. Phải đo tỷ lệ query/write của mỗi request. Ví dụ nếu một request trung bình tạo 3 query đọc và 1 transaction ghi:

~~~text
Database read QPS = 500 * 3 = 1.500
Database write txn/s = 500 * 1 = 500
~~~

Nếu chỉ 15% request ghi, write txn/s gần hơn với 75. Các con số phải phân biệt thao tác SQL, transaction và lượt ghi vật lý. Benchmark phải xác minh connection pooling, lock, IOPS, index và latency ở peak.

### 13.3. Kiểm tra worker và queue

Giả sử 20% request tạo một event. Với 500 RPS:

~~~text
Event rate = 500 * 20% = 100 events/s
~~~

Một worker xử lý bền vững 25 event/giây ở mức lỗi cho phép. Nếu cần giữ năng lực khi mất một worker:

~~~text
N = ceil(100 / 25) = 4
N+1 = 5 workers
~~~

Nếu phải chịu mất một zone, tiếp tục bố trí worker theo zone và tính năng lực còn lại, đồng thời kiểm tra broker, partition, consumer group và rate limit của downstream.

### 13.4. Bảng kết quả lập kế hoạch mẫu

| Thành phần | Peak/nhu cầu | Capacity giả định | Bố trí dự kiến | Kịch bản kiểm chứng |
|---|---|---|---|---|
| Booking API | 500 RPS | 120 RPS/instance theo benchmark | 3 instance/zone, 3 zone | Mất một zone, giữ 500 RPS, đo p95/p99 |
| Database | 1.500 read QPS; write theo tỷ lệ giao dịch | Cần benchmark | Managed HA, pool giới hạn | Tải DB, failover và connection recovery |
| Event worker | 100 event/s | 25 event/s/worker | Phân bố nhiều zone, có headroom | Mất worker/zone, backlog và replay |
| Broker | 100 event/s cộng burst/retry | Theo partition/quota benchmark | Replication theo SLA dịch vụ | Broker node lỗi, consumer lag và DLQ |
| Network/API egress | Theo payload và connection | Quota, throughput và NAT benchmark | Đủ gateway/đường ra theo topology | Peak connection, TLS và failover |

Tất cả số liệu là ví dụ. Trong dự án thực, capacity table cần ghi nguồn benchmark, phiên bản ứng dụng, loại instance, dữ liệu thử, timestamp, giới hạn dịch vụ và owner phê duyệt.

### 13.5. Ngân sách và chấp nhận rủi ro

Ba zone với chín instance có chi phí compute lớn hơn cấu hình năm instance. Nhưng năm instance không đạt yêu cầu mất zone trong giả định này. Nhóm có thể xem xét:

- Instance có năng lực đơn lớn hơn, nhưng phải benchmark và cân nhắc điểm lỗi/giới hạn scale up.
- Giảm nhu cầu peak bằng cache, tối ưu truy vấn hoặc tách workload.
- Giảm mức dịch vụ cho tác vụ phụ khi một zone mất.
- Dùng scheduled/predictive scale cho đỉnh biết trước, nhưng không dựa vào scale chậm để thay capacity tức thời.
- Điều chỉnh SLO hoặc yêu cầu chịu lỗi chỉ khi chủ sở hữu nghiệp vụ chấp thuận và ghi nhận rủi ro.

Không nên giảm tài nguyên dự phòng mà vẫn giữ nguyên lời hứa sẵn sàng. Mọi thay đổi phải cho thấy năng lực sau failure và chi phí theo điều kiện đó.

## 14. Quan sát và cảnh báo capacity

### 14.1. Bộ tín hiệu nên có

| Nhóm | Metric/cảnh báo | Mục đích |
|---|---|---|
| Compute | CPU, memory working set, throttling, restart, OOM | Phát hiện bão hòa hoặc thiếu bộ nhớ |
| Application | RPS, concurrency, latency p95/p99, error rate | Phát hiện tải vượt năng lực hữu dụng |
| Scaling | Desired/current/min/max, scale action, provision duration | Phát hiện autoscaler không đáp ứng kịp |
| Database | Connections, IOPS, lock, slow query, storage, lag | Phát hiện nút thắt dữ liệu |
| Queue | Depth, oldest-message age, consumer lag, retry/DLQ | Phát hiện backlog và recovery chậm |
| Network | Throughput, connection count, retransmit, gateway saturation | Phát hiện giới hạn đường truyền |
| Quota | Mức dùng/giới hạn, quota còn lại, yêu cầu tăng quota | Tránh fail scale do giới hạn tài khoản |
| Cost | Compute hours, egress, storage, idle/warm resources | Theo dõi chi phí dự phòng và tải biến động |

### 14.2. Đặt ngưỡng theo thời gian và xu hướng

Một cảnh báo “CPU > 80%” có thể quá nhạy hoặc quá muộn. Kết hợp:

- Ngưỡng utilization kéo dài trong một cửa sổ thời gian.
- Xu hướng tăng và thời gian dự kiến tới saturation.
- Tương quan với request rate, latency và error.
- Số instance hiện tại so với max capacity.
- Dung lượng còn lại khi giả lập mất một zone.

Ví dụ, cảnh báo khi queue age vượt 2 phút trong 5 phút liên tục có thể phản ánh độ trễ nghiệp vụ tốt hơn chỉ dựa vào CPU worker. Các ngưỡng phải căn cứ SLO và đặc tính xử lý thực tế.

### 14.3. Capacity review định kỳ

Một review hiệu quả nên gồm:

1. So sánh forecast với traffic, data growth và utilization thực.
2. Xem tải peak và các đỉnh bất thường trong giai đoạn gần nhất.
3. Kiểm tra sự kiện autoscaling, thời gian provisioning, quota và sự cố dependency.
4. Đánh giá capacity khi mất instance/zone/region và khi rollout.
5. Dự báo 3–12 tháng theo mức tăng trưởng và kế hoạch sản phẩm.
6. Cập nhật chi phí, cam kết ngân sách, reserved capacity/commitment nếu phù hợp và rủi ro còn lại.

## 15. Các sai lầm phổ biến

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng average load làm capacity mục tiêu | Quá tải ở peak và burst | Forecast theo peak, burst, duration và failure load |
| Dựa vào vCPU/RAM mà không benchmark | Dự báo sai năng lực thực | Benchmark với dữ liệu và SLO đại diện |
| Đạt N+1 instance nhưng không xét zone | Mất zone làm mất nhiều instance cùng lúc | Tính theo failure domain |
| Chỉ autoscale API | Database, broker hoặc quota thành bottleneck | Capacity plan xuyên dependency |
| Scale-out vô hạn | Retry storm và dependency quá tải | Max capacity, backpressure, rate limit, load shedding |
| Không tính startup time | Autoscaling phản ứng quá chậm với spike | Headroom, warm pool, scheduled scale |
| Không tính rollout/bảo trì | Deploy làm giảm capacity dưới peak | Surge capacity và maxUnavailable phù hợp |
| Quên quota region dự phòng | DR không thể khởi tạo đủ tài nguyên | Kiểm tra và xin quota trước |
| Chỉ nhìn CPU | Bỏ sót I/O, connection, memory và queue saturation | Dashboard đa tín hiệu và latency |
| Không diễn tập failover | Giả định dự phòng không được chứng minh | Game day, failover và recovery test |
| Dự phòng mọi thứ gấp đôi | Chi phí cao nhưng vẫn có điểm lỗi chung | Phân tích rủi ro và chọn mức redundancy theo mục tiêu |
| Không có scale-in protection/drain | Request hoặc job bị cắt giữa chừng | Graceful shutdown và queue visibility timeout |

## 16. Bài tập áp dụng

### Bài tập A — Tính số instance

Một API có peak demand 720 RPS. Load test chứng minh một instance xử lý bền vững 150 RPS ở p95 latency mục tiêu. Hệ thống cần chịu lỗi một instance.

**Câu hỏi:** Cần ít nhất bao nhiêu instance theo mô hình N+1?

**Gợi ý:** N = ceil(720/150) = 5. N+1 = 6 instance. Sau khi mất một instance, năm instance còn lại có năng lực 750 RPS theo benchmark. Cần tiếp tục xét zone distribution và các dependency khác.

### Bài tập B — Mất một zone

Một cụm gồm ba zone, mỗi zone có hai instance, mỗi instance đạt 100 RPS. Peak thiết kế là 450 RPS. Load balancer có thể chuyển traffic sang hai zone còn lại.

**Câu hỏi:** Mất một zone có đáp ứng peak không?

**Gợi ý:** Sau mất zone còn 4 instance, năng lực danh nghĩa 400 RPS, thấp hơn 450. Cần tăng instance mỗi zone hoặc cải thiện năng lực hữu dụng; sau đó kiểm chứng DB/network có nhận được tải dồn không.

### Bài tập C — Queue backlog tăng

Producer tạo 1.000 message/s. Mỗi worker xử lý được 180 message/s. Hiện có năm worker.

**Câu hỏi:** Backlog tăng hay giảm? Cần bao nhiêu worker để tốc độ xử lý bằng tốc độ tạo message, chưa xét dự phòng?

**Gợi ý:** Năng lực hiện tại 5 × 180 = 900 message/s, backlog tăng 100 message/s. Tối thiểu ceil(1.000/180) = 6 worker. Cần headroom và kiểm tra downstream trước khi scale tới sáu hoặc cao hơn.

### Bài tập D — Autoscaling không kịp

Một ứng dụng tăng từ 100 lên 1.000 RPS trong 15 giây. Autoscaler mất khoảng 90 giây để tạo instance và vượt readiness probe.

**Câu hỏi:** Tại sao chỉ tăng max instance không giải quyết vấn đề?

**Gợi ý:** Tài nguyên mới chưa sẵn sàng trong khoảng spike. Cần baseline/headroom, pre-warm hoặc scheduled capacity nếu sự kiện dự báo được, rate limit/queue để đệm, tối ưu startup và kiểm tra khả năng tăng tải của dependency.

### Bài tập E — DR không mở được compute

Primary region dùng 40 instance ở peak. Region DR chỉ được phê duyệt quota 20 instance và cơ chế autoscaling đặt max 30 instance.

**Câu hỏi:** Khi failover toàn bộ traffic, điểm nghẽn ở đâu và cần làm gì trước sự cố?

**Gợi ý:** DR chỉ có thể cấp tối đa 20 hoặc 30 theo quota thực tế, không đạt 40 instance cần thiết. Phải kiểm tra quota hiện tại theo region/type, tính lại tải tối ưu, xin nâng quota, giảm tải có kiểm soát hoặc điều chỉnh mục tiêu nghiệp vụ, rồi diễn tập failover.

## 17. Checklist trước khi phê duyệt capacity plan

- [ ] Đã mô hình hóa average, peak, burst, sustained, seasonal, growth và failure load.
- [ ] Các endpoint/workload được phân loại theo chi phí tài nguyên và mức quan trọng nghiệp vụ.
- [ ] Năng lực mỗi instance được đo bằng benchmark đại diện ở latency/error mục tiêu.
- [ ] Có dự báo CPU, memory, network, database, storage, IOPS, queue và connection.
- [ ] Số lượng tài nguyên được tính lại sau khi mất instance/node/zone/region theo failure domain cần chịu.
- [ ] Headroom được lựa chọn theo biến động tải, thời gian scale và mức rủi ro.
- [ ] Autoscaling có min/max, metric phù hợp, cooldown, warm-up, drain và scale-in behavior.
- [ ] Quota và rate limit của cloud provider cùng dependency bên thứ ba đã được kiểm tra ở mức failover.
- [ ] Rolling deployment, backup, batch, recovery và queue replay không làm cạn capacity của luồng quan trọng.
- [ ] Có load/stress/spike/soak/failover test và lưu benchmark, môi trường, phiên bản, kết quả.
- [ ] Có dashboard/cảnh báo cho saturation, latency, backlog, replication lag, scaling, quota và chi phí.
- [ ] Có cơ chế backpressure, rate limiting, load shedding và graceful degradation khi vượt max capacity.
- [ ] Owner, ngân sách, chu kỳ capacity review và quy trình cập nhật forecast đã được xác định.

**Điểm cốt lõi:** capacity planning trả lời **hệ thống cần bao nhiêu năng lực cho tải dự kiến**; redundancy trả lời **năng lực còn lại có đủ khi một phạm vi hạ tầng bị mất hay không**. Con số chỉ đáng tin khi được đo trên workload đại diện, tính theo failure domain và kiểm chứng bằng diễn tập. Kiến trúc cloud tốt giữ đủ headroom cho trải nghiệm và phục hồi, đồng thời giới hạn mở rộng bằng quota, kiểm soát tải, ngân sách và trách nhiệm vận hành rõ ràng.
