# Capacity planning và quản lý quota cho tải cao

Một hệ thống có thể chạy ổn định trong ngày thường nhưng thất bại khi chiến dịch bán hàng, đợt phát hành hoặc sự kiện bất ngờ làm lưu lượng tăng mạnh. Nguyên nhân có thể là thiếu CPU, bộ nhớ, kết nối database, địa chỉ IP, băng thông hoặc quota của một API. Capacity planning giúp dự báo tài nguyên cần thiết cho tải hiện tại và tương lai; quản lý quota bảo đảm project được phép tạo và sử dụng đủ tài nguyên khi nhu cầu tăng.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, bài học kết nối việc lập kế hoạch năng lực với cách vận hành project, IAM, VPC, Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Mục tiêu là dự báo tải có căn cứ, giữ đủ headroom, hiểu giới hạn của từng dịch vụ, theo dõi quota trước khi cạn và chuẩn bị phương án mở rộng hoặc suy giảm có kiểm soát.

Sau bài học, người học có thể:

- Đo nhu cầu tải bằng throughput, concurrency, latency, kích thước dữ liệu và mẫu tăng trưởng.
- Ước lượng CPU, memory, network, storage và connection capacity.
- Xác định headroom cho autoscaling, sự cố vùng và các đợt tải đột biến.
- Phân biệt quota, system limit, cấu hình giới hạn của dịch vụ và capacity vật lý.
- Theo dõi quota theo service, project và region; thiết lập cảnh báo và yêu cầu tăng quota.
- Lập kế hoạch tải cao cho Cloud Run, GKE, Compute Engine và Cloud SQL.
- Kiểm chứng kế hoạch bằng load test, SLO, error budget và kịch bản suy giảm có kiểm soát.

## 1. Capacity planning là gì?

Capacity planning là quá trình xác định hệ thống cần bao nhiêu tài nguyên để phục vụ một mức tải dự kiến với hiệu năng và độ tin cậy đã cam kết. Kế hoạch phải trả lời ba câu hỏi:

1. Tải hiện tại và tải tương lai có hình dạng như thế nào?
2. Tài nguyên nào sẽ trở thành nút thắt trước khi đạt tải mục tiêu?
3. Cần chuẩn bị, cấp phát hoặc dự phòng bao nhiêu năng lực để duy trì SLO khi tải tăng hoặc một thành phần gặp sự cố?

Capacity không chỉ là số lượng máy ảo. Một API có thể còn CPU nhưng hết connection pool tới Cloud SQL; GKE có thể còn quota CPU nhưng hết IP trong subnet; Cloud Run có thể tăng số instance nhưng dependency phía sau không chịu được số kết nối đồng thời. Năng lực của hệ thống bị giới hạn bởi thành phần hẹp nhất trên đường xử lý.

### 1.1. Các khái niệm tải cơ bản

| Chỉ số | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Throughput | Số request hoặc message xử lý trong một đơn vị thời gian | Hệ thống cần xử lý bao nhiêu request/giây? |
| Concurrency | Số operation đang được xử lý cùng lúc | Cần bao nhiêu request slot hoặc connection? |
| Latency | Thời gian hoàn thành một operation | p95/p99 có còn đạt SLO khi tải tăng? |
| Error rate | Tỷ lệ operation thất bại | Tải cao có làm tăng timeout hoặc lỗi quota? |
| Utilization | Mức sử dụng tài nguyên so với năng lực hiện có | CPU, memory, disk hoặc network đang gần bão hòa? |
| Queue depth/age | Số công việc chờ và thời gian chờ lâu nhất | Consumer có xử lý kịp tốc độ producer? |
| Growth rate | Tốc độ tăng nhu cầu theo thời gian | Khi nào cần thêm tài nguyên hoặc quota? |

Không dùng CPU utilization làm đại diện duy nhất cho capacity. Một hệ thống có thể nghẽn do lock database, thread pool, file descriptor, connection pool, quota API hoặc giới hạn số instance dù CPU vẫn thấp.

### 1.2. Phân biệt tải trung bình, tải đỉnh và burst

- **Average load** hữu ích để tính chi phí và mức sử dụng thông thường.
- **Peak load** là tải cao nhất trong một cửa sổ thời gian xác định, chẳng hạn đỉnh 5 phút hoặc 1 giờ.
- **Burst load** là mức tăng nhanh trong thời gian ngắn. Autoscaler có thể cần thời gian để khởi tạo instance hoặc node nên không phải lúc nào cũng đáp ứng ngay.
- **Seasonal load** là biến động theo giờ, ngày, mùa hoặc chiến dịch.
- **Failure load** là tải còn lại khi một vùng, node pool hoặc dependency bị lỗi và traffic được chuyển sang nơi khác.

Hãy đo theo nhiều cửa sổ thời gian. Một đỉnh 10 giây có thể bị làm mờ khi xem trung bình 1 giờ; ngược lại, một đợt tải kéo dài có thể làm đầy connection pool hoặc memory dù throughput không đạt đỉnh cực đại.

## 2. Thu thập dữ liệu trước khi dự báo

Một capacity plan đáng tin cậy bắt đầu từ dữ liệu thực tế. Thu thập ít nhất một chu kỳ đại diện cho hoạt động của hệ thống, bao gồm ngày thường, cuối tuần, giờ cao điểm và các chiến dịch nếu có.

### 2.1. Dữ liệu cần thu thập

- Request rate theo endpoint, tenant hoặc loại giao dịch.
- p50, p95 và p99 latency; error rate; timeout và retry count.
- CPU, memory, số instance/pod/node, thời gian scale-up và số lần restart.
- Database connections, query latency, lock, IOPS và storage growth.
- Network throughput, egress, số kết nối và kích thước payload.
- Queue depth, oldest message age, producer rate và consumer rate.
- Quota usage/limit theo service, project, region và dimension.
- Lịch phát hành, batch job, campaign, import/export và lịch tăng tải đã biết.

Phân biệt metric ở cấp service với metric ở cấp hạ tầng. CPU của node có thể thấp trong khi một pod bị giới hạn CPU; tổng memory cluster còn dư không có nghĩa pod có thể được scheduler đặt nếu node không có đủ tài nguyên liên tục.

### 2.2. Xác định workload model

Chia tải thành các nhóm có hành vi khác nhau:

| Workload | Đặc điểm | Cách lập kế hoạch |
|---|---|---|
| Interactive API | Nhạy với latency, có burst | Đo RPS, concurrency, p95/p99 và thời gian scale-up |
| Background worker | Có thể xử lý theo queue | Đo throughput mỗi worker, queue age và thời gian drain |
| Batch job | Tải lớn trong cửa sổ xác định | Ước lượng thời gian hoàn thành, CPU, memory và I/O |
| Data ingestion | Tải phụ thuộc tốc độ producer | Đo bytes/giây, message rate, buffer và retention |
| Database | Chia sẻ giữa nhiều ứng dụng | Đo connection, query mix, CPU, memory, IOPS và lock |

Không gộp tất cả workload thành một con số tổng nếu chúng dùng tài nguyên hoặc có SLO khác nhau. Một batch job có thể được phép chạy chậm hơn để nhường capacity cho API tương tác.

## 3. Ước lượng năng lực bằng mô hình đơn giản

Mô hình ban đầu giúp phát hiện mức thiếu hụt trước khi chạy thử tải. Các công thức sau là xấp xỉ; cần hiệu chỉnh bằng load test và số liệu thực tế.

### 3.1. Ước lượng concurrency bằng định luật Little

Định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số operation trung bình đang ở trong hệ thống.
- \(\lambda\): throughput trung bình, ví dụ request/giây.
- \(W\): thời gian trung bình một operation ở trong hệ thống, tính bằng giây.

Ví dụ, API nhận 250 request/giây và thời gian phản hồi trung bình là 0,8 giây:

\[
L = 250 \times 0.8 = 200
\]

Trung bình có khoảng 200 request đang xử lý hoặc chờ trong hệ thống. Nếu latency tăng lên 1,6 giây trong khi throughput không đổi, concurrency trung bình tăng lên khoảng 400. Điều này có thể làm tăng số thread, connection và memory cần thiết.

Little's Law dùng giá trị trung bình trên một hệ thống ổn định. Khi có burst, queue tăng nhanh hoặc request bị treo, hãy đo trực tiếp concurrency và queue age thay vì dựa duy nhất vào công thức.

### 3.2. Ước lượng CPU

Nếu biết lượng CPU time tiêu thụ trung bình cho một request, có thể ước lượng số vCPU:

\[
\text{vCPU cần thiết} \approx
\frac{\text{RPS} \times \text{CPU seconds/request}}
{\text{Target utilization}}
\]

Ví dụ:

- Peak throughput: 500 request/giây.
- CPU time trung bình: 0,04 core-second/request.
- Mục tiêu utilization khi tải đỉnh: 65%.

\[
\frac{500 \times 0.04}{0.65} \approx 30.8\ \text{vCPU}
\]

Kế hoạch sơ bộ cần khoảng 31 vCPU cho workload này, trước khi cộng dự phòng cho sự cố, tăng trưởng hoặc các job chạy đồng thời. CPU time/request phải được đo bằng profiling hoặc load test; không lấy latency tổng làm CPU time vì latency còn gồm network và thời gian chờ.

### 3.3. Ước lượng memory

Memory phụ thuộc vào baseline của process, số request đồng thời, kích thước payload, cache, buffer và cách runtime quản lý heap.

Một mô hình đơn giản:

\[
\text{Memory} \approx
\text{Baseline} +
(\text{Concurrency} \times \text{Memory/request})
\]

Ví dụ, process dùng 450 MiB ở trạng thái nền; mỗi request đang hoạt động giữ thêm trung bình 1,5 MiB; có 300 request đồng thời:

\[
450 + (300 \times 1.5) = 900\ \text{MiB}
\]

Đây là ước lượng để bắt đầu. Bộ nhớ thực tế có thể tăng không tuyến tính do cache, garbage collection, buffer và dữ liệu được giữ lâu. Đo working set và peak memory trong soak test để xác định giới hạn an toàn.

### 3.4. Ước lượng network và storage

Nếu mỗi request truyền trung bình 40 KB và hệ thống xử lý 500 request/giây, payload một chiều xấp xỉ:

\[
500 \times 40\ \text{KB} = 20\ \text{MB/s}
\]

Tương đương khoảng 160 Mbit/s trước khi tính overhead, response, TLS, retry, replication và traffic nền. Với dữ liệu hai chiều, cần tính riêng ingress và egress.

Storage nên tính theo dung lượng dữ liệu mới mỗi ngày, retention, index, replica, backup, temporary files và tốc độ tăng trưởng. Đừng chỉ dựa trên dung lượng hiện tại; cần dự báo thời điểm đạt ngưỡng disk và thời gian cần để mở rộng.

## 4. Headroom, dự phòng và khả năng chịu lỗi

**Headroom** là phần năng lực còn dư sau khi phục vụ tải dự kiến. Headroom giúp hệ thống hấp thụ burst, biến động của workload và thời gian autoscaler mở rộng.

Không có một tỷ lệ headroom phù hợp cho mọi hệ thống. Hãy chọn theo:

- Mức độ biến động của traffic.
- Thời gian khởi động instance, pod, node hoặc database.
- Mức độ quan trọng của SLO.
- Khả năng giảm tải hoặc xếp hàng công việc.
- Thời gian cần để xin quota hoặc mua/đặt trước capacity.
- Kịch bản mất một zone hoặc một dependency.

### 4.1. Dự phòng theo kịch bản lỗi

Kế hoạch production nên mô phỏng các tình huống:

1. Tải bình thường đạt đỉnh ngày thường.
2. Traffic tăng gấp đôi trong vài phút.
3. Một zone không khả dụng và traffic chuyển sang zone còn lại.
4. Một node pool hoặc một nhóm instance mất khả năng phục vụ.
5. Dependency database chậm khiến request tồn tại lâu hơn và concurrency tăng.
6. Một consumer ngừng hoạt động khiến queue backlog tăng.

Nếu hệ thống cần tiếp tục phục vụ khi mất một zone, tổng capacity còn lại ở các zone khác phải đủ đáp ứng tải mục tiêu. Cấu hình autoscaling chỉ đặt giới hạn tối đa cao không bảo đảm capacity đã sẵn sàng ở mọi zone.

### 4.2. Capacity reservation và quota là hai việc khác nhau

Quota cho biết project được phép yêu cầu tạo hoặc sử dụng bao nhiêu tài nguyên theo một dimension. Capacity vật lý là tài nguyên thực sự có sẵn trong hạ tầng tại một thời điểm và vị trí cụ thể.

Với Compute Engine, có quota CPU hoặc GPU không có nghĩa luôn có máy phù hợp để tạo ở một zone. Khi cần bảo đảm tài nguyên máy ảo theo vị trí và cấu hình, hãy đánh giá Compute Engine reservations hoặc lựa chọn capacity phù hợp. Reservation không thay thế quota; quota vẫn phải đủ để sử dụng tài nguyên đã đặt chỗ.

Với dịch vụ managed khác, capacity được quản lý theo cơ chế riêng của sản phẩm. Hãy kiểm tra cả quota, giới hạn cấu hình và khả năng phục vụ thực tế; không giả định tăng quota sẽ tự tạo thêm capacity vật lý.

## 5. Autoscaling và giới hạn ở từng dịch vụ GCP

Autoscaling điều chỉnh số lượng tài nguyên theo tín hiệu tải. Nó giúp giảm công việc vận hành thủ công nhưng không thay thế capacity planning. Cần đặt cả ngưỡng scale-up, giới hạn tối đa, tốc độ scale, capacity của dependency và quota nền tảng.

### 5.1. Cloud Run

- Dùng concurrency để quyết định số request có thể xử lý đồng thời trên một instance.
- Đặt maximum instances để bảo vệ dependency và kiểm soát chi phí.
- Cân nhắc minimum instances nếu cần giảm cold start hoặc có baseline traffic ổn định.
- Đo CPU/memory, request latency, instance count, startup latency và lỗi 429/5xx.
- Tính số instance cần thiết từ throughput, concurrency mục tiêu và hiệu năng mỗi instance dưới tải.
- Kiểm tra quota Cloud Run theo region và các giới hạn liên quan tới project.

Ví dụ: nếu một instance xử lý ổn định 40 request đồng thời và tải đỉnh cần 800 request đồng thời, mô hình sơ bộ cần 20 instance. Cần cộng headroom cho biến động, thời gian scale và instance không sẵn sàng; đồng thời kiểm tra dependency phía sau có chịu được 800 kết nối hay không.

Giới hạn maximum instances có thể được đặt ở cấp service/revision và quota của nền tảng cũng có thể áp dụng. Thay đổi cấu hình service không tự nâng quota project.

### 5.2. Google Kubernetes Engine

- Dùng Horizontal Pod Autoscaler (HPA) để tăng/giảm replica theo CPU, memory hoặc custom/external metric phù hợp.
- Dùng Vertical Pod Autoscaler (VPA) để quan sát hoặc đề xuất/cập nhật request và limit của container theo chính sách triển khai.
- Dùng Cluster Autoscaler để thêm/bớt node khi pod không thể được scheduler đặt do thiếu tài nguyên.
- Đặt resource requests sát nhu cầu thực tế; requests quá cao gây lãng phí và làm pod không được schedule, quá thấp khiến node bị overcommit.
- Kiểm tra quota Compute Engine cho CPU, GPU, disk, IP và tài nguyên node pool theo region/zone.
- Kiểm tra Pod IP range, secondary range và subnet capacity trước khi tăng số node hoặc pod.
- Dành capacity cho system pods, daemonsets, rolling update và workload quan trọng.

HPA có thể tăng số pod nhanh hơn Cluster Autoscaler tạo node mới. Trong khoảng thời gian chờ node, pod ở trạng thái Pending và request có thể bị chậm hoặc thất bại. Hãy kiểm thử thời gian scale toàn chuỗi từ pod đến node.

### 5.3. Compute Engine và Managed Instance Groups

- Dùng Managed Instance Group autoscaler dựa trên CPU, load balancing serving capacity hoặc custom metric phù hợp.
- Đặt minimum/maximum replicas theo tải, quota và giới hạn của ứng dụng.
- Chọn machine type theo profiling CPU, memory, network và disk.
- Đánh giá regional MIG nếu cần phân phối qua nhiều zone.
- Kiểm tra quota CPU, GPU, persistent disk, external IP và các tài nguyên phụ thuộc.
- Cân nhắc reservation khi cần bảo đảm capacity cho tải quan trọng.
- Kiểm tra thời gian boot, startup script, image pull, health check và warm-up.

Một MIG có maximum replica cao nhưng quota CPU không đủ sẽ không thể mở rộng tới mức dự kiến. Ngược lại, quota đủ nhưng zone hết capacity cũng có thể khiến instance không tạo được.

### 5.4. Cloud SQL và database

Database thường là dependency khó mở rộng ngang nhất. Kế hoạch cần xem:

- CPU, memory, storage, IOPS và throughput.
- Số kết nối đồng thời và connection pool ở từng service.
- Query latency, lock, transaction duration và replica lag.
- Khả năng read replica, HA/failover và thời gian chuyển đổi.
- Backup, point-in-time recovery và dung lượng cần cho restore.
- Giới hạn kết nối hoặc giới hạn sản phẩm theo loại máy và cấu hình database.

Không tăng số instance ứng dụng mà không tính connection pool. Ví dụ 30 instance, mỗi instance mở pool tối đa 80 kết nối, có thể tạo ra 2.400 kết nối tới database khi tất cả pool hoạt động tối đa. Giới hạn database có thể bị chạm trước khi CPU của ứng dụng đạt ngưỡng.

Sử dụng connection pooling, giới hạn số kết nối theo service, timeout và backpressure. Nếu database là nút thắt, cân nhắc tối ưu query, cache, read replica hoặc điều chỉnh cấu hình trước khi chỉ tăng replica ứng dụng.

## 6. Quota và system limits trong Google Cloud

Quota là giới hạn mức sử dụng tài nguyên hoặc API mà Google Cloud áp dụng cho một phạm vi tiêu thụ, thường theo project, service, region hoặc dimension cụ thể. Quota giúp kiểm soát mức sử dụng, bảo vệ hệ thống dùng chung và hạn chế lỗi do cấu hình hoặc chương trình tạo tài nguyên không kiểm soát.

### 6.1. Các nhóm quota thường gặp

| Nhóm | Ví dụ | Đơn vị/phạm vi thường gặp |
|---|---|---|
| Allocation quota | Số vCPU, GPU, persistent disk hoặc IP được cấp phát | Số lượng tài nguyên, thường theo region hoặc project |
| Rate quota | Số request API trong một khoảng thời gian | Request/giây, request/phút hoặc đơn vị thời gian khác |
| Concurrent quota | Số operation hoặc request đang hoạt động | Số operation đồng thời |
| Service-specific quota | Giới hạn riêng của Cloud Run, GKE, BigQuery hoặc dịch vụ khác | Phụ thuộc dịch vụ và dimension |

Tên nhóm và cách đo có thể khác theo sản phẩm. Hãy đọc mô tả quota cụ thể trong trang Quotas & System Limits của service đang sử dụng.

### 6.2. Quota, system limit và cấu hình service

| Khái niệm | Ý nghĩa | Cách xử lý |
|---|---|---|
| Quota | Hạn mức sử dụng có thể được điều chỉnh trong một số trường hợp | Theo dõi usage, yêu cầu tăng hoặc phân bổ lại |
| System limit | Giới hạn cố định hoặc giới hạn sản phẩm không thể tùy ý tăng | Thiết kế lại workload hoặc chọn dịch vụ/cấu hình khác |
| Service configuration limit | Giá trị do người vận hành đặt, ví dụ max instances hoặc max replicas | Điều chỉnh cấu hình sau khi đánh giá dependency và quota |
| Physical capacity | Năng lực phần cứng thực tế tại zone/region | Reservation, chọn vùng/machine type khác hoặc phối hợp nhà cung cấp |

Một quota có thể được tăng nhưng giới hạn sản phẩm vẫn tồn tại. Một cấu hình max instances có thể được nâng nhưng quota project hoặc capacity của dependency chưa đủ. Khi gặp lỗi resource exhausted, cần xác định đúng loại giới hạn trước khi xử lý.

### 6.3. Quota theo project và region

Nhiều quota được tính riêng theo project và region. Một project có thể còn quota ở region A nhưng đã hết quota ở region B. Một số quota API được tính ở cấp project hoặc theo consumer; một số quota khác có dimension theo location, user hoặc method.

Khi đọc quota, ghi lại:

- Service name và quota metric.
- Limit name hoặc dimension cụ thể.
- Project/consumer đang chịu quota.
- Region/location nếu quota có phân vùng.
- Usage hiện tại, limit và thời điểm reset nếu là quota theo chu kỳ.
- Đơn vị và cách tính quota.

Đừng cộng quota của nhiều project như thể chúng là một pool chung. Nếu ứng dụng được triển khai ở nhiều project, mỗi project cần được kiểm tra theo đúng consumer và tài nguyên thực tế.

## 7. Kiểm tra và theo dõi quota

### 7.1. Dùng Cloud Console

Trong Google Cloud Console:

1. Chọn đúng project.
2. Mở trang **Quotas & System Limits** trong phần IAM & Admin hoặc trang quota tương ứng của dịch vụ.
3. Lọc theo service, quota name, metric, region hoặc trạng thái.
4. Xem usage, limit, phần trăm sử dụng và khả năng chỉnh sửa.
5. Mở quota cụ thể để xem dimension và điều kiện yêu cầu tăng.
6. Ghi nhận quota có liên quan tới capacity plan và người chịu trách nhiệm.

Giao diện có thể thay đổi theo dịch vụ và phiên bản Console. Một số quota được quản lý ở trang riêng của sản phẩm hoặc cần gửi yêu cầu qua Support.

### 7.2. Theo dõi quota bằng Cloud Monitoring

Cloud Monitoring cung cấp quota metrics cho nhiều dịch vụ. Các metric thường gặp trong nhóm Service Runtime gồm:

- **serviceruntime.googleapis.com/quota/allocation/usage**
- **serviceruntime.googleapis.com/quota/limit**
- **serviceruntime.googleapis.com/quota/rate/net_usage**
- **serviceruntime.googleapis.com/quota/rate/limit**

Các metric và label có sẵn phụ thuộc service và loại quota. Hãy kiểm tra metric descriptor trong project thay vì giả định mọi quota đều phát ra cùng một bộ metric.

Khi xây dashboard, hiển thị usage cùng limit theo đúng dimension. Một biểu đồ chỉ có usage mà không có limit sẽ khó cho biết còn bao nhiêu headroom. Với quota theo region, tách series theo location để tránh tổng hợp che mất một region đã gần cạn.

### 7.3. Đặt cảnh báo trước khi cạn quota

Ngưỡng cảnh báo nên dựa trên tốc độ tăng usage và thời gian cần để xử lý tăng quota. Ví dụ:

| Mức cảnh báo | Hành động gợi ý |
|---|---|
| Theo dõi | Usage bắt đầu tăng nhanh hơn baseline; kiểm tra nguyên nhân |
| Cảnh báo sớm | Còn đủ thời gian để dự báo ngày/giờ chạm limit; mở kế hoạch tăng quota |
| Cảnh báo khẩn | Headroom thấp hơn mức dự phòng vận hành; chuẩn bị giảm tải hoặc chuyển traffic |
| Exhausted | Request tạo/sử dụng tài nguyên đã bị từ chối; kích hoạt playbook sự cố |

Không dùng một ngưỡng phần trăm cho mọi quota. Với quota tăng chậm nhưng quy trình xin tăng mất nhiều ngày, cảnh báo ở mức thấp hơn. Với quota rate reset mỗi phút, cần đánh giá theo burst và thời gian reset.

Có thể ước lượng thời điểm cạn quota:

\[
\text{Time to exhaustion} \approx
\frac{\text{Limit} - \text{Current usage}}
{\text{Net usage growth per unit time}}
\]

Nếu usage biến động theo mùa hoặc burst, dùng forecast theo chu kỳ và percentile thay vì ngoại suy tuyến tính từ một khoảng ngắn.

## 8. Quy trình yêu cầu tăng quota

Không chờ đến khi production bị từ chối tạo tài nguyên mới bắt đầu yêu cầu tăng quota. Hãy chuẩn bị dựa trên forecast, load test và lịch phát hành.

Quy trình khuyến nghị:

1. Xác định quota metric, limit name, service, project và region cần tăng.
2. Xác nhận đây thực sự là quota có thể điều chỉnh, không phải system limit hoặc thiếu physical capacity.
3. Đo usage hiện tại, peak usage và tốc độ tăng.
4. Tính nhu cầu mục tiêu gồm tải dự báo, headroom, failover và growth horizon.
5. Kiểm tra các quota liên quan; tăng một quota đơn lẻ có thể chưa đủ nếu workload cần thêm IP, disk hoặc CPU cùng lúc.
6. Gửi yêu cầu qua trang Quotas & System Limits hoặc quy trình của dịch vụ/Cloud Customer Care.
7. Cung cấp lý do nghiệp vụ, project, region, limit hiện tại, limit đề xuất, tải dự kiến và thời điểm cần.
8. Theo dõi trạng thái yêu cầu, xác minh quota mới sau khi được chấp thuận và cập nhật capacity plan.

Yêu cầu tăng quota có thể cần thời gian đánh giá và không được chấp thuận tự động. Một số quota không thể tăng hoặc cần điều kiện bổ sung. Tăng quota cũng có thể làm tăng khả năng phát sinh chi phí; cần phối hợp với budget owner.

### 8.1. Ví dụ nội dung yêu cầu

~~~text
Service: Compute Engine API
Project: production-project
Region: asia-southeast1
Quota: Regional CPUs
Current limit: 200
Requested limit: 320

Reason:
The service will add two production node pools and increase the
regional managed instance group capacity for a planned traffic event.
Load testing indicates a peak requirement of 220 vCPUs. The requested
limit includes failover headroom and the next planned growth period.
The workload, rollout window, monitoring plan and rollback procedure
have been reviewed by the service owner.
~~~

Đây là mẫu minh họa; thay quota name, số liệu, region và lý do bằng dữ liệu đã đo. Không yêu cầu limit quá lớn nếu chưa có mô hình sử dụng và kế hoạch chi phí.

## 9. Load testing để xác nhận capacity

Mô hình tính toán cần được kiểm chứng bằng thử tải. Môi trường thử nên gần production về machine type, cấu hình runtime, dữ liệu, network path, database, autoscaling và quota.

### 9.1. Các loại thử tải

| Loại test | Mục đích | Điều cần quan sát |
|---|---|---|
| Baseline | Đo hiệu năng ở tải thông thường | Latency, CPU, memory và error rate |
| Load test | Kiểm tra tải mục tiêu dự kiến | SLO, throughput, autoscaling và quota |
| Stress test | Tăng tải vượt mức thiết kế để tìm điểm gãy | Saturation, queue, lỗi và hành vi khi quá tải |
| Spike test | Tăng tải đột ngột | Scale-up delay, cold start và burst quota |
| Soak test | Duy trì tải trong thời gian dài | Memory leak, connection leak, queue growth |
| Failover test | Mô phỏng mất zone/node/dependency | Capacity còn lại và khả năng duy trì SLO |

### 9.2. Quy trình thử tải

1. Xác định mục tiêu: peak RPS, concurrency, latency percentile, error rate và thời gian chạy.
2. Chuẩn bị dữ liệu và workload mix đại diện; tránh chỉ gửi một endpoint đơn giản.
3. Xác nhận quota, budget, giới hạn dịch vụ và thông báo cho các nhóm liên quan.
4. Tăng tải theo từng bậc, giữ đủ thời gian để autoscaler ổn định.
5. Ghi lại CPU, memory, connection, queue, network, storage, quota usage và số instance/node.
6. Tăng đến khi đạt tải mục tiêu, sau đó thử burst hoặc stress trong giới hạn an toàn.
7. Phân tích bottleneck và điều chỉnh capacity model.
8. Lặp lại sau khi thay đổi cấu hình quan trọng.

Không chạy stress test trên production khi chưa có phê duyệt vận hành và kế hoạch bảo vệ dependency. Một load test có thể làm cạn quota dùng chung, tăng chi phí hoặc ảnh hưởng khách hàng khác trong cùng project.

### 9.3. Tiêu chí pass

Một bài load test đạt yêu cầu khi:

- Throughput mục tiêu được duy trì trong thời gian kiểm thử.
- p95/p99 latency và error rate nằm trong SLO.
- Không có quota exhaustion ngoài dự kiến.
- CPU, memory, connection và queue vẫn có headroom theo thiết kế.
- Autoscaler mở rộng và thu hẹp trong thời gian chấp nhận được.
- Database và dependency không trở thành nút thắt.
- Hệ thống phục hồi sau khi giảm tải; queue backlog được drain và resource được scale-in an toàn.

## 10. Bảo vệ hệ thống khi đạt giới hạn

Capacity plan phải xác định cách hệ thống phản ứng khi không thể mở rộng thêm. Mục tiêu là giữ chức năng quan trọng hoạt động và tránh sự cố lan truyền.

### 10.1. Backpressure và queue

- Giới hạn số request đồng thời để bảo vệ dependency.
- Dùng queue cho công việc có thể xử lý bất đồng bộ.
- Đặt giới hạn backlog và oldest message age; cảnh báo trước khi queue tăng mất kiểm soát.
- Điều chỉnh số consumer theo throughput thực tế và quota downstream.
- Trả lỗi có thể retry với backoff và jitter; tránh retry storm.
- Từ chối sớm request vượt khả năng thay vì giữ connection vô thời hạn.

### 10.2. Graceful degradation

Khi capacity khan hiếm:

- Ưu tiên luồng nghiệp vụ cốt lõi và tenant/service tier quan trọng.
- Tắt hoặc trì hoãn tính năng phụ như báo cáo nặng, recommendation hoặc tác vụ nền không khẩn cấp.
- Dùng cache cho dữ liệu đọc phù hợp và kiểm soát cache stampede.
- Hạn chế batch job và non-critical traffic trong khung giờ cao điểm.
- Dùng circuit breaker để ngăn dependency lỗi kéo sập toàn bộ service.
- Thông báo lỗi có thể retry và cung cấp retry-after nếu phù hợp.

### 10.3. Kiểm soát retry và timeout

Retry làm tăng tải khi dependency đang suy giảm. Đặt timeout theo ngân sách latency của request, giới hạn số lần retry, dùng exponential backoff và jitter. Chỉ retry thao tác an toàn hoặc có idempotency key. Không retry mọi lỗi 4xx hoặc lỗi quota theo vòng lặp nhanh.

## 11. Quản trị quota và capacity theo project

Quota có thể bị tiêu thụ bởi nhiều nhóm và nhiều workload trong cùng project. Nếu không có quản trị, một môi trường thử nghiệm hoặc batch job có thể làm production thiếu hạn mức.

Các biện pháp:

- Tách project production, staging và development theo ranh giới quản trị phù hợp.
- Đặt owner cho từng quota quan trọng và ghi rõ workload tiêu thụ.
- Gắn label và inventory để truy vết tài nguyên, môi trường và chi phí.
- Định kỳ rà soát quota không dùng, resource tồn tại lâu dài và cấu hình autoscaling tối đa.
- Lập capacity calendar cho campaign, migration, batch và đợt phát hành.
- Có quy trình duyệt cho workload đột biến hoặc tạo nhiều tài nguyên.
- Kiểm tra quota liên vùng nếu dùng active-active hoặc failover.
- Đánh giá tác động chi phí khi tăng quota và mở rộng autoscaling.

Tách project có thể cô lập quota cho một số dịch vụ và workload, nhưng không phải mọi quota đều có cùng phạm vi. Hãy xác minh dimension của từng quota trước khi quyết định kiến trúc phân tách.

## 12. Ví dụ thực hành: chuẩn bị API cho chiến dịch tải cao

Một API thương mại điện tử hiện xử lý 180 request/giây ở giờ cao điểm. Chiến dịch sắp tới dự kiến đạt 450 request/giây trong 30 phút, với khả năng burst ngắn lên 600 request/giây.

Số liệu load test hiện tại:

- CPU time: 0,035 core-second/request.
- Latency trung bình: 0,45 giây.
- Mục tiêu CPU utilization khi tải cao: 65%.
- Concurrency mục tiêu tại 450 RPS: khoảng 450 × 0,45 = 203 request.

Ước lượng CPU:

\[
\frac{450 \times 0.035}{0.65} \approx 24.2\ \text{vCPU}
\]

Nếu dự phòng một zone hoặc node group có thể mất 25% capacity, kế hoạch phải kiểm tra năng lực còn lại vẫn đáp ứng được tải quan trọng. Có thể cần đặt capacity danh nghĩa cao hơn 24,2 vCPU và xác nhận autoscaler/placement có thể cung cấp phần đó trong thời gian cần thiết.

Các bước chuẩn bị:

1. Chạy load test ở 450 RPS trong ít nhất một cửa sổ đại diện và spike test lên 600 RPS.
2. Xác định số Cloud Run instances hoặc GKE pods/node cần thiết dựa trên concurrency và throughput đo được.
3. Kiểm tra quota Cloud Run/GKE/Compute Engine theo region và project.
4. Kiểm tra Cloud SQL connections, CPU, storage và query latency ở tải tương ứng.
5. Đặt max instances/replicas có headroom nhưng không vượt khả năng database.
6. Thiết lập quota alerts và dashboard theo dõi usage/limit.
7. Chuẩn bị cache, queue, rate limit và chế độ tắt tính năng phụ.
8. Xác nhận budget và người trực trong thời gian chiến dịch.

Nếu database chỉ chịu được 300 request/giây, tăng Cloud Run instances lên mức phục vụ 600 RPS có thể làm database quá tải. Khi đó cần giảm số kết nối, cache, tối ưu query hoặc xử lý bất đồng bộ trước khi tăng capacity frontend.

## 13. Checklist capacity và quota

### Dự báo nhu cầu

- [ ] Có số liệu baseline, peak, burst và seasonal load.
- [ ] Đã đo throughput, concurrency, latency percentile và error rate.
- [ ] Đã xác định workload mix và dependency quan trọng.
- [ ] Có forecast tăng trưởng theo mốc thời gian cụ thể.

### Năng lực tài nguyên

- [ ] CPU, memory, network, storage và connection capacity đã được ước lượng.
- [ ] Có headroom cho autoscaling và failure scenario.
- [ ] Đã tính thời gian khởi động instance/node và warm-up.
- [ ] Đã kiểm tra queue, backpressure và khả năng drain backlog.
- [ ] Database và dependency downstream có capacity phù hợp.

### Quota

- [ ] Đã lập danh sách quota theo service, project, region và dimension.
- [ ] Đã phân biệt quota, system limit, service configuration và physical capacity.
- [ ] Usage và limit được giám sát cùng nhau.
- [ ] Có cảnh báo đủ sớm theo thời gian xử lý yêu cầu tăng quota.
- [ ] Quota liên quan được tăng đồng bộ, không chỉ một metric riêng lẻ.
- [ ] Đã xác minh quota mới và cập nhật capacity plan sau khi được duyệt.

### Kiểm thử và vận hành

- [ ] Có baseline, load, spike, stress, soak hoặc failover test phù hợp.
- [ ] Load test đạt SLO và không gây quota exhaustion ngoài dự kiến.
- [ ] Có playbook graceful degradation và retry/backoff.
- [ ] Có owner, lịch trực và kế hoạch rollback cho đợt tải cao.
- [ ] Budget và chi phí autoscaling/egress/storage đã được xem xét.

## 14. Sai lầm thường gặp

**Dùng average load để thiết kế peak capacity.** Trung bình che mất burst và giờ cao điểm. Hãy dùng percentile, peak theo cửa sổ thời gian và workload calendar.

**Nâng quota rồi cho rằng hệ thống đã đủ capacity.** Quota chỉ cho phép sử dụng tài nguyên đến một hạn mức; capacity vật lý và giới hạn dịch vụ vẫn có thể ngăn workload mở rộng.

**Chỉ kiểm tra quota CPU.** Workload có thể cần disk, GPU, IP, forwarding rule, API request hoặc connection quota cùng lúc. Lập danh sách tất cả dependency.

**Tăng max instances mà không kiểm tra database.** Frontend scale nhanh có thể tạo quá nhiều kết nối và làm dependency phía sau sụp đổ.

**Đặt autoscaling max quá thấp.** Hệ thống chạm max replicas dù quota còn dư. Ngược lại, đặt max quá cao có thể tăng chi phí và tạo tải không kiểm soát lên dependency.

**Không tính thời gian scale-up.** Autoscaler cần thời gian tạo instance/node và khởi động ứng dụng. Burst nhanh có thể đến trước capacity mới.

**Không thử failover.** Năng lực tổng toàn hệ thống có thể đủ nhưng capacity còn lại sau khi mất một zone lại không đủ.

**Xin tăng quota quá muộn.** Quy trình xét duyệt có thể mất thời gian hoặc cần thêm thông tin. Dùng forecast và time-to-exhaustion để mở yêu cầu sớm.

**Không tính retry vào tải.** Retry storm làm request rate thực tế cao hơn traffic người dùng. Dùng timeout, backoff, jitter và idempotency.

## 15. Tài liệu tham khảo chính thức

- [Google Cloud quotas overview](https://cloud.google.com/docs/quotas/overview)
- [View and manage quotas](https://cloud.google.com/docs/quotas/view-manage)
- [Request a quota adjustment](https://cloud.google.com/docs/quotas/help/request_increase)
- [Cloud Monitoring quota metrics](https://cloud.google.com/monitoring/quotas)
- [Compute Engine quotas](https://cloud.google.com/compute/quotas)
- [Compute Engine reservations](https://cloud.google.com/compute/docs/instances/reserving-zonal-resources)
- [Cloud Run autoscaling](https://cloud.google.com/run/docs/about-instance-autoscaling)
- [GKE cluster autoscaler](https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [Cloud SQL performance overview](https://cloud.google.com/sql/docs/postgres/monitor-instance)
- [Site Reliability Engineering: Managing Load](https://sre.google/sre-book/handling-overload/)

Capacity planning là hoạt động lặp lại, không phải phép tính một lần trước ngày phát hành. Sau mỗi đợt tải cao, hãy so sánh forecast với usage thực tế, cập nhật mô hình, rà soát quota và điều chỉnh autoscaling. Khi có số liệu, headroom, quota và playbook rõ ràng, nhóm có thể mở rộng đúng thành phần, giữ SLO và tránh chi phí hoặc rủi ro do cấp phát thiếu hay thừa.
