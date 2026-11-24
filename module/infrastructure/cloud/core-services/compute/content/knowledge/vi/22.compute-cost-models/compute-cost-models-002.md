# On-demand và cách đo thời gian sử dụng tài nguyên

On-demand là mô hình sử dụng tài nguyên compute theo nhu cầu, không cần cam kết mua trước một lượng capacity trong thời gian dài. Người dùng tạo VM, container hoặc workload serverless khi cần và thanh toán theo đơn vị đo mà dịch vụ quy định. Mô hình này linh hoạt cho workload thay đổi, môi trường phát triển, thử nghiệm và những hệ thống chưa dự báo chắc chắn được nhu cầu.

Để kiểm soát chi phí, cần hiểu hai khái niệm khác nhau: **thời gian tài nguyên được cấp phát và tính phí** và **mức tài nguyên thực sự được workload sử dụng**. Một VM có thể chỉ dùng 10% CPU nhưng vẫn bị tính phí compute trong toàn bộ khoảng thời gian ở trạng thái được tính phí. Ngược lại, một VM đã dừng có thể không còn phí CPU nhưng volume, IP, snapshot hoặc license đi kèm vẫn phát sinh chi phí.

Bài học này giải thích cách hoạt động của on-demand, xác định khoảng thời gian tính phí, đo usage theo VM, container và serverless, đọc billing export, phân bổ chi phí và đối chiếu số liệu vận hành với hóa đơn.

## 1. On-demand là gì?

On-demand là mô hình cung cấp tài nguyên theo yêu cầu. Người dùng chọn loại tài nguyên, cấu hình và khu vực triển khai; nhà cung cấp cấp phát tài nguyên và ghi nhận mức sử dụng theo meter tương ứng.

Đặc điểm thường gặp:

- Không cần cam kết sử dụng trong nhiều tháng hoặc nhiều năm.
- Có thể tạo, thay đổi hoặc xóa tài nguyên theo nhu cầu.
- Chi phí biến đổi theo thời gian, cấu hình và lượng tài nguyên được tính phí.
- Có thể phù hợp với tải khó dự báo hoặc thời gian chạy ngắn.
- Đơn giá thường cao hơn một số lựa chọn có cam kết hoặc capacity mua trước, tùy dịch vụ và điều kiện.

On-demand không có nghĩa mọi thành phần chỉ tính tiền khi CPU đang bận. Mỗi loại tài nguyên có cách đo riêng. VM có thể được tính theo thời gian instance ở trạng thái billable; block volume có thể tính theo dung lượng được provision theo tháng; network egress tính theo dữ liệu truyền; serverless có thể tính theo số request và thời gian thực thi.

### Ví dụ

Một nhóm phát triển tạo 4 VM để kiểm thử trong 3 giờ, sau đó xóa chúng. Nếu compute meter tính phí trong khoảng VM tồn tại ở trạng thái billable, chi phí compute được xác định từ cấu hình và thời gian tính phí của 4 VM. Nếu nhóm giữ lại 4 disk sau khi xóa VM, storage meter vẫn có thể tiếp tục phát sinh chi phí.

On-demand giúp nhóm tạo và hủy tài nguyên linh hoạt, nhưng cần quy trình lifecycle và dọn dẹp để tránh tài nguyên không còn được sử dụng vẫn tiếp tục bị tính phí.

## 2. Phân biệt thời gian được cấp phát, thời gian hoạt động và mức sử dụng

Ba đại lượng thường bị nhầm lẫn:

- **Provisioned time:** thời gian tài nguyên được cấp phát hoặc tồn tại theo cách dịch vụ tính phí.
- **Operational time:** thời gian tài nguyên ở trạng thái có thể hoạt động hoặc phục vụ workload.
- **Utilization:** tỷ lệ hoặc lượng tài nguyên thực sự được sử dụng trong khoảng thời gian đó.

Ví dụ một VM 8 vCPU được tính phí trong 10 giờ. Trong 10 giờ đó, CPU trung bình chỉ bận 20%. Nếu đơn giá là theo instance-hour cố định, compute usage vẫn là 10 instance-hours; mức CPU 20% là metric vận hành, không tự động làm hóa đơn giảm còn 2 giờ.

Tương tự, VM có 32 GiB RAM được provision trong 10 giờ vẫn có thể bị tính phí theo cấu hình và thời gian provision dù process chỉ dùng 8 GiB. Cách tính cụ thể tùy dịch vụ; một số nền tảng serverless hoặc container có meter theo vCPU-second và GiB-second, nhưng đó là một mô hình meter khác.

### Bảng phân biệt

| Khái niệm | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Provisioned time | Tài nguyên được giữ/cấp phát trong bao lâu? | VM tồn tại ở trạng thái billable 10 giờ |
| Runtime | Workload thực sự chạy trong bao lâu? | Job chạy 42 phút |
| Utilization | Trong thời gian đó tài nguyên bận bao nhiêu? | CPU trung bình 20% |
| Billable usage | Meter của nhà cung cấp ghi nhận bao nhiêu đơn vị tính phí? | 10 instance-hours hoặc 80 vCPU-hours |
| Charge | Usage đó được quy đổi thành tiền bao nhiêu? | Billable quantity nhân đơn giá, sau điều chỉnh |

Để quản lý chi phí, cần theo dõi cả billable usage và utilization. Billable usage giải thích lượng được tính tiền; utilization cho biết tài nguyên có đang bị cấp dư hoặc sử dụng hiệu quả không.

## 3. Đơn vị đo thời gian và tài nguyên

Nhà cung cấp có thể dùng nhiều đơn vị đo khác nhau. Cần đọc đúng unit của từng meter trong pricing page và billing export.

| Đơn vị | Ý nghĩa | Trường hợp thường gặp |
|---|---|---|
| Instance-second | Một instance được tính phí trong một giây | Một số VM hoặc dịch vụ compute |
| Instance-minute | Một instance được tính phí trong một phút | Một số dịch vụ theo phút |
| Instance-hour | Một instance được tính phí trong một giờ | VM và capacity theo giờ |
| vCPU-second / vCPU-hour | Số vCPU nhân với thời gian | Container hoặc compute theo CPU |
| GiB-second / GiB-hour | Dung lượng bộ nhớ nhân với thời gian | Serverless/container theo memory |
| GPU-hour | Một GPU hoặc loại accelerator được tính phí trong một giờ | GPU instance hoặc accelerator |
| Request / invocation | Một lần gọi hoặc thực thi | Function/serverless API |
| GB-month / GiB-month | Dung lượng lưu trữ nhân thời gian tháng | Volume, snapshot hoặc object storage |
| GB transferred | Dữ liệu truyền qua một ranh giới mạng | Egress hoặc inter-region transfer |

Tên đơn vị và quy tắc quy đổi có thể khác nhau. GB và GiB không giống nhau; giờ billing có thể không phải 3.600 giây usage trong mọi trường hợp nếu có minimum charge hoặc rounding. Không tự suy ra cách làm tròn từ tên metric.

### Ví dụ vCPU-hour

Một VM có 4 vCPU được tính phí trong 5 giờ:

\[
vCPU\text{-}hours = 4 \times 5 = 20
\]

Nếu có 3 VM cùng cấu hình và cùng thời gian:

\[
3 \times 4 \times 5 = 60\ vCPU\text{-}hours
\]

Nếu nhà cung cấp tính theo instance-hour cố định, billable quantity có thể là 15 instance-hours thay vì 60 vCPU-hours. Cần dùng đúng meter trong billing export để tính tiền.

### Ví dụ memory-time

Một container được cấp 2 GiB memory trong 30 phút:

\[
GiB\text{-}hours = 2 \times 0.5 = 1
\]

Một số dịch vụ tính CPU và memory riêng; một số dịch vụ gộp vào một cấu hình instance; một số tính theo request và duration. Không áp dụng công thức GiB-hour cho mọi loại compute.

## 4. Khoảng thời gian nào của VM được tính phí?

VM trải qua nhiều trạng thái trong vòng đời. Việc bắt đầu và kết thúc billable interval phụ thuộc nhà cung cấp, loại VM, OS license, loại disk và dịch vụ đi kèm.

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa vận hành | Cách tính phí cần xác minh |
|---|---|---|
| Requested / provisioning | Yêu cầu tạo máy đã được gửi, nền tảng đang cấp phát | Có thể có quy tắc meter riêng; kiểm tra billing record |
| Starting / booting | Máy đang khởi động | Thời điểm bắt đầu billable có thể gắn với cấp phát hoặc trạng thái chạy |
| Running | Máy đang hoạt động | Thường có compute charge theo cấu hình và thời gian |
| Stopping | Đang dừng máy | Xác định chính xác thời điểm compute meter kết thúc |
| Stopped / deallocated | Máy đã dừng hoặc nhả compute | Compute có thể ngừng tính, nhưng disk/IP/license có thể tiếp tục |
| Hibernated / suspended | Trạng thái ngủ hoặc lưu RAM ra storage | Quy tắc compute và storage phụ thuộc dịch vụ |
| Terminating / deleting | Đang xóa tài nguyên | Kiểm tra thời điểm kết thúc meter và resource phụ còn lại |
| Terminated / deleted | Tài nguyên compute đã bị xóa | Compute thường kết thúc; tài nguyên tách rời vẫn có thể tồn tại |

Không dùng timestamp click nút Start/Stop làm bằng chứng duy nhất. API request có thể được chấp nhận trước khi state chuyển đổi. Cần đối chiếu lifecycle event với billing usage record.

### Running không phải lúc nào cũng đồng nghĩa với workload đang làm việc

Một VM ở trạng thái running nhưng ứng dụng chưa khởi động, đang chờ traffic hoặc CPU idle vẫn có thể phát sinh compute charge. Điều này thường xảy ra trong:
- Môi trường development bật máy qua đêm.
- VM chờ batch job.
- Instance dự phòng không có traffic.
- Máy giữ cache hoặc connection nóng.
- Máy đang chờ phê duyệt hoặc thao tác thủ công.

Nếu workload không cần máy liên tục, có thể xem xét schedule start/stop, autoscaling, scale-to-zero hoặc mô hình serverless phù hợp.

### Stopped không có nghĩa toàn bộ chi phí bằng 0

Sau khi stop VM, các thành phần sau có thể vẫn được tính phí:
- Boot disk hoặc data disk.
- Snapshot và backup.
- Public/static IP được giữ lại.
- Reserved capacity hoặc commitment.
- License theo giờ hoặc theo host.
- Network appliance, NAT hoặc load balancer.
- Dịch vụ monitoring/logging lưu trữ dữ liệu.

Khi cần dừng chi phí, phải kiểm tra từng resource được tạo cùng VM và quan hệ phụ thuộc của chúng.

## 5. Cách đo thời gian sử dụng VM

Để đo billable time, cần thu thập thông tin từ control plane và billing system.

### Dữ liệu lifecycle

Tối thiểu nên có:
- Resource ID.
- Resource type và SKU/instance family.
- Region/zone.
- Timestamp tạo yêu cầu.
- Timestamp chuyển sang running.
- Timestamp stop/deallocate.
- Timestamp terminate/delete.
- Các lần start/stop tiếp theo.
- Account/project/subscription.
- Tags hoặc labels phân bổ chi phí.

Timestamp nên được lưu theo UTC hoặc có timezone rõ ràng. Khi tính thời lượng, dùng timestamp thực tế của state transition nếu nền tảng cung cấp.

### Tính khoảng thời gian

Với một VM có một khoảng billable duy nhất:

\[
T_{billable} = t_{end} - t_{start}
\]

Nếu VM được start/stop nhiều lần, cộng các khoảng billable:

\[
T_{total} = \sum_{k=1}^{n}(t_{end,k} - t_{start,k})
\]

Công thức này chỉ xác định thời lượng theo state event. Kết quả cuối cần được đối chiếu với meter quantity của nhà cung cấp, vì có thể có minimum duration, rounding, license meter hoặc quy tắc riêng.

### Ví dụ

Một VM được tạo và chạy từ 09:10 đến 12:40, sau đó dừng. Khoảng thời gian theo event là 3 giờ 30 phút.

Nếu dịch vụ tính theo giây và không có minimum/rounding bổ sung:

\[
T = 3.5\ hours
\]

Nếu dịch vụ tính theo giờ với quy tắc làm tròn hoặc minimum charge, billable quantity có thể khác. Không tự làm tròn lên hay xuống trước khi đọc pricing terms.

### Nhiều instance

Giả sử 5 VM có khoảng chạy billable khác nhau:

| VM | Billable start | Billable end | Thời gian theo event |
|---|---|---|---:|
| vm-a | 08:00 | 10:00 | 2 giờ |
| vm-b | 08:30 | 11:30 | 3 giờ |
| vm-c | 09:00 | 10:15 | 1,25 giờ |
| vm-d | 10:00 | 12:00 | 2 giờ |
| vm-e | 10:30 | 12:30 | 2 giờ |
| **Tổng** |  |  | **10,25 instance-hours** |

Tổng instance-hours không giống elapsed time của cả nhóm. Nhóm tồn tại từ 08:00 đến 12:30, tức 4,5 giờ, nhưng tổng lượng compute là 10,25 instance-hours.

## 6. Tính chi phí on-demand từ billable usage

Mô hình đơn giản:

\[
Cost_{compute} = \sum_i Quantity_i \times UnitPrice_i
\]

Trong đó:
- Quantity là số đơn vị billable được ghi nhận.
- UnitPrice là đơn giá của đúng SKU, region, OS và pricing dimension.
- i là từng dòng meter hoặc từng khoảng cấu hình.

Tổng hóa đơn có thể cộng thêm storage, network, license, support, tax và các khoản điều chỉnh. Không dùng một đơn giá VM để tính toàn bộ chi phí hệ thống.

### Ví dụ minh họa

Giả sử một loại VM có đơn giá giả định 0,12 đơn vị tiền cho mỗi instance-hour. Nhóm chạy 3 VM trong 5 giờ, không có discount hoặc khoản phụ:

\[
Quantity = 3 \times 5 = 15\ instance\text{-}hours
\]

\[
Cost = 15 \times 0.12 = 1.80
\]

Đây là phép tính minh họa, không phải giá của nhà cung cấp cụ thể. Giá thực tế phụ thuộc region, OS, loại máy, license, currency, discount và thời điểm sử dụng.

### Khi cấu hình thay đổi giữa kỳ

Nếu VM resize từ 2 vCPU sang 8 vCPU giữa ngày, cần chia thành các đoạn meter riêng:

\[
Cost = Q_{small}P_{small} + Q_{large}P_{large}
\]

Không nhân tổng thời gian với cấu hình cuối cùng. Tương tự, nếu đổi region, OS license hoặc instance family, cần tách từng SKU.

### Discount và credit

On-demand usage có thể được giảm bởi credit, promotion, negotiated discount hoặc pricing program. Billing export thường phân biệt list cost, effective cost, net cost hoặc các adjustment tùy provider. Cần xác định đang phân tích:
- Giá niêm yết.
- Chi phí trước discount.
- Chi phí sau discount.
- Chi phí phân bổ nội bộ.
- Số tiền thực thanh toán sau credit/tax.

Không so sánh hai nhóm workload bằng những cột cost khác định nghĩa.

## 7. Tài nguyên compute không phải meter duy nhất

Một VM có thể tạo ra nhiều loại chi phí độc lập.

| Thành phần | Đơn vị thường gặp | Có thể còn tính phí khi VM stop? |
|---|---|---|
| Compute instance | Instance-second/hour hoặc vCPU-time | Thường ngừng khi compute đã deallocate, theo điều kiện dịch vụ |
| Boot/data disk | GiB-month, provisioned IOPS hoặc throughput | Có |
| Snapshot/backup | Dung lượng lưu trữ hoặc operation | Có |
| Public/static IP | IP-hour hoặc điều kiện giữ IP | Có thể có |
| Network egress | GB transferred | Khi có traffic |
| NAT/load balancer | Gateway-hour, capacity unit, processed bytes | Có thể có |
| License | Theo giờ, core, host hoặc subscription | Tùy điều khoản |
| Monitoring/logging | Ingest, retention, query | Có |
| Reservation/commitment | Phí theo cam kết | Theo hợp đồng, không phụ thuộc VM đang chạy |

Một VM bị stop nhưng giữ disk 500 GiB trong 30 ngày vẫn có thể tạo storage charge đáng kể. Nếu chỉ theo dõi compute instance-hours, báo cáo sẽ không giải thích được toàn bộ hóa đơn.

### Tài nguyên tách rời

Cần lập quan hệ giữa:
- VM và disk.
- VM và IP.
- VM và snapshot.
- VM và load balancer/backend.
- VM và license.
- VM và log/monitoring workspace.

Khi terminate VM, kiểm tra chính sách delete-on-termination. Một số disk hoặc IP có thể được giữ lại có chủ đích; không xóa tự động nếu có dữ liệu cần bảo toàn.

## 8. On-demand trong container và Kubernetes

Trong container platform, có thể có nhiều lớp tính phí.

### Kubernetes tự quản lý trên VM

Nếu cluster chạy trên VM do tổ chức quản lý, cloud provider thường tính compute theo node VM và các resource liên quan. Pod CPU request/limit giúp scheduler quản lý capacity, nhưng không nhất thiết là meter trực tiếp để tính hóa đơn VM.

Ví dụ node có 8 vCPU và chạy 10 pod. Nếu tổng CPU request là 5 vCPU, provider vẫn có thể tính phí node theo VM capacity trong thời gian node billable, không phải chỉ 5 vCPU được request.

Để phân bổ chi phí cho pod, cần dùng allocation model dựa trên:
- CPU request hoặc usage.
- Memory request hoặc working set.
- GPU allocation.
- PVC và storage.
- Network hoặc service-specific charge.
- Phần overhead của system daemon và node.

Đây là cost allocation nội bộ, có thể khác với billable usage trực tiếp.

### Container service tính theo resource-time

Một số dịch vụ container managed hoặc serverless tính theo vCPU-second, GiB-second, số request hoặc thời gian task chạy. Trong trường hợp này, meter có thể gắn với resource configuration của task/container và thời gian được dịch vụ xác định.

Cần đọc rõ:
- Thời điểm bắt đầu tính.
- Thời điểm dừng tính.
- Có minimum duration không.
- CPU và memory có tính riêng không.
- Idle capacity có bị tính không.
- Có phí cho request, network, storage hoặc control plane không.

### Kubernetes node autoscaling

Node scale out/in thay đổi số VM được tính phí. Pod scheduling và eviction có thể khiến node tồn tại lâu hơn workload. Cluster autoscaler có thể giữ node rỗng trong thời gian scale-down delay để tránh churn.

Cần đo:
- Node billable hours.
- Node utilization và allocatable capacity.
- Pod request/usage.
- Thời gian node rỗng.
- Scale-up/scale-down delay.
- System overhead và daemonset usage.

Node utilization thấp trong thời gian dài có thể là dấu hiệu overprovisioning, nhưng không nên giảm node chỉ dựa vào trung bình nếu workload có burst hoặc yêu cầu availability.

## 9. On-demand trong serverless

Serverless thường thay đổi cách đo từ thời gian tồn tại của VM sang số lần thực thi và tài nguyên trong mỗi lần thực thi.

Các meter có thể gồm:
- Request/invocation count.
- Duration theo millisecond hoặc đơn vị thời gian khác.
- Memory configuration hoặc memory consumed.
- CPU hoặc vCPU-time.
- Provisioned concurrency hoặc warm capacity.
- Data transfer và các dịch vụ phụ trợ.

### Ví dụ duration-based

Một function được gọi 10.000 lần, mỗi invocation có duration trung bình 250 ms. Tổng execution duration:

\[
10{,}000 \times 0.25 = 2{,}500\ seconds
\]

Nếu function được cấu hình 1 GiB memory và meter tính theo memory-time:

\[
2{,}500 \times 1 = 2{,}500\ GiB\text{-}seconds
\]

Phép tính trên chưa bao gồm request charge, provisioned capacity, network hoặc dịch vụ khác. Một số nền tảng có quy tắc làm tròn từng invocation, minimum duration hoặc cách tính memory riêng.

### Cold start và idle

Thời gian cold start có thể nằm trong duration tính phí hoặc được xử lý theo quy tắc cụ thể của nền tảng. Provisioned concurrency hoặc warm instance có thể phát sinh phí ngay cả khi ít request. Cần đọc meter tương ứng và so sánh với latency benefit.

### So sánh VM và serverless

| Tiêu chí | VM on-demand | Function/serverless |
|---|---|---|
| Đơn vị chính | Thời gian instance/cấu hình | Request, duration và resource-time |
| Idle | Thường vẫn tính khi VM billable | Có thể không tính execution khi idle, nhưng warm/provisioned capacity có thể tính |
| Control | Người dùng quản lý OS và runtime | Provider quản lý phần lớn nền tảng |
| Burst | Cần autoscaling hoặc capacity sẵn | Có thể scale tự động theo dịch vụ và quota |
| Chi phí phụ | Disk, IP, network, license | Request, duration, provisioned capacity, network và dependency |
| Đo utilization | OS/process/VM metrics | Invocation, duration, concurrency, memory/CPU metrics |

Không nên kết luận serverless luôn rẻ hơn VM. Với workload chạy liên tục, serverless có thể đắt hơn hoặc có giới hạn hiệu năng khác. Cần so sánh chi phí theo workload hoàn thành và SLO.

## 10. Đo runtime bằng metric vận hành

Billing record cho biết nhà cung cấp tính phí bao nhiêu đơn vị. Metric vận hành cho biết tài nguyên được dùng như thế nào.

### Metric VM

- Instance state và uptime.
- CPU utilization theo thời gian.
- Memory available/working set.
- Disk IOPS, throughput và latency.
- Network bytes/packets.
- Process uptime và service health.
- Boot time, shutdown time và restart count.

### Metric container

- Container start/stop timestamp.
- CPU usage và throttling.
- Memory working set và OOM.
- Pod/container uptime.
- Request/limit.
- Queue depth và replica count.
- Node allocatable và node idle time.

### Metric serverless

- Invocation count.
- Duration distribution.
- Concurrent execution.
- Throttles và retries.
- Cold start.
- Memory used.
- Error và timeout.
- Provisioned/warm capacity.

### Vì sao cần cả billing và monitoring?

Ví dụ, billing cho thấy VM chạy 720 giờ trong tháng. Monitoring cho thấy CPU trung bình 4%, RAM dùng 15% và không có request vào ban đêm. Đây là bằng chứng có thể cân nhắc schedule hoặc resize.

Ngược lại, VM chạy 720 giờ nhưng CPU trung bình 70%, p95 latency đạt SLO và tải liên tục có thể là capacity hợp lý. Chỉ số uptime giống nhau nhưng quyết định tối ưu khác nhau.

## 11. Billing export và usage records

Cloud provider thường cung cấp cost management report, usage detail hoặc billing export để phân tích chi phí ở cấp dòng.

Các trường hữu ích có thể gồm:
- Usage start/end time.
- Resource ID hoặc resource name.
- SKU/service/meter.
- Region/zone.
- Usage quantity và unit.
- Pricing unit và rate.
- Cost trước/sau discount.
- Currency.
- Project/account/subscription.
- Tags/labels hoặc cost allocation tag.
- Charge type như usage, tax, credit, adjustment hoặc commitment.

Tên trường và mức chi tiết khác nhau giữa nhà cung cấp. Một số dòng có thể không chứa resource ID, hoặc cost được tổng hợp theo meter thay vì instance.

### Billing export là nguồn đối chiếu tính phí

Không tự tạo hóa đơn bằng cách cộng thời gian từ log VM nếu billing system đã cung cấp usage quantity chính thức. Log lifecycle hữu ích để điều tra và phân tích, nhưng billing export là nguồn để đối chiếu lượng nhà cung cấp ghi nhận theo meter.

### Usage delay và finalized cost

Cost data có thể đến trễ hoặc được điều chỉnh sau khi usage phát sinh. Báo cáo ngày hiện tại có thể chưa đầy đủ. Cần phân biệt:
- Usage event time.
- Ingestion/record time.
- Invoice period.
- Finalized charge.
- Adjustment hoặc credit xuất hiện sau đó.

Không kết luận chi phí ngày hiện tại thấp bất thường nếu dữ liệu billing chưa hoàn tất.

## 12. Gắn nhãn để phân bổ chi phí

Để biết ai hoặc workload nào tạo ra usage, cần có quy tắc tagging/labeling nhất quán.

Các nhãn nên cân nhắc:
- service hoặc application.
- environment: dev, test, staging, production.
- team hoặc cost center.
- owner.
- project/product.
- customer/tenant nếu chính sách cho phép.
- lifecycle hoặc expiry date.
- managed-by hoặc IaC stack.

### Tránh tag không ổn định

Không dùng giá trị thay đổi liên tục như request ID hoặc timestamp làm resource tag. Tag nên có cardinality vừa phải và được áp dụng từ provisioning pipeline.

### Untagged cost

Một phần chi phí có thể không gắn được trực tiếp vào một resource:
- Shared network.
- NAT gateway.
- Load balancer.
- Monitoring workspace.
- Shared Kubernetes node.
- Support plan.
- Commitment discount.
- Data transfer liên vùng.

Cần quy định cách phân bổ shared cost: theo traffic, CPU usage, memory request, số instance, doanh thu hoặc một driver phù hợp. Ghi rõ đây là allocation policy nội bộ, không phải meter trực tiếp của provider.

### Ví dụ phân bổ shared node

Một node VM có chi phí compute 100 đơn vị tiền trong một ngày. Ba workload có CPU request trung bình tương ứng 50%, 30% và 20% allocatable CPU. Nếu tổ chức chọn CPU request làm driver phân bổ, cost nội bộ có thể được chia 50, 30 và 20.

Đây chỉ là quy tắc phân bổ. Nếu một workload sử dụng CPU thực tế rất thấp nhưng giữ request lớn, phân bổ theo request có thể khác với phân bổ theo usage. Chọn driver phù hợp mục tiêu chargeback/showback và công bố rõ.

## 13. Đo và tính thời gian bằng dữ liệu event

Một cách triển khai là lưu lifecycle event của từng resource vào bảng hoặc hệ thống log.

Ví dụ cấu trúc:

| resource_id | event | timestamp_utc | region | sku |
|---|---|---|---|---|
| vm-101 | started | 2026-11-01T02:00:00Z | region-a | compute-medium |
| vm-101 | stopped | 2026-11-01T05:30:00Z | region-a | compute-medium |
| vm-101 | started | 2026-11-01T08:00:00Z | region-a | compute-medium |
| vm-101 | terminated | 2026-11-01T10:00:00Z | region-a | compute-medium |

Từ các event, có thể dựng các interval:
- 02:00–05:30: 3,5 giờ.
- 08:00–10:00: 2 giờ.
- Tổng thời gian theo lifecycle event: 5,5 giờ.

Nếu meter tính theo instance-hour và không có rounding/minimum, quantity tham khảo là 5,5 instance-hours. Đối chiếu billing export để xác nhận.

### Pseudocode tính interval

~~~text
for each resource_id:
    sort lifecycle events by timestamp
    open_interval = none

    for event in events:
        if event starts a billable state:
            if open_interval is none:
                open_interval = event.timestamp

        if event ends a billable state:
            if open_interval exists:
                duration += event.timestamp - open_interval
                open_interval = none

    if open_interval exists:
        duration += report_end_time - open_interval
~~~

Đoạn logic này cần xử lý các trường hợp:
- Thiếu stop event.
- Event trùng hoặc đến sai thứ tự.
- VM bị terminate khi đang running.
- Resource được resize giữa interval.
- Timezone hoặc clock skew.
- Event bị ghi nhận trễ.
- State transition thất bại hoặc bị rollback.

Không dùng một script đơn giản để thay thế meter chính thức nếu yêu cầu là đối soát hóa đơn.

## 14. Quy trình đối chiếu monitoring với billing

Một quy trình có thể thực hiện hàng ngày hoặc theo kỳ:

1. Lấy inventory resource theo account/project/subscription.
2. Lấy lifecycle events trong cùng kỳ.
3. Lấy billing usage export theo meter và resource ID.
4. Chuẩn hóa timezone và currency.
5. Map SKU, region, OS và pricing dimension.
6. Tính runtime theo event để kiểm tra chéo.
7. So sánh event-derived quantity với billing quantity.
8. Điều tra chênh lệch do rounding, minimum, license, delay hoặc thiếu event.
9. Gắn tag và phân bổ shared cost.
10. Ghi nhận cost owner và hành động tối ưu.

### Ví dụ sai lệch

Lifecycle event cho biết VM chạy 10 giờ, nhưng billing export có 11 instance-hours. Các nguyên nhân có thể:
- Meter bắt đầu tính trước timestamp running mà event log thu thập.
- Có minimum charge hoặc rounding.
- VM đã được restart trong kỳ nhưng thiếu event.
- Billing line gồm một SKU hoặc license khác.
- Event time và billing time dùng quy tắc khác.
- Export chưa finalized hoặc có adjustment.

Không tự sửa billing quantity để khớp log. Ghi nhận chênh lệch và xác minh định nghĩa meter.

### Kiểm tra theo ngày và theo tháng

Theo ngày giúp phát hiện resource chạy ngoài giờ, nhưng invoice thường tổng hợp theo kỳ và có discount/credit. Theo tháng cần xem:
- Usage quantity.
- Unit price và effective price.
- Cost trước/sau discount.
- Shared cost.
- Commitment coverage.
- Tax/credit/adjustment.
- Tỷ lệ cost chưa gắn owner.

## 15. Tối ưu chi phí dựa trên thời gian sử dụng

### Schedule start/stop

Phù hợp với:
- Development VM.
- Test environment.
- Sandbox.
- Build agent không cần chạy liên tục.
- Lab hoặc môi trường học tập.

Ví dụ môi trường chỉ làm việc 10 giờ mỗi ngày trong 5 ngày mỗi tuần. Nếu có thể dừng ngoài giờ mà không ảnh hưởng dữ liệu và tác vụ nền, compute runtime có thể giảm đáng kể.

Trước khi schedule:
- Kiểm tra cron/job và batch.
- Kiểm tra backup window.
- Kiểm tra license.
- Kiểm tra dependency và connection.
- Dùng lifecycle hook để shutdown an toàn.
- Đảm bảo disk và dữ liệu vẫn được giữ.
- Có cơ chế start trước giờ làm việc và health check.

### Autoscaling và scale to zero

Autoscaling phù hợp với tải biến động. Scale to zero phù hợp khi workload chấp nhận cold start hoặc có queue bền vững.

Cần tránh scale quá nhanh tạo instance churn, bootstrap cost hoặc request lỗi. Theo dõi min/desired/max, cooldown, startup duration và queue backlog.

### Rightsizing

Nếu VM chạy đủ thời gian nhưng CPU/RAM sử dụng thấp, xem xét:
- Chọn instance nhỏ hơn.
- Giảm memory provision nếu runtime cho phép.
- Tách workload để giảm headroom lãng phí.
- Dùng instance family phù hợp với CPU/memory ratio.
- Dùng container để chia sẻ node capacity.
- Chuyển workload phù hợp sang serverless hoặc job service.

Rightsizing phải dựa trên peak, p95/p99, failover headroom và tải mùa vụ, không chỉ CPU trung bình.

### Xóa tài nguyên phụ

Tìm:
- Disk không còn gắn VM.
- Snapshot quá cũ.
- IP không dùng.
- Load balancer/backend rỗng.
- NAT hoặc gateway không cần.
- Image cũ.
- Log retention vượt nhu cầu.
- Volume provisioned IOPS không dùng.

Có thể gắn expiry tag và quy trình owner review trước khi xóa để tránh mất dữ liệu cần thiết.

## 16. Khi nào on-demand phù hợp và khi nào nên cân nhắc mô hình khác?

| Đặc điểm workload | On-demand có thể phù hợp | Cần cân nhắc |
|---|---|---|
| Tải không ổn định, khó dự báo | Linh hoạt tăng/giảm tài nguyên | Autoscaling và quota |
| Dev/test chạy theo giờ | Chỉ trả trong thời gian cần | Schedule và cleanup |
| Workload ngắn hạn hoặc thử nghiệm | Không cần cam kết dài hạn | Minimum charge và startup time |
| Production tải ổn định quanh năm | Dễ bắt đầu và linh hoạt | Commitment/reservation có thể giảm đơn giá |
| Batch có thể retry | Tạo compute khi có queue | Spot/preemptible nếu chịu interruption |
| API cần phản hồi tức thời | Có thể giữ minimum capacity | Serverless cold start và provisioned capacity |
| GPU workload theo đợt | On-demand tránh giữ GPU nhàn rỗi | GPU quota, availability và startup delay |

On-demand thường là baseline linh hoạt để bắt đầu. Khi đã hiểu pattern sử dụng ổn định, tổ chức có thể kết hợp on-demand với reserved/committed capacity hoặc spot để cân bằng chi phí và rủi ro.

Không so sánh đơn giá riêng lẻ. So sánh chi phí trên một đơn vị công việc hoàn thành, có tính đến downtime, retry, performance, license, storage và network.

## 17. Những sai lầm thường gặp khi đo thời gian sử dụng

1. **Dùng CPU utilization để suy ra billable hours.** CPU thấp không làm giảm instance-hours nếu meter tính theo thời gian instance.
2. **Coi Stop VM là dừng mọi chi phí.** Disk, IP, snapshot, license và network service có thể còn tính.
3. **Dùng thời điểm nhấn nút làm timestamp billing.** API request và state transition có thể khác thời điểm.
4. **Tự làm tròn thời gian.** Quy tắc minimum và rounding phụ thuộc meter.
5. **Nhân thời gian với cấu hình cuối cùng.** VM resize giữa kỳ cần chia interval theo SKU.
6. **Cộng tổng elapsed time thay cho instance-hours.** Nhiều VM chạy song song tạo tổng instance-hours lớn hơn thời gian đồng hồ.
7. **Bỏ qua resource phụ.** Hóa đơn compute không giải thích storage, egress, IP và monitoring.
8. **Coi pod request là billable quantity của VM.** Node VM có thể bị tính theo capacity trong khi pod metrics dùng cho phân bổ nội bộ.
9. **Bỏ qua warm/provisioned capacity.** Serverless hoặc container warm capacity có thể có meter riêng.
10. **So sánh list cost với net cost.** Phải thống nhất discount, credit và charge type.
11. **Không gắn owner/tag.** Chi phí phát sinh nhưng không xác định được team chịu trách nhiệm.
12. **Chỉ xem báo cáo ngày hiện tại.** Billing export có thể trễ hoặc được điều chỉnh.

## 18. Ví dụ tổng hợp: đo một môi trường test on-demand

Một team có môi trường test gồm:
- 2 VM application, mỗi máy 4 vCPU.
- 1 VM worker, 8 vCPU.
- 3 disk dữ liệu, mỗi disk 100 GiB.
- Một public IP và load balancer.
- Môi trường chạy từ 09:00 đến 13:00 trong ngày test.

### Tính compute runtime

Application VMs:

\[
2 \times 4\ hours = 8\ instance\text{-}hours
\]

Worker VM:

\[
1 \times 4\ hours = 4\ instance\text{-}hours
\]

Tổng:

\[
8 + 4 = 12\ instance\text{-}hours
\]

Nếu tính theo vCPU-hour:

\[
(2 \times 4 + 8) \times 4 = 64\ vCPU\text{-}hours
\]

Hai con số đo hai thứ khác nhau. Billing export có thể dùng một hoặc nhiều meter theo cấu hình dịch vụ.

### Tính storage

Nếu 3 disk 100 GiB được giữ trong 30 ngày:

\[
3 \times 100 \times 30 = 9{,}000\ GiB\text{-}days
\]

Storage thường có đơn vị billing riêng như GiB-month, có thể dùng số giờ/ngày trong kỳ để quy đổi. Compute chỉ chạy 4 giờ không có nghĩa disk chỉ bị tính phí 4 giờ.

### Kiểm tra tài nguyên phụ

Sau test, VM được stop nhưng team muốn giữ disk thêm 7 ngày để phân tích kết quả. Khi đó:
- Compute có thể ngừng tính sau khi deallocate theo quy tắc provider.
- Disk tiếp tục phát sinh storage charge.
- Public IP có thể còn phí nếu vẫn được giữ.
- Load balancer có thể tiếp tục có phí theo giờ và traffic.
- Log/monitoring vẫn có thể phát sinh ingest/retention.

Báo cáo chi phí nên tách compute, storage, network và shared service thay vì ghi một dòng “test environment 4 hours”.

## 19. Quy trình xây dựng báo cáo usage và cost

Một báo cáo có thể gồm các phần:

### Usage

- Resource ID và owner.
- Resource type/SKU.
- Region/zone.
- Billable start/end hoặc usage quantity.
- Unit.
- Runtime theo lifecycle event.
- Utilization CPU/RAM/network/storage.
- Idle time hoặc time outside schedule.

### Cost

- List cost.
- Effective/net cost.
- Discount/credit.
- Storage/network/license.
- Shared cost allocation.
- Cost center/team.
- Cost per request/job/transaction.

### Reconciliation

- Billing quantity.
- Event-derived quantity.
- Delta.
- Lý do sai lệch.
- Trạng thái điều tra.
- Người chịu trách nhiệm.

### Action

- Stop/schedule.
- Resize.
- Autoscale.
- Delete orphan resource.
- Change pricing model.
- Improve tagging.
- Review commitment.
- Optimize workload.

## 20. Checklist đo thời gian sử dụng tài nguyên on-demand

- [ ] Đã xác định meter và đơn vị tính phí cho từng resource.
- [ ] Đã đọc quy tắc billable start/end, minimum duration và rounding.
- [ ] Đã phân biệt provisioned time, runtime, utilization và billable usage.
- [ ] Đã thu thập resource ID và lifecycle event.
- [ ] Timestamp có timezone rõ ràng và được chuẩn hóa.
- [ ] Đã xử lý nhiều lần start/stop trong cùng kỳ.
- [ ] Đã chia interval khi VM resize hoặc đổi SKU.
- [ ] Đã đối chiếu event-derived duration với billing export.
- [ ] Đã tách compute, disk, snapshot, IP, network và license.
- [ ] Đã phân biệt VM node billing với pod-level allocation.
- [ ] Đã tính request/duration/resource-time cho serverless.
- [ ] Đã áp dụng tag owner, service, environment và cost center.
- [ ] Đã xác định cách phân bổ shared cost.
- [ ] Đã kiểm tra billing data delay và adjustment.
- [ ] Đã đo utilization cùng billable hours để phát hiện overprovisioning.
- [ ] Đã kiểm tra orphan disk, IP, snapshot và load balancer.
- [ ] Đã có schedule/autoscaling policy và cleanup owner.
- [ ] Đã xác định cost per request/job/transaction nếu phù hợp.

## Kết luận

On-demand cho phép tạo và sử dụng compute theo nhu cầu, nhưng chi phí được xác định bởi meter và quy tắc billable của từng dịch vụ. Thời gian VM được tính phí không đồng nghĩa với thời gian CPU bận; một VM idle vẫn có thể phát sinh compute charge, còn VM đã stop vẫn có thể giữ phí disk, IP, snapshot hoặc license. Đo chính xác cần kết hợp lifecycle event, usage quantity trong billing export và metric vận hành. Khi tách rõ instance-hours, vCPU-time, memory-time, request duration và các resource phụ, đội vận hành có thể đối chiếu hóa đơn, tìm thời gian idle, phân bổ chi phí và chọn cách schedule, autoscale hoặc rightsizing phù hợp.
