# Chẩn đoán nghẽn CPU, bộ nhớ, đĩa và mạng

## 1. Mục tiêu và bối cảnh

Một ứng dụng triển khai trên Microsoft Azure có thể phản hồi chậm dù trạng thái dịch vụ vẫn là **Running** và các phép kiểm tra sức khỏe vẫn trả về HTTP 200. Nguyên nhân có thể nằm ở CPU đang xử lý hết công suất, bộ nhớ bị áp lực, đĩa không phục vụ kịp các thao tác I/O, hoặc mạng và các phụ thuộc qua mạng có độ trễ cao. Đôi khi nhiều nút thắt xuất hiện đồng thời: truy vấn cơ sở dữ liệu tạo nhiều I/O, I/O chậm kéo dài thời gian giữ kết nối, rồi số yêu cầu đang chờ tăng lên.

Bài học thuộc chương **Hiệu năng và vận hành** trong lộ trình tìm hiểu hệ sinh thái Azure: từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage và dữ liệu đến triển khai, giám sát, bảo vệ và kiểm soát chi phí. Trọng tâm là chẩn đoán có chứng cứ trên **Azure Virtual Machines (VM)**, đồng thời chỉ ra cách áp dụng tư duy tương tự cho Azure App Service, Azure Kubernetes Service (AKS) và dịch vụ dữ liệu được quản lý.

Sau bài này, người học có thể:

1. Phân biệt **triệu chứng** (độ trễ, timeout, lỗi) với **tài nguyên bị bão hòa** và **nguyên nhân gốc**.
2. Xây dựng chuỗi bằng chứng từ Azure Monitor, Application Insights, chỉ số hệ điều hành và cấu hình tài nguyên.
3. Nhận diện dấu hiệu đặc trưng của nghẽn CPU, bộ nhớ, đĩa và mạng; tránh kết luận từ một chỉ số đơn lẻ.
4. Đề xuất thay đổi có thể kiểm chứng, đo lại trước/sau và cân nhắc giới hạn SKU cùng chi phí Azure.

**Tình huống xuyên suốt:** một API chạy trên VM trong virtual network (VNet), kết nối đến Azure SQL Database và một dịch vụ bên ngoài qua HTTPS. Người dùng báo thời gian phản hồi tăng mạnh vào giờ cao điểm. Nhiệm vụ vận hành là xác định lớp nào làm chậm luồng yêu cầu và bằng chứng nào xác nhận điều đó.

## 2. Hiểu đúng về “nghẽn” trong hệ thống

Tài nguyên được coi là nút thắt khi nhu cầu sử dụng vượt khả năng phục vụ trong một khoảng thời gian và gây ra hàng đợi, độ trễ hoặc lỗi. Mức sử dụng cao **chưa đủ** để khẳng định có nghẽn. Ví dụ, CPU ở 90% khi xử lý một tác vụ nền có thể bình thường nếu các yêu cầu tương tác vẫn đáp ứng SLO. Ngược lại, CPU trung bình chỉ 40% vẫn có thể che giấu một tiến trình đơn luồng dùng hết một lõi, hoặc container bị giới hạn CPU.

Bốn nhóm tín hiệu cần quan sát cùng nhau:

| Nhóm tín hiệu | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Latency** (độ trễ) | Khách hàng phải đợi bao lâu? | P50/P95/P99 của HTTP request; thời gian gọi SQL |
| **Traffic** (lưu lượng) | Hệ thống đang nhận và xử lý bao nhiêu công việc? | Requests/giây, truy vấn/giây, MB/giây |
| **Errors** (lỗi) | Công việc nào không hoàn tất? | HTTP 5xx, timeout, lỗi kết nối, OOM kill |
| **Saturation** (bão hòa) | Tài nguyên/hàng đợi đã gần giới hạn chưa? | CPU, swap, disk latency, IOPS, retransmission |

**P95** là mức thời gian mà khoảng 95% lượt yêu cầu có độ trễ nhỏ hơn hoặc bằng. P95/P99 giúp nhìn thấy các yêu cầu chậm mà số trung bình dễ che khuất. Khi tăng tải, hàng đợi thường tăng nhanh trước khi hệ thống phát sinh lỗi rõ rệt.

Để kết luận nguyên nhân, cần chứng minh một chuỗi hợp lý: **tải hoặc thay đổi cụ thể → chỉ số bão hòa/hàng đợi → tăng thời gian chờ trong luồng request → triệu chứng người dùng**. Nếu không tìm được mối liên hệ về thời gian và phạm vi, đó mới là giả thuyết.

## 3. Thu thập bằng chứng đúng lớp trên Azure

### 3.1. Xác định nguồn đo

| Lớp quan sát | Dữ liệu hữu ích | Công cụ Azure | Lưu ý |
|---|---|---|---|
| Trải nghiệm ứng dụng | Request rate, P95/P99, lỗi, dependency call | Azure Monitor Application Insights; distributed tracing | Cần bật instrumentation và sampling phù hợp |
| Azure VM / tài nguyên | Percentage CPU, disk operations/bytes, network traffic, các metric bão hòa có hỗ trợ | Azure Monitor Metrics, Metrics Explorer, alerts | Tên và danh sách metric phụ thuộc loại tài nguyên/SKU |
| Bên trong hệ điều hành | Bộ nhớ còn khả dụng, paging/swap, tiến trình dùng CPU, disk latency, TCP retransmit | Azure Monitor Agent (AMA) với Data Collection Rule (DCR); VM insights; công cụ Linux/Windows | Nhiều guest metric không tự có chỉ vì đã tạo VM |
| Cấu hình và giới hạn | VM size, disk SKU, số/loại disk, NIC, vùng triển khai, giới hạn dịch vụ | Azure Portal, Azure CLI, tài liệu giới hạn SKU | Giới hạn thực tế có thể đến từ cả VM lẫn disk |
| Hệ thống liên quan | DB CPU/IO, connection pool, downstream latency, DNS | Azure SQL metrics, Application Insights dependencies, Connection Monitor | “Request chậm” không nhất thiết do VM tiếp nhận request |

**Phân biệt platform metric và guest metric:** phần lớn metric nền tảng của VM được Azure thu thập mà không cần cài agent, nhưng số liệu chi tiết về bộ nhớ, swap, tiến trình hay bộ đếm bên trong máy phải được cấu hình thu thập từ guest. Cài AMA chưa đồng nghĩa DCR đã thu tất cả performance counters. Với App Service hoặc Azure SQL, tên metric và cách thu thập khác VM.

### 3.2. Chuẩn bị một cửa sổ điều tra

Trước khi kết luận, ghi lại:

- **Khoảng thời gian bằng UTC**, ví dụ 14:00–14:30 UTC, và thời điểm bắt đầu xuất hiện triệu chứng.
- **Phạm vi**: subscription, resource group, tên resource/VM, instance, availability zone, region, deployment version.
- **Định nghĩa triệu chứng**: API endpoint cụ thể, P95/P99, tỷ lệ lỗi, tải/requests mỗi phút, số người dùng bị ảnh hưởng.
- **Đường cơ sở**: cùng giờ ở ngày bình thường hoặc giai đoạn trước lần deploy gần nhất.
- **Thay đổi gần đây**: code, cấu hình app, autoscale, VM size, disk, firewall/route, database, số kết nối.

Chọn cùng độ phân giải thời gian khi so sánh, thường bắt đầu với khoảng **1 phút** để thấy spike, sau đó tổng hợp theo **5 phút** để nhìn xu hướng. Đối chiếu timestamp của các hệ thống; dữ liệu bị tổng hợp hoặc đến trễ có thể khiến hai biểu đồ nhìn như không liên quan.

Kiểm tra Azure RBAC/Entra ID để có quyền xem metrics và Log Analytics; cần thêm quyền truy cập hệ điều hành nếu chạy lệnh trong VM. Không bắt buộc mở cổng quản trị ra Internet: có thể dùng Azure Bastion hoặc kênh quản trị đã được tổ chức cho phép.

## 4. Runbook chẩn đoán tổng quát

1. **Xác nhận tác động ở tầng ứng dụng.** Đo request rate, P95/P99 và lỗi theo endpoint, phiên bản, instance. Hỏi: mọi request chậm hay chỉ các request gọi một dependency?
2. **Khoanh phạm vi và thời gian.** Tách theo VM/instance, pod, vùng, môi trường và phiên bản. So sánh cùng khung thời gian trước/sau sự cố.
3. **Đối chiếu bốn tài nguyên.** Xem CPU, memory pressure, disk latency/IOPS/throughput, network throughput/RTT/loss; đặt chúng cạnh latency và traffic.
4. **Đi xuống hệ điều hành hoặc tiến trình.** Tìm process, thread, disk device, kết nối hoặc container đóng góp phần lớn vào tín hiệu bất thường.
5. **Kiểm tra giới hạn và phụ thuộc.** Xem hạn mức VM/disk/NIC, giới hạn container, Azure SQL, số kết nối, DNS, SNAT; xác minh nơi thời gian thực sự bị tiêu tốn.
6. **Thử một giả thuyết có khả năng đảo ngược.** Ví dụ giảm đồng thời truy vấn nặng, tăng cache có kiểm soát, tăng disk tier phù hợp, hoặc scale-out có điều kiện.
7. **Đo lại và ghi kết luận.** So sánh P95, tỷ lệ lỗi, tải tương đương, hàng đợi và chi phí. Nếu triệu chứng không thay đổi, quay về bước 3 và cập nhật giả thuyết.

Sơ đồ quyết định ban đầu:

~~~mermaid
flowchart TD
    A["API chậm hoặc timeout"] --> B["Xác nhận P95, lỗi, traffic và thời gian"]
    B --> C{"Dependency trace có chiếm phần lớn latency?"}
    C -- "Có" --> D["Kiểm tra SQL, DNS, kết nối, dịch vụ bên ngoài"]
    C -- "Không hoặc chưa rõ" --> E["So sánh CPU, memory, disk, network theo instance"]
    E --> F{"Có saturation đi kèm latency tăng?"}
    F -- "Có" --> G["Đào sâu process, queue và giới hạn SKU"]
    F -- "Không" --> H["Xem lock, pool, GC, thread, tracing và các phụ thuộc"]
    D --> I["Đề xuất giả thuyết và thay đổi nhỏ"]
    G --> I
    H --> I
    I --> J["Đo lại trên tải tương đương"]
~~~

Sơ đồ chỉ định hướng tìm kiếm. Một ứng dụng có thể có đồng thời nghẽn CPU và disk; trình tự ưu tiên dựa vào tín hiệu liên quan trực tiếp đến độ trễ.

## 5. Chẩn đoán nghẽn CPU

### 5.1. Dấu hiệu cần ghép với nhau

- **Azure VM Percentage CPU** tăng trùng thời điểm P95/P99 tăng; request rate ngừng tăng dù traffic đầu vào còn tăng.
- Một hoặc nhiều lõi CPU liên tục bận; run queue tăng; thời gian chờ thực thi thread tăng.
- CPU tập trung ở process cụ thể, ví dụ tiến trình Java xử lý JSON, nén, mã hóa TLS, garbage collection (GC), hoặc chạy truy vấn tại chỗ.
- Ứng dụng container có thể bị **CPU throttling** do CPU limit dù mức CPU trung bình toàn node thấp.
- CPU cao do retry hoặc polling đôi khi là **hệ quả** của dependency chậm; cần xem trace và số lần retry.

**Ví dụ:** VM 8 vCPU có CPU trung bình 25% nhưng một luồng xử lý critical path luôn chiếm 100% một lõi. Việc tăng tổng số vCPU chưa chắc làm luồng đơn chạy nhanh hơn; cần profile, tăng tính song song hợp lý hoặc tối ưu đoạn xử lý nóng.

### 5.2. Kiểm tra tại chỗ

Linux, trong máy ảo:

~~~bash
# Hiện tải và tiến trình tiêu thụ CPU.
uptime
top -H -p 12345            # thay 12345 bằng PID thực; xem thread
ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -20

# Nếu đã có sẵn các công cụ sysstat:
mpstat -P ALL 1 5
pidstat -u 1 5
vmstat 1 5
~~~

Đọc **%usr/%sys**, CPU theo lõi, số process chờ chạy (cột **r** của vmstat), và CPU của process. Đối chiếu run queue với số vCPU. **%iowait** cao không có nghĩa CPU tính toán đang thiếu; nó thường gợi ý cần kiểm tra I/O.

Windows PowerShell:

~~~powershell
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 Name,Id,CPU
Get-Counter '\Processor(_Total)\% Processor Time'
Get-Counter '\System\Processor Queue Length'
~~~

Giá trị **CPU** của Get-Process là thời gian CPU tích lũy, không phải phần trăm tức thời. Dùng Get-Counter hoặc Performance Monitor để nhìn tỷ lệ theo thời gian. Tên counter phụ thuộc hệ điều hành và ngôn ngữ Windows.

Trong AKS:

~~~bash
kubectl top nodes
kubectl top pods -A --containers
kubectl describe pod api-7d6c8fbd8d-abcde -n production
~~~

Các lệnh trên cần Metrics Server/cấu hình quan sát phù hợp. Thông tin CPU throttling cần chỉ số container/cgroup hoặc telemetry tương ứng; **kubectl top** đơn thuần không chứng minh throttling.

### 5.3. Phân biệt nguyên nhân và cách xử lý

| Bằng chứng | Giả thuyết | Kiểm chứng tiếp | Hành động có thể cân nhắc |
|---|---|---|---|
| CPU cao, request rate cao, queue tăng | Compute không đáp ứng tải | Profile hotspot, đo hiệu suất/vCPU | Tối ưu thuật toán, cache, scale-out hoặc VM size phù hợp |
| Một lõi bận, toàn VM còn rảnh | Giới hạn bởi công việc đơn luồng | Kiểm tra thread dump/profile | Giảm việc trên critical path, phân tách hoặc cải thiện đồng thời |
| GC chiếm CPU, pause cao | Phân bổ bộ nhớ quá nhiều / heap pressure | GC logs, allocation profile | Giảm allocation, chỉnh heap sau khi đo |
| Pod chậm nhưng node CPU chưa cao | CPU limit/throttling | Quan sát throttled periods, limit/request | Điều chỉnh resource limit và replica |
| CPU tăng sau timeout downstream | Retry storm | Trace dependency, retry count | Backoff, circuit breaker, giảm retry không cần thiết |

Không scale CPU chỉ vì biểu đồ vượt một ngưỡng cố định. Kết quả cần gắn với latency và throughput, đồng thời xem chi phí VM/AKS sau thay đổi.

## 6. Chẩn đoán nghẽn bộ nhớ

### 6.1. Phân biệt ba khái niệm

1. **Bộ nhớ sử dụng cao**: RAM được process, kernel hoặc page cache tận dụng; trên Linux có thể là trạng thái bình thường.
2. **Memory pressure**: hệ thống khó đáp ứng yêu cầu cấp phát, phải reclaim liên tục, swap/page ra đĩa hoặc thu gom rác thường xuyên.
3. **Hết bộ nhớ (OOM)**: tiến trình bị kết thúc hoặc cấp phát thất bại; container có thể bị đánh dấu **OOMKilled**.

Chỉ báo tốt hơn “RAM còn trống thấp” là **available memory**, tốc độ paging/swap, major page faults, sự kiện OOM, commit usage, GC pause và độ trễ. Với dịch vụ có heap được quản lý như Java, phải xem cả heap và **native/off-heap memory**, vì tổng RSS có thể lớn hơn heap.

### 6.2. Lệnh kiểm tra

Linux:

~~~bash
free -h
cat /proc/meminfo
vmstat 1 5
ps -eo pid,comm,rss,%mem --sort=-rss | head -20

# Tìm sự kiện OOM trong kernel log, nếu có quyền:
journalctl -k --since "1 hour ago" | grep -i -E 'out of memory|oom|killed process'
~~~

Cách đọc nhanh:

- **MemAvailable** trong /proc/meminfo ước tính lượng RAM có thể dùng mà không phải swap đáng kể.
- Cột **si/so** của vmstat cho thấy swap-in/swap-out; lưu lượng lặp lại cùng độ trễ tăng là tín hiệu pressure.
- **RSS** phản ánh resident memory của process; cộng RSS nhiều tiến trình có thể đếm trùng shared pages.
- OOM kill là bằng chứng mạnh nhưng thường xuất hiện **sau** một giai đoạn áp lực bộ nhớ.

Windows:

~~~powershell
Get-Counter '\Memory\Available MBytes'
Get-Counter '\Memory\Pages/sec'
Get-Counter '\Memory\Committed Bytes'
Get-Process | Sort-Object WorkingSet64 -Descending |
    Select-Object -First 10 Name,Id,WorkingSet64
~~~

**Pages/sec** có thể chứa hoạt động paging không đồng nghĩa thiếu RAM; xem cùng **Available MBytes**, page reads/writes và độ trễ ứng dụng. Dùng Event Viewer để kiểm tra thông báo cạn tài nguyên hoặc process restart.

Trong AKS:

~~~bash
kubectl top pods -A --containers
kubectl describe pod api-7d6c8fbd8d-abcde -n production
kubectl get pod api-7d6c8fbd8d-abcde -n production \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'
~~~

Nếu kết quả có **OOMKilled**, kiểm tra memory limit, working set, dấu hiệu leak và tải trước khi tăng limit. Chỉ tăng limit không giải quyết leak tiếp diễn.

### 6.3. Câu hỏi chẩn đoán

- Bộ nhớ tăng theo **traffic** rồi giảm, hay tăng đều qua nhiều giờ/ngày? Trường hợp sau gợi ý leak hoặc cache không giới hạn.
- Có đột biến **swap-in/out** và disk I/O đồng thời không? Nghẽn được nhìn thấy ở disk có thể bắt nguồn từ RAM thiếu.
- Có **GC pause**, restart/OOM hoặc lỗi allocation cùng lúc P99 tăng không?
- Có khác biệt giữa **memory request/limit** của container và RAM trống trên node không?
- Một process đang bị giới hạn bộ nhớ hay toàn VM thiếu RAM?

Hướng xử lý có thể là sửa memory leak, giới hạn cache, tối ưu allocation, cấu hình heap phù hợp, giảm concurrency, tăng replica hoặc chọn VM SKU nhiều RAM hơn. Mỗi phương án phải được đo bằng độ trễ, tỷ lệ OOM/restart và memory pressure sau thay đổi.

## 7. Chẩn đoán nghẽn đĩa và lưu trữ

### 7.1. Bốn chỉ số không thể thay thế lẫn nhau

| Chỉ số | Ý nghĩa | Tình huống nổi bật |
|---|---|---|
| **IOPS** (operations/s) | Số thao tác đọc/ghi mỗi giây | Nhiều truy cập nhỏ, ngẫu nhiên |
| **Throughput** (MB/s) | Dung lượng dữ liệu truyền mỗi giây | Đọc/ghi file lớn, sao lưu, tuần tự |
| **Latency** (ms/op) | Thời gian hoàn thành một thao tác | Ảnh hưởng trực tiếp thời gian chờ |
| **Queue depth / queue length** | Số thao tác đang chờ hoặc chưa hoàn tất | Xem tài nguyên có bị dồn hàng hay không |

Một hệ thống có thể đạt giới hạn **IOPS** dù MB/s còn thấp; hệ thống khác đạt giới hạn **throughput** với ít thao tác lớn. Trong Azure còn có hai tầng hạn mức:

**Khả năng I/O hiệu dụng ≈ giới hạn nhỏ nhất giữa khả năng của từng managed disk, giới hạn tổng I/O của VM/SKU, và khả năng của ứng dụng/đường I/O.**

Disk cache, burst và workload pattern khiến hiệu năng đo được có thể khác thông số danh nghĩa. Khi phân tích Azure Disk, kiểm tra **disk SKU/tier**, kích thước/provisioned performance, cache mode, **disk IOPS/bandwidth consumed percentage** nếu metric hỗ trợ, cùng **VM uncached IOPS/bandwidth consumed percentage**. Đối chiếu cả phía disk và VM; nâng cấp disk sẽ không cải thiện nếu VM đã chạm trần tổng I/O.

### 7.2. Đo trong guest

Linux:

~~~bash
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT
df -h
vmstat 1 5

# Nếu sysstat được cài:
iostat -xz 1 5

# Xác định tiến trình đọc/ghi nhiều, khi công cụ có sẵn:
pidstat -d 1 5
~~~

Với **iostat -x**, xem **r/s**, **w/s**, **rkB/s**, **wkB/s**, **r_await/w_await** (độ trễ I/O tính bằng ms trong các phiên bản phổ biến) và độ dài hàng đợi trung bình (**aqu-sz**, tùy phiên bản). Không dùng riêng **%util** như kết luận tuyệt đối về bão hòa trên thiết bị lưu trữ có tính song song cao. Lệnh **df -h** tìm vấn đề **hết dung lượng**, đây là lỗi cần xử lý nhưng khác với IOPS/throughput saturation.

Windows:

~~~powershell
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Read'
Get-Counter '\PhysicalDisk(_Total)\Avg. Disk sec/Write'
Get-Counter '\PhysicalDisk(_Total)\Current Disk Queue Length'
Get-Counter '\PhysicalDisk(_Total)\Disk Transfers/sec'
Get-Volume | Select-Object DriveLetter,SizeRemaining,Size
~~~

Giá trị **Avg. Disk sec/Read** và **Avg. Disk sec/Write** được trả về theo **giây**, có thể nhân 1000 để ra mili giây. Dùng counter theo từng disk/instance nếu tổng gộp che khuất một volume nóng.

### 7.3. Diễn giải nguyên nhân

- **Disk latency tăng, queue tăng, IOPS giữ gần một trần**: nghi disk hoặc VM bị giới hạn IOPS.
- **Throughput giữ gần trần, request size lớn**: nghi giới hạn MB/s.
- **Read latency tăng khi bộ nhớ thiếu và swap hoạt động**: ưu tiên tìm nguyên nhân RAM, vì tăng disk có thể chỉ che triệu chứng.
- **Disk còn dư nhưng truy vấn DB chậm**: xem query plan, locking, transaction log, giới hạn của Azure SQL Database; không quy ngay về managed disk của VM.
- **Độ trễ tăng sau deploy**: kiểm tra thay đổi access pattern, scan toàn bảng, log đồng bộ hoặc write amplification.

Giải pháp có thể là tối ưu truy vấn và index, batch I/O, cache đọc phù hợp, giảm ghi log không cần thiết, chỉnh độ đồng thời, chọn disk tier/performance phù hợp, hoặc tăng VM size khi chính VM giới hạn I/O. Trước khi chỉnh cache mode phải kiểm tra yêu cầu tính nhất quán/durability của workload; không đổi cache chỉ dựa trên benchmark throughput.

## 8. Chẩn đoán nghẽn mạng

Mạng không chỉ có “băng thông”. API có thể nhận ít dữ liệu nhưng chậm vì DNS, TCP handshake, TLS, số lượt round trip, packet loss, TCP retransmission, số lượng kết nối hoặc giới hạn dịch vụ downstream.

### 8.1. Nhóm chỉ số và nguyên nhân

| Triệu chứng | Kiểm tra | Nguyên nhân có thể |
|---|---|---|
| Network bytes/s gần mức bền vững của SKU; queue hoặc retransmit tăng | Azure Monitor network metrics, NIC, TCP stats | Bandwidth/packet processing bị giới hạn, ứng dụng gửi nhiều dữ liệu |
| Kết nối thiết lập chậm | DNS lookup, TCP connect, TLS handshake | DNS, routing, firewall, proxy, endpoint phía xa |
| Kết nối thất bại ngắt quãng khi fan-out lớn | Connection count, ephemeral ports, SNAT | Cạn cổng SNAT, connection churn, pool cấu hình kém |
| RTT tăng, packet loss/retransmit tăng | Connection Monitor, mtr/pathping, TCP stats | Đường truyền/đích có vấn đề; cần so sánh hai chiều |
| Chỉ một dependency có thời gian chờ cao | Application Insights dependency spans, DB metrics | Dịch vụ downstream, query, pool hoặc giao thức |
| Kết nối bị từ chối/timeout nhất quán | NSG rules, route tables, DNS, firewall, endpoint | Sự cố reachability/cấu hình; khác nghẽn băng thông |

**Network In Total / Network Out Total** (hoặc metric tương đương) cho biết lưu lượng, chưa chứng minh băng thông là nguyên nhân. Đặc biệt, **DNS chậm** hay **service downstream chậm** có thể làm tổng lưu lượng mạng thấp hơn bình thường.

### 8.2. Kiểm tra kết nối từ VM

Linux:

~~~bash
ip -s link
ss -s
ss -tan state established | head -20

# Đo các giai đoạn của một HTTP request kiểm tra:
curl -sS -o /dev/null \
  -w 'dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  https://example.com/health

# Nếu môi trường đã cài:
sar -n DEV,TCP,ETCP 1 5
~~~

Thay **example.com** bằng endpoint được phép kiểm tra. Kết quả **curl** là một mẫu đơn lẻ, có thể không tái hiện connection pooling/keep-alive, số lượt gọi song song hoặc truy cập nội bộ của ứng dụng; cần lấy nhiều mẫu và đối chiếu distributed tracing.

Windows:

~~~powershell
Get-NetAdapterStatistics
Get-NetTCPConnection | Group-Object State |
    Select-Object Name,Count
Test-NetConnection -ComputerName example.com -Port 443 -InformationLevel Detailed
Resolve-DnsName example.com
~~~

**Test-NetConnection** chứng minh kết nối TCP có thể thiết lập trong điều kiện kiểm tra, không xác nhận latency HTTP/TLS hoặc throughput. Khi cần đo đường truyền giữa hai endpoint, dùng **Azure Network Watcher Connection Monitor** nếu đã được cấu hình và có quyền, xem latency, reachability, loss. **Network Watcher packet capture** có thể hỗ trợ phân tích sâu khi có yêu cầu điều tra cụ thể và quyền cần thiết.

### 8.3. Phân biệt lỗi mạng với giới hạn ứng dụng

Trace cho thấy request chờ **900 ms ở SQL dependency** trong khi các giai đoạn DNS/TCP rất nhanh. Khi đó hãy kiểm tra SQL CPU, Data IO, Log IO, query duration, locking và pool của ứng dụng; chưa thể kết luận VNet hoặc NIC nghẽn. Nếu outbound connections tăng vọt và xuất hiện timeout khi mở kết nối mới, kiểm tra cách ứng dụng tái sử dụng connection, số cổng SNAT, NAT Gateway hoặc kiến trúc egress tương ứng.

Với AKS, ngoài network node cần xem service discovery, DNS nội bộ, ingress, giới hạn pod và các lớp proxy/sidecar. Trong App Service, xem request/dependency latency và outbound connection trước khi thay đổi App Service plan.

## 9. Lấy số liệu bằng Azure CLI và Log Analytics

Các ví dụ sau dùng tên resource giả định, thực hiện truy vấn đọc. Cần đăng nhập Azure CLI và chọn subscription có quyền truy cập. Metric khả dụng tùy resource; luôn tra danh sách metric được Azure công bố cho resource thực tế.

### 9.1. Tra platform metrics của VM

~~~bash
RG="rg-perf-demo"
VM="vm-api-01"

# Lấy đúng Azure resource ID từ subscription đang chọn.
VM_ID=$(az vm show --resource-group "$RG" --name "$VM" --query id -o tsv)

# Xem tên metric mà resource thực tế cung cấp.
az monitor metrics list-definitions --resource "$VM_ID" \
  --query "[].name.value" -o table

# Xem CPU trong cửa sổ mặc định mà CLI hỗ trợ.
az monitor metrics list --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --interval PT1M \
  --aggregation Average Maximum \
  --output json
~~~

Dùng resource ID để tránh nhầm VM trùng tên ở resource group khác. Khi phân tích sự cố cụ thể, đặt **start-time** và **end-time** ở UTC thay vì chỉ dựa trên cửa sổ mặc định, ví dụ:

~~~bash
az monitor metrics list --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --start-time "2026-11-20T12:00:00Z" \
  --end-time "2026-11-20T13:00:00Z" \
  --interval PT1M --aggregation Average Maximum -o json
~~~

Các timestamp trên chỉ minh họa cú pháp. Metric trên nền tảng không có sẵn mọi chỉ số như RAM còn khả dụng hay latency ở mức từng process. Những chỉ số ấy cần guest instrumentation.

### 9.2. Phân tích CPU trong Log Analytics

Nếu Data Collection Rule đã thu performance counters Windows vào bảng **Perf**, truy vấn ví dụ:

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| where ObjectName == "Processor"
    and CounterName == "% Processor Time"
    and InstanceName == "_Total"
| summarize CpuAverage = avg(CounterValue),
            CpuP95 = percentile(CounterValue, 95)
    by Computer, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

**Chú ý:** dữ liệu chỉ xuất hiện khi DCR thu đúng counter và VM gửi về workspace đang truy vấn. Với Linux, tên object/counter/instance có thể khác; xác minh tập dữ liệu đã thu thay vì sao chép điều kiện của Windows:

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| summarize Samples = count()
    by Computer, ObjectName, CounterName, InstanceName
| order by Samples desc
~~~

Nếu VM insights ghi dữ liệu vào **InsightsMetrics**, xem schema, namespace/name/tag của bản triển khai thực tế rồi viết query thích hợp. Tránh giả định tất cả nguồn guest telemetry cùng nằm trong bảng Perf.

### 9.3. Phân tích disk latency với counter Windows

~~~kusto
Perf
| where TimeGenerated > ago(2h)
| where ObjectName == "PhysicalDisk"
| where CounterName in ("Avg. Disk sec/Read", "Avg. Disk sec/Write")
| summarize LatencySeconds = avg(CounterValue)
    by Computer, CounterName, InstanceName, bin(TimeGenerated, 5m)
| extend LatencyMs = round(LatencySeconds * 1000.0, 1)
| order by TimeGenerated asc
~~~

Kết hợp latency guest với các platform metrics của managed disk/VM để xác định trần nào đang bị chạm. Nếu truy vấn trống, điều đó có thể do DCR không thu counter, không phải bằng chứng disk khỏe.

### 9.4. Đối chiếu request và dependency latency

Với **workspace-based Application Insights** đã có telemetry, query request như sau:

~~~kusto
AppRequests
| where TimeGenerated > ago(2h)
| summarize Requests = count(),
            P95Ms = percentile(DurationMs, 95),
            Failed = countif(Success == false)
    by Name, bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Để biết thời gian bị tiêu tốn ở dependency nào:

~~~kusto
AppDependencies
| where TimeGenerated > ago(2h)
| summarize Calls = count(),
            P95Ms = percentile(DurationMs, 95),
            Failures = countif(Success == false)
    by Target, Type, bin(TimeGenerated, 5m)
| order by P95Ms desc
~~~

Bảng **AppRequests/AppDependencies** chỉ có dữ liệu khi ứng dụng đã instrument; bản triển khai Application Insights khác có thể dùng tên bảng/schema khác. Nếu có sampling, số đếm là số telemetry quan sát được; cần xem cấu hình sampling trước khi dùng để ước tính traffic thực tế. P95 của dependency không được cộng cơ học với P95 của request vì các percentile có tập mẫu và tính song song khác nhau.

## 10. Tình huống thực hành: API chậm do I/O

Giả sử API có P95 từ **180 ms lên 2.400 ms** trong 20 phút, cùng lúc request rate từ **300 lên 900 yêu cầu/phút**. Trạng thái VM vẫn Running. Nhóm vận hành ghi nhận các số sau (hoàn toàn là dữ liệu giả định để luyện suy luận):

| Chỉ số trong khoảng sự cố | Quan sát | Ý nghĩa sơ bộ |
|---|---|---|
| CPU VM trung bình | 42%, không có lõi bận kéo dài | CPU chưa phải ứng viên mạnh nhất |
| Available memory | 4,5 GiB, swap-in/out gần 0 | Chưa có bằng chứng memory pressure |
| Disk read latency P95 | Tăng từ 5 ms lên 55 ms | Nghi ngờ thời gian chờ I/O |
| Disk queue | Tăng đều khi request rate tăng | Yêu cầu I/O bị tích lại |
| Disk IOPS consumed | Tiệm cận giới hạn hiệu dụng của cấu hình | Có khả năng chạm trần IOPS |
| Network throughput | Thấp hơn hạn mức SKU; không tăng loss rõ rệt | Chưa ủng hộ giả thuyết nghẽn bandwidth |
| Application trace | Phần lớn thời gian nằm ở đọc file/index trên VM | Khớp vị trí nghi ngờ từ disk metric |

**Lập luận chẩn đoán:**

1. Latency tăng cùng request rate, nhưng CPU và memory pressure không tương ứng.
2. Disk latency và queue tăng đúng khung thời gian, IOPS bị giữ tại một mức trần.
3. Trace cho thấy luồng request đang chờ đọc trên volume đó.
4. Kiểm tra VM SKU, managed disk tier, giới hạn IOPS của **cả VM và disk**, loại truy cập và cache; nếu chưa có giới hạn tương ứng, tiếp tục tìm lock hoặc truy cập I/O đồng bộ.
5. Kiểm tra ứng dụng sau deploy: có phát sinh truy cập index/file dư thừa không? Giảm I/O không cần thiết thường là phương án bền vững hơn chỉ nâng tier.

**Thử nghiệm:** tối ưu truy cập file/index và giảm số read cho mỗi request, hoặc trong một thử nghiệm được kiểm soát dùng cấu hình storage/VM có IOPS phù hợp. Chạy lại với tải tương đương **900 yêu cầu/phút** rồi ghi P95, lỗi, disk latency, queue, IOPS và chi phí. Ví dụ P95 trở về **260 ms**, disk read latency về **7 ms**, queue giảm cho thấy giả thuyết được ủng hộ. Nếu chỉ có disk IOPS tăng mà P95 không đổi, cần tìm nút thắt khác.

Từ tình huống này có hai bài học: (1) tài nguyên dùng nhiều nhất chưa chắc là nguyên nhân, và (2) **bằng chứng về chỗ chờ trong request** phải nối được với **metric bão hòa**.

## 11. Bảng phân biệt nhanh và thứ tự kiểm tra

| Khi thấy... | Đừng kết luận vội... | Hãy kiểm tra thêm... |
|---|---|---|
| CPU 95% | Cứ tăng số vCPU là xong | Request latency, run queue, process/thread, GC, CPU throttling |
| CPU 35% nhưng một endpoint chậm | CPU chắc chắn không liên quan | CPU theo lõi/thread, lock, serialization, giới hạn container |
| RAM free thấp | Thiếu RAM | MemAvailable, swap, page faults, OOM, GC, xu hướng RSS |
| Disk queue cao | Chắc chắn phải đổi disk tier | Read/write await, IOPS/MB/s, trần VM/disk, swapping, access pattern |
| Disk đầy dung lượng | Đồng nghĩa với IOPS nghẽn | Phân biệt capacity với performance, inode/quota, lỗi ghi |
| Network bytes/s cao | Mạng chắc chắn nghẽn | Băng thông SKU, RTT, loss/retransmit, connection count |
| HTTP timeout | Lỗi VNet/NSG | DNS/TCP/TLS timing, App Insights dependency spans, DB/egress |
| Truy vấn Logs không có kết quả | Không có sự cố | Agent, DCR, workspace, query filter, retention, sampling |

Một cách ưu tiên hữu ích là bắt đầu ở **luồng request đang chậm**, sau đó đi xuống tài nguyên nơi request thực sự chờ. Biểu đồ CPU, RAM, disk và network là các mảnh ghép để kiểm tra giả thuyết, không phải bốn bảng xếp hạng độc lập.

## 12. Khắc phục, xác nhận và vận hành lâu dài

### 12.1. Xây baseline theo tải

Chọn ít nhất hai giai đoạn đại diện: giờ bình thường và giờ cao điểm. Với mỗi giai đoạn, ghi **request rate**, **P50/P95/P99**, **error rate**, CPU theo instance, available memory/GC/swap, disk latency/IOPS/MB/s/queue, network latency/retransmit, cùng giới hạn VM/disk/service đang áp dụng. Baseline nên phân biệt ngày làm việc, batch job và đợt deploy nếu hành vi tải khác nhau.

### 12.2. Đặt cảnh báo theo tác động

- Cảnh báo **user-facing**: P95 vượt SLO và/hoặc tỷ lệ lỗi cao trong nhiều cửa sổ liên tiếp.
- Cảnh báo **tài nguyên dẫn đường**: memory pressure, OOMKilled, disk latency/queue tăng, disk/VM IOPS consumed tăng, CPU saturation hoặc network loss.
- Cảnh báo **hỗ trợ điều tra**: thay đổi configuration, deployment, số replica và downstream dependency latency.

Đặt ngưỡng theo baseline/SLO của **chính workload**, tránh gán một ngưỡng 80% cho mọi CPU, disk và mạng. Dùng Azure Monitor alerts và action groups theo chính sách vận hành; kiểm tra chi phí thu thập log, retention và cardinality để tránh tăng chi phí quan sát không cần thiết.

### 12.3. Đánh giá thay đổi có kiểm chứng

Mỗi hành động khắc phục cần ghi rõ **giả thuyết**, **chỉ số dự kiến cải thiện**, **mức tải so sánh**, **thời điểm áp dụng**, **kết quả trước/sau** và **hệ quả về chi phí**. Nếu scale VM, phải xem cả giới hạn network/disk và downtime hoặc cơ chế triển khai. Nếu chỉnh bộ nhớ Java, phải đo GC và RSS, không chỉ heap. Nếu đổi disk tier, kiểm tra giới hạn mới có thực sự được VM hỗ trợ không.

Giữ nhật ký ngắn cho incident: vùng ảnh hưởng, mốc UTC, biểu đồ/trace, nguyên nhân gốc đã xác nhận hoặc còn chưa chắc chắn, thay đổi áp dụng và việc phòng ngừa tái diễn. Điều này giúp các lần phân tích sau không lặp lại từ đầu.

## 13. Bài tập tự kiểm tra

**Bài 1.** VM có CPU trung bình 30%, một endpoint P99 tăng mạnh, còn một lõi CPU đạt 100% trong 10 phút. Bạn sẽ cần thêm dữ liệu gì để phân biệt nghẽn đơn luồng với lock hoặc dependency chậm?

*Gợi ý:* kiểm tra CPU theo thread, stack/profile, trace của endpoint, thời gian chờ lock, dependency latency và tỷ lệ retry.

**Bài 2.** API chậm; RAM “free” còn 5%, nhưng MemAvailable vẫn tương đối cao, không có swap và không có OOM. Có nên tăng RAM ngay không?

*Gợi ý:* chưa đủ bằng chứng về memory pressure; xem page cache, RSS, GC, luồng request đang chờ và các tài nguyên khác.

**Bài 3.** Tốc độ ghi của managed disk không vượt trần disk danh nghĩa, nhưng disk latency tăng khi traffic tăng. Hãy nêu ít nhất ba khả năng.

*Gợi ý:* trần IOPS/MB/s của VM, request I/O nhỏ hoặc access pattern gây queue, ứng dụng ghi đồng bộ, cache, hoặc thời gian chờ từ các lớp khác.

**Bài 4.** P95 request là 1.800 ms, CPU/đĩa đều bình thường, còn dependency tới một endpoint mất khoảng 1.500 ms. Lập kế hoạch kiểm tra DNS, TCP/TLS, response của downstream và connection pool mà không kết luận vội do “mạng Azure chậm”.

**Tiêu chí hoàn thành:** người học đưa ra được giả thuyết gắn với **ít nhất hai nguồn bằng chứng**, giải thích vì sao các khả năng khác yếu hơn, và nêu cách đo lại trong điều kiện tải tương đương.

## 14. Ghi nhớ khi trực vận hành

Chẩn đoán hiệu năng trên Azure bắt đầu bằng tác động mà người dùng nhìn thấy, rồi liên kết **request traces**, **platform metrics**, **guest metrics** và **cấu hình giới hạn**. CPU cần xem lõi, thread và hàng đợi; bộ nhớ cần xem pressure chứ không chỉ free RAM; đĩa cần phân biệt IOPS, throughput, latency và giới hạn VM/disk; mạng cần tách throughput khỏi DNS, RTT, loss, kết nối và downstream latency.

Kết luận đáng tin cậy là kết luận có thể tái kiểm chứng: giải pháp tác động đúng điểm nghẽn, P95/error rate cải thiện ở tải tương đương, và chi phí cùng độ ổn định vẫn phù hợp yêu cầu vận hành.
